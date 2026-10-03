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
from state import Store, OUTCOMES, DEFAULT_HOME

FIELDS = ['event_key','day','date','start','end','timezone','event','status','your_decision',
          'networking_fit','what_to_expect','location','hosts','url','attendance_notes','evidence']
RECOMMENDATION_FIELDS = ['recommendation', 'fit_score', 'fit_confidence', 'target_people',
                         'why_recommended', 'conversation_plan', 'fit_sources', 'conflicting_event_keys']


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
    fields = FIELDS + RECOMMENDATION_FIELDS if recommendations else FIELDS
    ranked = {}
    if recommendations:
        from recommend import rank
        ranked = {r['event_key']: r for r in rank(s, campaign, limit=limit,
                  decisions={k: v['your_decision'] for k, v in previous.items()})}
    rows = []
    for event in s.listing(campaign):
        if event['status'] not in OUTCOMES:
            continue
        m = event['metadata']
        row = {field: '' for field in fields}
        row.update(event_key=event['id'], event=m.get('title', event['url']), status=event['status'],
                   your_decision=event['decision'], networking_fit=m.get('fit', ''), what_to_expect=m.get('offers', ''),
                   location=m.get('location', ''), hosts=m.get('hosts', ''), url=event['url'],
                   attendance_notes=event['notes'], evidence=event['evidence'], timezone=timezone)
        for key in ('start', 'end'):
            if m.get(key):
                dt = datetime.fromisoformat(m[key])
                if dt.tzinfo is None:
                    raise ValueError('Event times must include timezone offsets')
                local = dt.astimezone(ZoneInfo(timezone))
                row[key] = local.isoformat(timespec='minutes')
                if key == 'start':
                    row.update(date=local.date().isoformat(), day=local.strftime('%A'))
        if event['id'] in previous:
            for key in ('your_decision', 'attendance_notes'):
                row[key] = previous[event['id']][key]
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
