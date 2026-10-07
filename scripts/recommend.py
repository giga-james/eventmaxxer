#!/usr/bin/env python3
"""Evidence-backed attendance recommendations. No browsing or registration actions."""
import argparse
from datetime import datetime, timezone
import json
from state import Store, DEFAULT_HOME, DECLINE_WORDS


def assess(store, campaign, eid, data):
    """Persist a campaign-specific judgment without changing application state."""
    config = json.loads(store.campaign(campaign)['config'])
    goal = config.get('preferences', {}).get('networking_goal')
    if not isinstance(goal, str) or not goal.strip():
        raise ValueError('Set preferences.networking_goal from the user first')
    if eid not in {e['id'] for e in store.listing(campaign)}:
        raise ValueError('Event is not in this campaign')
    for field in ('audience_fit', 'conversation_access'):
        if type(data.get(field)) is not int or not 0 <= data[field] <= 3:
            raise ValueError(field + ' must be an integer from 0 to 3')
    for field in ('reason', 'target_people', 'conversation_plan'):
        if not isinstance(data.get(field), str) or not data[field].strip():
            raise ValueError(field + ' is required')
    if data.get('confidence') not in ('low', 'medium', 'high'):
        raise ValueError('confidence must be low, medium or high')
    evidence = data.get('sources')
    if not isinstance(evidence, list) or not evidence:
        raise ValueError('Source evidence is required')
    for source in evidence:
        if not isinstance(source, dict) or any(not isinstance(source.get(k), str) or not source[k].strip()
                                               for k in ('url', 'observation', 'checked_at')):
            raise ValueError('Each source needs url, observation and checked_at')
        from state import canonical_url
        canonical_url(source['url'])
        if datetime.fromisoformat(source['checked_at']).utcoffset() is None:
            raise ValueError('Source checked_at needs a timezone')
    record = {k: data[k] for k in ('audience_fit', 'conversation_access', 'confidence',
                                  'reason', 'target_people', 'conversation_plan', 'sources')}
    record.update(goal=goal, assessed_at=datetime.now(timezone.utc).isoformat())
    with store.transaction():
        store.db.execute('INSERT OR REPLACE INTO assessments(campaign,event,data) VALUES(?,?,?)',
                         (campaign, eid, json.dumps(record)))
    return record


def rank(store, campaign, limit=3, now=None, decisions=None):
    """Return ranked options; unknown facts remain research tasks, not low-fit facts."""
    if type(limit) is not int or limit < 1:
        raise ValueError('limit must be a positive integer')
    now = now or datetime.now(timezone.utc)
    if now.utcoffset() is None:
        raise ValueError('now needs a timezone')
    goal = json.loads(store.campaign(campaign)['config']).get('preferences', {}).get('networking_goal')
    assessments = {r['event']: json.loads(r['data']) for r in store.db.execute(
        'SELECT event,data FROM assessments WHERE campaign=?', (campaign,))}
    results = []
    for event in store.listing(campaign):
        m = event['metadata']
        a = assessments.get(event['id'])
        if a and a['goal'] != goal:
            a = None
        item = dict(event_key=event['id'], event=m.get('title', event['url']), url=event['url'],
                    status=event['status'], assessment=a, score=None, recommendation='Research',
                    reason='Needs an assessment for the current networking goal', conflicts=[])
        start = end = None
        try:
            start = datetime.fromisoformat(m['start'])
            end = datetime.fromisoformat(m['end']) if m.get('end') else None
            if start.utcoffset() is None or (end and (end.utcoffset() is None or end <= start)):
                raise ValueError('Invalid interval')
        except (KeyError, ValueError, TypeError):
            start = end = None
        item['_start'], item['_end'] = start, end
        decision = (decisions or {}).get(event['id'], event['decision']).strip().lower()
        if decision in DECLINE_WORDS:
            item.update(recommendation='Skipped by you', reason='Preserved attendance decision')
        elif event['status'] in ('declined', 'closed', 'skipped', 'cancelled'):
            item.update(recommendation='Unavailable', reason='Registration is ' + event['status'])
        elif start and (end or start) <= now:
            item.update(recommendation='Past', reason='Event has ended or its known start has passed')
        elif a and goal and a['goal'] == goal:
            item['score'] = a['audience_fit'] * 2 + a['conversation_access']
            if a['confidence'] == 'low':
                item['reason'] = 'Low confidence: verify audience and conversation access'
            elif not start:
                item['reason'] = 'Verify event date and timezone'
            elif a['audience_fit'] < 2 or a['conversation_access'] < 1:
                item.update(recommendation='Low priority', reason=a['reason'])
            elif event['status'] in ('approved', 'going'):
                item.update(recommendation='Consider', reason=a['reason'])
            else:
                item.update(recommendation='Conditional', reason='Admission unconfirmed. ' + a['reason'])
        results.append(item)
    results.sort(key=lambda r: (-(r['score'] if r['score'] is not None else -1),
                                r['_start'] or datetime.max.replace(tzinfo=timezone.utc), r['event_key']))
    selected = []
    for item in results:
        if item['recommendation'] != 'Consider':
            continue
        conflicts = [other['event_key'] for other in selected
                     if item['_end'] and other['_end'] and
                     item['_start'] < other['_end'] and other['_start'] < item['_end']]
        if conflicts:
            item.update(recommendation='Alternative', conflicts=conflicts,
                        reason='Overlaps a higher-ranked shortlist event. ' + item['reason'])
        elif len(selected) < limit:
            item['recommendation'] = 'Shortlist'
            selected.append(item)
        if not item['_end']:
            item['reason'] += ' End time unknown; check schedule before committing.'
    for item in results:
        del item['_start'], item['_end']
    return results


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--home', type=str, default=str(DEFAULT_HOME))
    p.add_argument('--campaign', required=True)
    p.add_argument('--limit', type=int, default=3)
    p.add_argument('--event', help='Save an assessment for this event instead of ranking')
    p.add_argument('--json', help='Assessment JSON or @private/path.json')
    args = p.parse_args()
    s = Store(args.home)
    try:
        if args.event:
            from pathlib import Path
            if not args.json:
                p.error('--event requires --json')
            data = json.loads(Path(args.json[1:]).read_text() if args.json.startswith('@') else args.json)
            output = assess(s, args.campaign, args.event, data)
        else:
            output = rank(s, args.campaign, args.limit)
        print(json.dumps(output, indent=2))
    finally:
        s.db.close()
