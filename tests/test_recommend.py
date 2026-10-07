import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from state import Store
from recommend import assess, rank
from export import export, FIELDS, RECOMMENDATION_FIELDS


class Recommendations(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.s = Store(self.tmp.name)
        self.s.init('one', 'account', {'sources': [], 'preferences': {'networking_goal': 'Meet robotics buyers'}})
        self.s.authorize('one', 'Fictional test authorization')
        self.now = datetime(2026, 10, 1, tzinfo=timezone.utc)

    def tearDown(self):
        self.s.db.close()
        self.tmp.cleanup()

    def event(self, slug, status='approved', fit=3, confidence='high', start='2026-10-07T17:00:00-07:00'):
        eid = self.s.add('one', 'https://example.org/' + slug, {'start': start, 'end': '2026-10-07T20:00:00-07:00', 'service': 'example.org'})
        self.s.review(eid, 'ready', 'Free and eligible', {'free': True, 'eligible': True})
        self.s.reserve('one', eid)
        self.s.result(eid, status, 'Verified test status')
        if status in ('approved', 'going'):
            self.s.rsvp(eid, 'attending', 'Fictional user confirmed attendance')
        self.s.ack('one', eid, 'Test tracker readback')
        assess(self.s, 'one', eid, {'audience_fit': fit, 'conversation_access': 2,
            'confidence': confidence, 'target_people': 'Robotics procurement leads',
            'reason': 'Buyer roundtables', 'conversation_plan': 'Ask about procurement pain points',
            'sources': [{'url': 'https://example.org/' + slug, 'observation': 'Lists buyer roundtables',
                         'checked_at': '2026-10-01T12:00:00+00:00'}]})
        return eid

    def test_admission_confidence_and_overlap(self):
        first = self.event('a')
        second = self.event('b', fit=2)
        pending = self.event('pending', status='pending')
        uncertain = self.event('uncertain', confidence='low')
        rows = {r['event_key']: r for r in rank(self.s, 'one', now=self.now)}
        self.assertEqual(rows[first]['recommendation'], 'Shortlist')
        self.assertEqual(rows[second]['recommendation'], 'Alternative')
        self.assertEqual(rows[second]['conflicts'], [first])
        self.assertEqual(rows[pending]['recommendation'], 'Conditional')
        self.assertEqual(rows[uncertain]['recommendation'], 'Research')
        self.assertEqual(self.s.event(pending)['status'], 'pending')
        self.assertEqual(self.s.gate('one')['action'], 'review')

    def test_goal_changes_invalidate_and_campaigns_are_independent(self):
        eid = self.event('a')
        self.s.configure('one', {'preferences': {'networking_goal': 'Meet collaborators'}})
        self.assertEqual(rank(self.s, 'one', now=self.now)[0]['recommendation'], 'Research')
        self.assertIsNone(rank(self.s, 'one', now=self.now)[0]['assessment'])
        self.s.init('two', 'account', {'sources': [], 'preferences': {'networking_goal': 'Meet robotics buyers'}})
        self.s.add('two', 'https://example.org/a', {})
        self.assertEqual(rank(self.s, 'two', now=self.now)[0]['recommendation'], 'Research')

    def test_missing_time_past_and_skipped(self):
        eid = self.event('a')
        self.assertEqual(rank(self.s, 'one', now=self.now, decisions={eid: 'Skip'})[0]['recommendation'], 'Skipped by you')
        self.assertEqual(rank(self.s, 'one', now=datetime(2027, 1, 1, tzinfo=timezone.utc))[0]['recommendation'], 'Past')
        with self.s.transaction():
            self.s.db.execute('UPDATE events SET metadata=? WHERE id=?', (json.dumps({}), eid))
        self.assertEqual(rank(self.s, 'one', now=self.now)[0]['recommendation'], 'Research')

    def test_limit(self):
        self.event('a')
        self.event('b', start='2026-10-07T20:00:00-07:00')
        # Supply a valid later interval.
        e = self.s.listing('one')[1]
        m = e['metadata']; m['end'] = '2026-10-07T21:00:00-07:00'
        with self.s.transaction():
            self.s.db.execute('UPDATE events SET metadata=? WHERE id=?', (json.dumps(m), e['id']))
        rows = rank(self.s, 'one', limit=1, now=self.now)
        self.assertEqual(sum(r['recommendation'] == 'Shortlist' for r in rows), 1)
        self.assertEqual(sum(r['recommendation'] == 'Consider' for r in rows), 1)

    def test_export_upgrades_preserves_and_refreshes(self):
        self.event('a')
        path = Path(self.tmp.name) / 'tracker.csv'
        export(self.s, 'one', path)
        with path.open() as f:
            rows = list(csv.DictReader(f))
        rows[0]['your_decision'] = 'Skip'
        rows[0]['attendance_notes'] = 'Personal note'
        with path.open('w') as f:
            w = csv.DictWriter(f, FIELDS); w.writeheader(); w.writerows(rows)
        export(self.s, 'one', path, recommendations=True)
        export(self.s, 'one', path)
        with path.open() as f:
            reader = csv.DictReader(f)
            row = next(reader)
            self.assertEqual(reader.fieldnames, FIELDS + RECOMMENDATION_FIELDS)
        self.assertEqual(row['recommendation'], 'Skipped by you')
        self.assertEqual(row['attendance_notes'], 'Personal note')
        self.assertEqual(row['status'], 'approved')
        # The tracker Skip is the user's RSVP, so the spot is queued for automatic release.
        self.assertEqual(self.s.event(row['event_key'])['rsvp'], 'cancel_pending')
        self.assertEqual(self.s.gate('one')['action'], 'sync')
        self.assertEqual(row['your_decision'], 'Skip')

    def test_chat_rsvp_overrides_stale_cell_in_ranking(self):
        eid = self.event('a')
        path = Path(self.tmp.name) / 'tracker.csv'
        export(self.s, 'one', path, recommendations=True)
        with path.open() as f:
            row = next(csv.DictReader(f))
        self.assertEqual((row['your_decision'], row['recommendation']), ('Attend', 'Shortlist'))
        self.s.rsvp(eid, 'not_attending', 'User in chat: cannot go')
        export(self.s, 'one', path)
        with path.open() as f:
            row = next(csv.DictReader(f))
        self.assertEqual((row['your_decision'], row['recommendation']), ('Not attending', 'Skipped by you'))

    def test_tracker_no_is_skipped_in_ranking(self):
        eid = self.event('a')
        path = Path(self.tmp.name) / 'tracker.csv'
        export(self.s, 'one', path, recommendations=True)
        with path.open() as f:
            rows = list(csv.DictReader(f))
        rows[0]['your_decision'] = 'No'
        with path.open('w') as f:
            w = csv.DictWriter(f, FIELDS + RECOMMENDATION_FIELDS); w.writeheader(); w.writerows(rows)
        export(self.s, 'one', path)
        with path.open() as f:
            row = next(csv.DictReader(f))
        self.assertEqual(self.s.event(eid)['rsvp'], 'cancel_pending')
        self.assertEqual((row['your_decision'], row['recommendation']), ('No', 'Skipped by you'))

    def test_assessment_requires_goal_and_evidence(self):
        eid = self.s.add('one', 'https://example.org/new', {})
        with self.assertRaises(ValueError):
            assess(self.s, 'one', eid, {})
        self.assertEqual(self.s.db.execute('SELECT COUNT(*) FROM assessments').fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
