import csv
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from state import Store, canonical_url
from wake import tick
from export import export, FIELDS


class Workflow(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.s = Store(self.home)
        self.s.init('one', 'account', {'sources':['https://example.org'], 'discovery_complete':True})
        self.s.authorize('one', 'User authorized free events')

    def tearDown(self):
        self.s.db.close()
        self.tmp.cleanup()

    def ready(self, slug='one', service='partiful.com', campaign='one'):
        eid = self.s.add(campaign, 'https://' + service + '/e/' + slug,
                         {'title':slug, 'service':service, 'start':'2026-10-07T17:30:00-07:00'})
        self.s.review(eid, 'ready', 'Explicitly free and founder eligible', {'free':True, 'eligible':True})
        return eid

    def test_draft_blocks_applications(self):
        self.s.init('draft', 'other', {'sources':[]})
        eid = self.ready(campaign='draft')
        with self.assertRaises(ValueError):
            self.s.reserve('draft', eid)
        self.assertEqual(self.s.gate('draft')['action'], 'idle')

    def test_canonical_dedup_preserves_unknown_identity(self):
        self.assertEqual(canonical_url('https://partiful.com/e/one?rsvp=true&c=abc'),
                         'https://partiful.com/e/one')
        self.assertNotEqual(canonical_url('https://example.org/?c=1'),
                            canonical_url('https://example.org/?c=2'))
        self.assertNotEqual(canonical_url('https://example.org/#/1'),
                            canonical_url('https://example.org/#/2'))
        first = self.ready()
        self.assertEqual(self.s.add('one','https://partiful.com/e/one?utm_source=x',{}), first)
        self.s.alias(first, 'https://tickets.example.org/123')
        self.assertEqual(self.s.add('one','https://tickets.example.org/123',{}), first)

    def test_uncertain_result_blocks_other_campaign_same_account(self):
        first = self.ready()
        self.s.init('two', 'account', {'sources':[], 'discovery_complete':True})
        self.s.authorize('two', 'User authorization')
        second = self.ready('second', campaign='two')
        self.s.reserve('one', first)
        # A new connection sees the durable reservation.
        other = Store(self.home)
        self.assertEqual(other.gate('two'), {'action':'reconcile','event':first})
        with self.assertRaises(ValueError):
            other.reserve('two', second)
        other.db.close()
        self.s.result(first, 'not_submitted', 'Account history confirms no registration')
        self.assertEqual(self.s.gate('two')['action'], 'apply')

    def test_rate_limit_exact_boundary_and_server_deadline(self):
        eid = self.ready()
        self.s.reserve('one', eid, now=100)
        self.s.result(eid,'rate_limited','RSVP rate limit',now=100,retry_after=5000)
        self.assertEqual(self.s.gate('one',4999), {'action':'wait','retry_at':5000})
        self.s.reserve('one',eid,now=5000)
        with self.assertRaises(ValueError):
            self.s.reserve('one',eid,now=5000)
        self.s.result(eid,'rate_limited','Still limited',now=5001)
        self.assertEqual(self.s.gate('one',6000), {'action':'wait','retry_at':6201})
        self.assertEqual(self.s.gate('one',6201)['action'], 'apply')

    def test_unaffected_service_proceeds(self):
        first = self.ready()
        self.s.reserve('one',first,now=100)
        self.s.result(first,'rate_limited','Limited',now=100)
        second = self.ready('second','other.example.org')
        self.assertEqual(self.s.gate('one',101), {'action':'apply','event':second})

    def test_success_requires_export_before_next_application(self):
        first = self.ready()
        second = self.ready('two')
        self.s.reserve('one',first)
        self.s.result(first,'pending','Awaiting approval visible')
        with self.assertRaises(ValueError):
            self.s.reserve('one',second)
        self.s.ack('one', first, 'Read back sheet row')
        self.assertEqual(self.s.gate('one'), {'action':'apply','event':second})
        self.assertEqual(self.s.event(first)['status'],'pending')

    def test_profile_history_and_staleness(self):
        self.s.fact('stage','bootstrapped','User',expires=100,share='routine')
        self.s.fact('stage','seed','User correction',expires=200,share='ask')
        self.assertEqual(self.s.db.execute('SELECT COUNT(*) FROM fact_history').fetchone()[0],2)
        self.assertTrue(self.s.profile(now=201)[0]['stale'])
        self.assertEqual(self.s.profile(now=150)[0]['value'],'seed')

    def test_question_answer_does_not_imply_global_fact_or_eligibility(self):
        eid = self.ready()
        q = self.s.question(eid,'Are you presenting?')
        self.s.review(eid,'needs_input','Required question')
        self.s.answer(q,'Attend only','User')
        self.assertEqual(self.s.event(eid)['status'],'needs_input')
        self.assertEqual(self.s.profile(),[])
        with self.assertRaises(ValueError): self.s.finish('one')

    def test_free_eligibility_required_and_completion_guard(self):
        eid = self.s.add('one','https://example.org/x',{})
        with self.assertRaises(ValueError): self.s.review(eid,'ready','Looks relevant')
        with self.assertRaises(ValueError): self.s.finish('one')
        self.s.review(eid,'skipped','Paid ticket')
        self.s.finish('one')
        self.assertEqual(self.s.gate('one')['reason'],'complete')

    def test_export_preserves_decisions_and_local_day(self):
        eid = self.ready()
        self.s.reserve('one',eid)
        self.s.result(eid,'pending','Pending visible')
        path = self.home / 'events.csv'
        self.s.configure('one',{'tracker':{'kind':'csv','path':str(path)}})
        self.assertEqual(export(self.s,'one',path),1)
        with path.open(newline='') as f: rows=list(csv.DictReader(f))
        rows[0]['your_decision']='Attend'
        rows[0]['attendance_notes']='Meet a friend'
        with path.open('w',newline='') as f:
            w=csv.DictWriter(f,FIELDS);w.writeheader();w.writerows(rows)
        export(self.s,'one',path)
        with path.open(newline='') as f: row=next(csv.DictReader(f))
        self.assertEqual(row['day'],'Wednesday')
        self.assertEqual(row['your_decision'],'Attend')
        self.assertEqual(row['attendance_notes'],'Meet a friend')
        self.assertEqual(self.s.gate('one')['action'],'idle')

    def test_csv_does_not_ack_google_sheet(self):
        eid = self.ready()
        self.s.reserve('one',eid)
        self.s.result(eid,'waitlisted','Waitlist visible')
        export(self.s,'one',self.home/'backup.csv')
        self.assertEqual(self.s.gate('one')['action'],'sync')


    def test_sync_blocks_other_campaign_same_account(self):
        first = self.ready()
        self.s.init('two', 'account', {'sources':[], 'discovery_complete':True})
        self.s.authorize('two', 'User authorization')
        second = self.ready('second', campaign='two')
        self.s.reserve('one', first)
        self.s.result(first, 'pending', 'Pending visible')
        self.assertEqual(self.s.gate('two'), {'action':'sync','event':first,'campaign':'one'})
        with self.assertRaises(ValueError): self.s.reserve('two', second)

    def admit(self, slug='one', start='2026-10-07T17:30:00-07:00', outcome='approved'):
        eid = self.s.add('one', 'https://partiful.com/e/' + slug,
                         {'title':slug, 'service':'partiful.com', 'start':start})
        self.s.review(eid, 'ready', 'Explicitly free', {'free':True, 'eligible':True})
        self.s.reserve('one', eid, now=0)
        self.s.result(eid, outcome, 'Approval visible', now=0)
        self.s.ack('one', eid, 'Read back tracker row')
        return eid

    def test_admission_requires_rsvp_and_backlog_stops_new_applications(self):
        later = 2_000_000_000
        admitted = [self.admit(str(i), start='2033-05-18T03:33:20+00:00') for i in range(3)]
        self.assertEqual(self.s.event(admitted[0])['rsvp'], 'needs_rsvp')
        fresh = self.ready('fresh')
        gate = self.s.gate('one', now=0)
        self.assertEqual((gate['action'], gate['reason'], gate['events']), ('idle', 'awaiting_rsvp', admitted))
        with self.assertRaises(ValueError): self.s.reserve('one', fresh, now=0)
        self.s.rsvp(admitted[0], 'attending', 'User said yes on 2026-10-07')
        self.assertEqual(self.s.gate('one', now=0)['action'], 'sync')
        self.s.ack('one', admitted[0], 'Read back')
        self.assertEqual(self.s.gate('one', now=0), {'action':'apply','event':fresh})
        self.assertEqual(self.s.event(admitted[0])['decision'], 'Attend')
        # Past events no longer count against the backlog.
        self.assertEqual(self.s.unanswered_rsvps('account', later), [])

    def test_not_attending_automatically_cancels_before_new_applications(self):
        eid = self.admit(start='2033-05-18T03:33:20+00:00')
        fresh = self.ready('fresh')
        with self.assertRaises(ValueError): self.s.cancelled(eid, 'Cancelled', now=0)
        self.s.rsvp(eid, 'not_attending', 'User on 2026-10-07: cannot make it')
        self.s.ack('one', eid, 'Read back')
        self.assertEqual(self.s.gate('one', now=0), {'action':'cancel','event':eid,'reason':'not_attending'})
        with self.assertRaises(ValueError): self.s.reserve('one', fresh, now=0)
        with self.assertRaises(ValueError): self.s.finish('one')
        self.s.cancelled(eid, 'Visible: registration cancelled', now=0)
        e = self.s.event(eid)
        self.assertEqual((e['status'], e['rsvp'], e['decision']), ('cancelled', 'cancelled', 'Not attending'))
        self.assertEqual(self.s.gate('one', now=0)['action'], 'sync')
        self.s.ack('one', eid, 'Read back')
        self.assertEqual(self.s.gate('one', now=0), {'action':'apply','event':fresh})
        # A cancelled spot is never re-reviewed into a new application.
        with self.assertRaises(ValueError): self.s.review(eid, 'ready', 'Free', {'free':True, 'eligible':True})
        with self.assertRaises(ValueError): self.s.rsvp(eid, 'attending', 'Changed mind')

    def test_unanswered_rsvp_is_released_at_deadline(self):
        start = 100_000
        eid = self.admit(start='1970-01-02T03:46:40+00:00')
        self.assertEqual(self.s.gate('one', now=start - 86_401)['action'], 'idle')
        self.assertEqual(self.s.gate('one', now=start - 86_400), {'action':'cancel','event':eid,'reason':'rsvp_deadline'})
        with self.assertRaises(ValueError): self.s.cancelled(eid, 'Too early', now=start - 86_401)
        prefs = {'rsvp_deadline_hours': 48}
        self.s.configure('one', {'preferences': prefs})
        self.assertEqual(self.s.gate('one', now=start - 86_401)['reason'], 'rsvp_deadline')
        self.s.cancelled(eid, 'Visible cancellation', now=start - 86_401)
        self.assertEqual(self.s.event(eid)['status'], 'cancelled')

    def test_later_admission_starts_rsvp_and_pending_can_be_withdrawn(self):
        eid = self.admit(outcome='pending', start='2033-05-18T03:33:20+00:00')
        self.assertIsNone(self.s.event(eid)['rsvp'])
        self.s.admission(eid, 'approved', 'Approval email visible')
        self.assertEqual(self.s.event(eid)['rsvp'], 'needs_rsvp')
        self.assertEqual(self.s.gate('one', now=0)['action'], 'sync')
        with self.assertRaises(ValueError): self.s.admission(eid, 'declined', 'Already approved')
        self.s.ack('one', eid, 'Read back')
        other = self.admit('two', outcome='waitlisted', start='2033-05-18T03:33:20+00:00')
        self.s.rsvp(other, 'not_attending', 'User: withdraw')
        self.s.cancelled(other, 'Left waitlist', now=0)
        with self.assertRaises(ValueError): self.s.admission(other, 'approved', 'Late approval')

    def test_existing_admissions_migrate_to_needs_rsvp(self):
        eid = self.admit()
        self.s.db.execute("UPDATE events SET rsvp=NULL")
        self.s.db.execute("ALTER TABLE events DROP COLUMN rsvp")
        self.s.db.commit()
        self.s.db.close()
        self.s = Store(self.home)
        self.assertEqual(self.s.event(eid)['rsvp'], 'needs_rsvp')

    def test_export_shows_rsvp_and_cancellation(self):
        path = self.home / 'events.csv'
        self.s.configure('one', {'tracker':{'kind':'csv','path':str(path)}})
        asked = self.admit('asked', start='2033-05-18T03:33:20+00:00')
        gone = self.admit('gone', start='2033-05-18T03:33:20+00:00')
        export(self.s, 'one', path)
        with path.open(newline='') as f: rows = {r['event_key']: r for r in csv.DictReader(f)}
        rows[gone]['your_decision'] = 'Maybe'
        with path.open('w', newline='') as f:
            w = csv.DictWriter(f, FIELDS); w.writeheader(); w.writerows(rows.values())
        self.s.rsvp(gone, 'not_attending', 'User declined')
        self.s.cancelled(gone, 'Visible cancellation', now=0)
        export(self.s, 'one', path)
        with path.open(newline='') as f: rows = {r['event_key']: r for r in csv.DictReader(f)}
        self.assertEqual(rows[asked]['your_decision'], 'RSVP needed')
        rows[asked]['your_decision'] = 'Attend'
        with path.open('w', newline='') as f:
            w = csv.DictWriter(f, FIELDS); w.writeheader(); w.writerows(rows.values())
        export(self.s, 'one', path)
        self.assertEqual(self.s.event(asked)['rsvp'], 'attending')
        self.assertEqual(self.s.gate('one', now=0)['action'], 'idle')
        self.assertEqual((rows[gone]['status'], rows[gone]['your_decision']), ('cancelled', 'Not attending'))

    def write_decision(self, path, eid, decision):
        with path.open(newline='') as f: rows = list(csv.DictReader(f))
        for r in rows:
            if r['event_key'] == eid: r['your_decision'] = decision
        with path.open('w', newline='') as f:
            w = csv.DictWriter(f, FIELDS); w.writeheader(); w.writerows(rows)

    def decision(self, path, eid):
        with path.open(newline='') as f:
            return next(r['your_decision'] for r in csv.DictReader(f) if r['event_key'] == eid)

    def test_tracker_can_reverse_queued_cancellation_and_chat_answer_wins_over_stale_cell(self):
        path = self.home / 'events.csv'
        self.s.configure('one', {'tracker':{'kind':'csv','path':str(path)}})
        eid = self.admit(start='2033-05-18T03:33:20+00:00')
        export(self.s, 'one', path)
        self.write_decision(path, eid, 'Skip')
        export(self.s, 'one', path)
        self.assertEqual(self.s.event(eid)['rsvp'], 'cancel_pending')
        # User corrects the cell before the agent releases the spot.
        self.write_decision(path, eid, 'Attend')
        export(self.s, 'one', path)
        self.assertEqual(self.s.event(eid)['rsvp'], 'attending')
        self.assertEqual(self.s.gate('one', now=0)['action'], 'idle')
        self.assertEqual(self.decision(path, eid), 'Attend')
        # A later chat answer is not undone by the cell the export wrote before it.
        self.s.rsvp(eid, 'not_attending', 'User in chat: cannot go')
        export(self.s, 'one', path)
        self.assertEqual(self.s.event(eid)['rsvp'], 'cancel_pending')
        self.assertEqual(self.decision(path, eid), 'Not attending')
        self.assertEqual(self.s.gate('one', now=0)['action'], 'cancel')

    def test_migrated_admissions_are_queued_for_tracker_sync(self):
        eid = self.admit()
        self.assertEqual(self.s.gate('one', now=0)['action'], 'idle')
        self.s.db.execute("ALTER TABLE events DROP COLUMN rsvp")
        self.s.db.commit()
        self.s.db.close()
        self.s = Store(self.home)
        self.assertEqual(self.s.gate('one', now=0), {'action':'sync','event':eid,'campaign':'one'})

    def test_finish_waits_for_upcoming_rsvps(self):
        eid = self.admit(start='2033-05-18T03:33:20+00:00')
        with self.assertRaises(ValueError): self.s.finish('one')
        self.s.rsvp(eid, 'attending', 'User: yes')
        self.s.ack('one', eid, 'Read back')
        self.s.finish('one')

    def test_draft_campaign_deadline_cannot_cancel(self):
        start = 100_000
        eid = self.admit(start='1970-01-02T03:46:40+00:00')
        self.s.init('draft', 'account', {'sources':[], 'preferences':{'rsvp_deadline_hours':1000}})
        self.s.add('draft', 'https://partiful.com/e/one', {})
        self.s.ack('draft', eid, 'Read back')
        self.assertEqual(self.s.gate('one', now=start - 86_401)['action'], 'idle')
        with self.assertRaises(ValueError): self.s.cancelled(eid, 'Too early', now=start - 86_401)
        self.assertEqual(self.s.gate('one', now=start - 86_400)['reason'], 'rsvp_deadline')

    def test_unparseable_start_is_unknown(self):
        for i, start in enumerate(('TBD', '2033-05-18T03:33:20')):
            eid = self.admit(str(i), start=start)
            self.assertEqual(self.s.unanswered_rsvps('account', 0)[-1], (eid, None))
        self.assertEqual(self.s.gate('one', now=0)['action'], 'idle')
        with self.assertRaises(ValueError): self.s.finish('one')

    def test_runner_account_lock(self):
        import fcntl
        import hashlib
        self.ready()
        lock = self.home / ('runner-' + hashlib.sha256(b'account').hexdigest() + '.lock')
        with lock.open('a') as handle:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with patch('wake.subprocess.Popen', side_effect=AssertionError('no parallel run')):
                self.assertEqual(tick(self.runner_config())['action'], 'busy')

    def test_runner_timeout_leaves_hold(self):
        self.ready()
        config = self.runner_config([sys.executable, '-c', 'import time; time.sleep(30)'])
        data = json.loads(config.read_text())
        data['timeout_seconds'] = 1
        config.write_text(json.dumps(data))
        self.assertEqual(tick(config)['exit_code'], 124)
        self.assertEqual(tick(config)['action'], 'runner_hold')

    def runner_config(self, argv=None):
        path=self.home/'runner.json'
        path.write_text(json.dumps({'state_home':str(self.home),'campaign':'one',
          'argv':argv or [sys.executable,'-c','import sys; sys.stdin.read()'],
          'capability_probe_verified':True,'timeout_seconds':5}))
        return path

    def test_cooldown_never_invokes_agent(self):
        eid=self.ready()
        self.s.reserve('one',eid,now=100)
        self.s.result(eid,'rate_limited','Limited',now=100)
        with patch('wake.subprocess.Popen', side_effect=AssertionError('must not start')):
            self.assertEqual(tick(self.runner_config(),now=101)['action'],'wait')
        self.assertFalse((self.home/'runs').exists())

    def test_runner_due_and_failure_hold(self):
        self.ready()
        config=self.runner_config([sys.executable,'-c','import sys; sys.stdin.read(); sys.exit(7)'])
        self.assertEqual(tick(config)['exit_code'],7)
        with patch('wake.subprocess.Popen', side_effect=AssertionError('no retry')):
            self.assertEqual(tick(config)['action'],'runner_hold')

    def test_runner_requires_capability_probe(self):
        self.ready()
        config=self.runner_config()
        data=json.loads(config.read_text());data['capability_probe_verified']=False
        config.write_text(json.dumps(data))
        self.assertEqual(tick(config)['action'],'needs_setup')

    def test_runner_success_saves_prompt_and_releases_hold(self):
        self.ready()
        result=tick(self.runner_config())
        self.assertEqual(result['exit_code'],0)
        self.assertIn('EVENTMAXXER.md',(Path(result['run'])/'prompt.txt').read_text())
        self.assertFalse(list(self.home.glob('*.hold')))

if __name__ == '__main__':
    unittest.main()
