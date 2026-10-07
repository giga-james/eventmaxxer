#!/usr/bin/env python3
"""Export verified applications, preserving existing user decisions/notes by event key."""
import argparse
import csv
import json
import os
from pathlib import Path
import tempfile
from datetime import datetime
from zoneinfo import ZoneInfo
import time
from state import Store, TRACKED, HELD, DEFAULT_HOME, started

FIELDS = ['event_key','day','date','start','end','timezone','event','status','your_decision',
          'networking_fit','what_to_expect','location','hosts','url','attendance_notes','evidence']
RECOMMENDATION_FIELDS = ['recommendation', 'fit_score', 'fit_confidence', 'target_people',
                         'why_recommended', 'conversation_plan', 'fit_sources', 'conflicting_event_keys']
DECLINE_WORDS = {'skip', 'decline', 'declined', 'not attending', 'no'}
ATTEND_WORDS = {'attend', 'attending', 'going', 'yes'}


def intent(decision):
    value = (decision or '').strip().lower()
    return 'not_attending' if value in DECLINE_WORDS else 'attending' if value in ATTEND_WORDS else None


def rsvp_intent(event):
    return {'attending': 'attending', 'cancel_pending': 'not_attending', 'cancelled': 'not_attending'}.get(event['rsvp'])


def ingest_rsvps(s, campaign, previous, destination):
    """Treat a decision the user changed in the tracker as their RSVP; a decline queues a release."""
    path = str(destination.resolve())
    written = {r['event']: r['decision'] for r in s.db.execute('SELECT event,decision FROM tracker_cells WHERE path=?', (path,))}
    for event in s.listing(campaign):
        cell = previous.get(event['id'], {}).get('your_decision', '')
        answer = intent(cell)
        # A cell this export wrote last time is not a new answer; it may predate a chat RSVP.
        if cell == written.get(event['id']) or answer is None or answer == rsvp_intent(event):
            continue
        # A past event's spot can no longer be released, so its cell stays a historical note.
        if event['status'] in HELD and event['rsvp'] != 'cancelled' and not started(event['metadata'], time.time()):
            s.rsvp(event['id'], answer, f'User tracker decision "{cell}" in {path}')


def shown_decision(event, cell):
    """Show the recorded RSVP, keeping the user's own wording when it agrees."""
    stated = intent(cell)
    if event['rsvp'] and (cell in ('', 'Undecided', 'RSVP needed')
                          or (stated and stated != rsvp_intent(event))
                          or (rsvp_intent(event) == 'not_attending' and stated is None)):
        return 'RSVP needed' if event['rsvp'] == 'needs_rsvp' else event['decision']
    return cell


def export(s, campaign, destination, timezone='America/Los_Angeles', recommendations=False, limit=3):
    destination = Path(destination)
    previous = {}
    if destination.exists():
        with destination.open(newline='') as f:
            reader = csv.DictReader(f)
            if reader.fieldnames not in (FIELDS, FIELDS + RECOMMENDATION_FIELDS):
                raise ValueError('Unexpected CSV schema; preserve file and reconcile')
            recommendations = recommendations or reader.fieldnames == FIELDS + RECOMMENDATION_FIELDS
            for row in reader:
                if row['event_key'] in previous:
                    raise ValueError('Duplicate keys in existing export')
                previous[row['event_key']] = row
    ingest_rsvps(s, campaign, previous, destination)
    decisions = {k: v['your_decision'] for k, v in previous.items()}
    for event in s.listing(campaign):
        if event['status'] in TRACKED:
            decisions[event['id']] = shown_decision(event, decisions.get(event['id'], event['decision']))
    fields = FIELDS + RECOMMENDATION_FIELDS if recommendations else FIELDS
    ranked = {}
    if recommendations:
        from recommend import rank
        # Rank from the reconciled decision, not a cell made stale by a newer RSVP.
        ranked = {r['event_key']: r for r in rank(s, campaign, limit=limit, decisions=decisions)}
    rows = []
    for event in s.listing(campaign):
        if event['status'] not in TRACKED:
            continue
        m = event['metadata']
        row = {field: '' for field in fields}
        row.update(event_key=event['id'], event=m.get('title', event['url']), status=event['status'],
                   your_decision=event['decision'], networking_fit=m.get('fit', ''), what_to_expect=m.get('offers', ''),
                   location=m.get('location', ''), hosts=m.get('hosts', ''), url=event['url'],
                   attendance_notes=event['notes'], evidence=event['evidence'], timezone=timezone)
        for key in ('start', 'end'):
            try:
                dt = datetime.fromisoformat(m[key])
            except (KeyError, TypeError, ValueError):
                continue  # Missing or unreadable times stay unknown (blank).
            if dt.utcoffset() is not None:
                local = dt.astimezone(ZoneInfo(timezone))
                row[key] = local.isoformat(timespec='minutes')
                if key == 'start':
                    row.update(date=local.date().isoformat(), day=local.strftime('%A'))
            # A time without an offset is ambiguous, so it also stays blank rather than guessed.
        if event['id'] in previous:
            row['attendance_notes'] = previous[event['id']]['attendance_notes']
        row['your_decision'] = decisions[event['id']]
        if recommendations:
            r = ranked[event['id']]
            a = r['assessment'] or {}
            row.update(recommendation=r['recommendation'], fit_score=str(r['score']) if r['score'] is not None else '',
                       fit_confidence=a.get('confidence', ''), target_people=a.get('target_people', ''),
                       why_recommended=r['reason'], conversation_plan=a.get('conversation_plan', ''),
                       fit_sources=json.dumps(a.get('sources', [])),
                       conflicting_event_keys=', '.join(r['conflicts']))
        rows.append(row)
    keys = {r['event_key'] for r in rows}
    rows.extend({field: v.get(field, '') for field in fields} for k, v in previous.items() if k not in keys)
    rows.sort(key=lambda r: (r['date'] or '9999', r['start'], r['event_key']))
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=destination.parent)
    try:
        with os.fdopen(fd, 'w', newline='') as f:
            writer = csv.DictWriter(f, fields)
            writer.writeheader()
            writer.writerows(rows)
        os.replace(tmp, destination)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)
    with destination.open(newline='') as f:
        actual = list(csv.DictReader(f))
    if actual != rows:
        raise ValueError('Export read-back mismatch')
    with s.transaction():
        s.db.executemany('INSERT OR REPLACE INTO tracker_cells VALUES(?,?,?)',
                         [(str(destination.resolve()), r['event_key'], r['your_decision']) for r in rows if r['event_key'] in keys])
    tracker = json.loads(s.campaign(campaign)['config']).get('tracker', {})
    if tracker.get('kind') == 'csv' and tracker.get('path') and Path(tracker['path']).expanduser().resolve() == destination.resolve():
        for eid in keys:
            s.ack(campaign, eid, 'CSV read-back verified: ' + str(destination.resolve()))
    return len(rows)

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--home', type=Path, default=DEFAULT_HOME)
    p.add_argument('--campaign', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--timezone', default='America/Los_Angeles')
    p.add_argument('--recommendations', action='store_true')
    p.add_argument('--limit', type=int, default=3)
    a=p.parse_args()
    print(export(Store(a.home),a.campaign,a.output,a.timezone,a.recommendations,a.limit))
