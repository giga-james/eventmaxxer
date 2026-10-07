#!/usr/bin/env python3
"""Private, transactional event application state. No network or browser access."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import time
from contextlib import contextmanager
from datetime import datetime
from urllib.parse import urlsplit, urlunsplit

DEFAULT_HOME = Path.home() / '.local/share/eventmaxxer'
OUTCOMES = {'pending', 'waitlisted', 'going', 'approved', 'declined'}
ADMITTED = {'going', 'approved'}
# Registrations the user still holds; organizers count these spots as taken.
HELD = {'pending', 'waitlisted', 'going', 'approved'}
# Exported registration states include cancellations the user asked for.
TRACKED = OUTCOMES | {'cancelled'}
# rsvp: NULL until admitted, then needs_rsvp -> attending | cancel_pending -> cancelled.
RSVP_LIMIT = 3
ATTEND_DECISION = 'Attend'
DECLINE_DECISION = 'Not attending'
# Tracker decision vocabulary, shared by RSVP ingestion and ranking.
DECLINE_WORDS = {'skip', 'decline', 'declined', 'not attending', 'no'}
ATTEND_WORDS = {'attend', 'attending', 'going', 'yes'}


def canonical_url(url):
    p = urlsplit(url)
    if p.scheme not in ('http', 'https') or not p.hostname or p.username or p.password:
        raise ValueError('Expected an HTTP(S) event URL without credentials')
    host = p.netloc.lower()
    path = p.path.rstrip('/') or '/'
    # Only known tracking parameters can be removed. Unknown query IDs are identities.
    from urllib.parse import parse_qsl, urlencode
    query = urlencode([(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
                       if not k.startswith('utm_') and not (p.hostname.lower() in ('partiful.com', 'www.partiful.com') and k in ('rsvp', 'source', 'c'))])
    return urlunsplit((p.scheme.lower(), host, path, query, '' if p.hostname.lower() in ('partiful.com', 'www.partiful.com') else p.fragment))


def start_epoch(value):
    """Offset-aware ISO start as an epoch; anything else is an unknown start."""
    try:
        dt = datetime.fromisoformat(value)
    except (TypeError, ValueError):
        return None
    return dt.timestamp() if dt.utcoffset() is not None else None


def started(metadata, now):
    """True only when the event's known start has passed; its spot can no longer be released."""
    start = start_epoch(metadata.get('start'))
    return start is not None and start <= now


class Store:
    def __init__(self, home=DEFAULT_HOME):
        self.home = Path(home).expanduser().resolve()
        self.home.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.db = sqlite3.connect(self.home / 'state.sqlite', timeout=10)
        os.chmod(self.home / 'state.sqlite', 0o600)
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
        PRAGMA foreign_keys=ON;
        CREATE TABLE IF NOT EXISTS campaigns (
          id TEXT PRIMARY KEY, account TEXT NOT NULL, config TEXT NOT NULL,
          active INTEGER NOT NULL DEFAULT 0, complete INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS facts (
          name TEXT PRIMARY KEY, value TEXT NOT NULL, source TEXT NOT NULL,
          updated REAL NOT NULL, expires REAL, share TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS fact_history (
          name TEXT, value TEXT, source TEXT, updated REAL, expires REAL, share TEXT);
        CREATE TABLE IF NOT EXISTS events (
          id TEXT PRIMARY KEY, account TEXT NOT NULL, url TEXT NOT NULL,
          metadata TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'discovered',
          evidence TEXT, decision TEXT NOT NULL DEFAULT 'Undecided', notes TEXT NOT NULL DEFAULT '',
          UNIQUE(account, url));
        CREATE TABLE IF NOT EXISTS members (
          campaign TEXT REFERENCES campaigns(id), event TEXT REFERENCES events(id),
          PRIMARY KEY(campaign,event));
        CREATE TABLE IF NOT EXISTS aliases (
          account TEXT, url TEXT, event TEXT REFERENCES events(id), PRIMARY KEY(account,url));
        CREATE TABLE IF NOT EXISTS attempts (
          id INTEGER PRIMARY KEY, event TEXT REFERENCES events(id), started REAL,
          finished REAL, outcome TEXT, evidence TEXT);
        CREATE TABLE IF NOT EXISTS cooldowns (
          account TEXT, service TEXT, until REAL NOT NULL, evidence TEXT NOT NULL,
          PRIMARY KEY(account,service));
        CREATE TABLE IF NOT EXISTS questions (
          id INTEGER PRIMARY KEY, event TEXT REFERENCES events(id), question TEXT,
          answer TEXT, source TEXT);
        CREATE TABLE IF NOT EXISTS sync (
          campaign TEXT, event TEXT REFERENCES events(id), pending INTEGER NOT NULL DEFAULT 1,
          evidence TEXT, PRIMARY KEY(campaign,event));
        CREATE TABLE IF NOT EXISTS assessments (
          campaign TEXT REFERENCES campaigns(id), event TEXT REFERENCES events(id),
          data TEXT NOT NULL, PRIMARY KEY(campaign,event));
        CREATE TABLE IF NOT EXISTS tracker_cells (
          path TEXT, event TEXT REFERENCES events(id), decision TEXT NOT NULL, pending TEXT,
          PRIMARY KEY(path,event));
        ''')
        if 'rsvp' not in {r['name'] for r in self.db.execute('PRAGMA table_info(events)')}:
            with self.transaction():
                self.db.execute('ALTER TABLE events ADD COLUMN rsvp TEXT')
                # Upcoming admissions recorded before the RSVP flow still need an attendance answer.
                now = time.time()
                for r in self.db.execute("SELECT id,metadata FROM events WHERE status IN ('going','approved')").fetchall():
                    if not started(json.loads(r['metadata']), now):
                        self.db.execute("UPDATE events SET rsvp='needs_rsvp' WHERE id=?", (r['id'],))
                # Re-export them so the tracker asks the user for the new decision.
                self.db.execute("INSERT OR REPLACE INTO sync(campaign,event,pending) SELECT m.campaign,m.event,1 FROM members m JOIN events e ON e.id=m.event WHERE e.rsvp='needs_rsvp'")

    @contextmanager
    def transaction(self):
        self.db.execute('BEGIN IMMEDIATE')
        try:
            yield
            self.db.commit()
        except BaseException:
            self.db.rollback()
            raise

    def campaign(self, name):
        row = self.db.execute('SELECT * FROM campaigns WHERE id=?', (name,)).fetchone()
        if not row:
            raise ValueError('Unknown campaign')
        return dict(row)

    def init(self, name, account, config):
        if not name or not account or not isinstance(config.get('sources'), list):
            raise ValueError('Campaign name, account and sources list required')
        with self.transaction():
            self.db.execute('INSERT INTO campaigns(id,account,config) VALUES(?,?,?)',
                            (name, account, json.dumps(config)))

    def authorize(self, campaign, evidence):
        if not evidence.strip():
            raise ValueError('Record user authorization and scope')
        with self.transaction():
            row = self.campaign(campaign)
            config = json.loads(row['config'])
            config['authorization'] = evidence
            self.db.execute('UPDATE campaigns SET active=1,config=? WHERE id=?',
                            (json.dumps(config), campaign))

    def fact(self, name, value, source, share='ask', expires=None):
        if share not in ('routine', 'ask', 'never') or not source.strip():
            raise ValueError('Fact needs provenance and sharing classification')
        values = (name, json.dumps(value), source, time.time(), expires, share)
        with self.transaction():
            self.db.execute('INSERT INTO fact_history VALUES(?,?,?,?,?,?)', values)
            self.db.execute('INSERT OR REPLACE INTO facts VALUES(?,?,?,?,?,?)', values)

    def profile(self, now=None):
        now = time.time() if now is None else now
        return [dict(r, value=json.loads(r['value']), stale=r['expires'] is not None and r['expires'] <= now)
                for r in self.db.execute('SELECT * FROM facts ORDER BY name')]

    def add(self, campaign, url, metadata):
        c = self.campaign(campaign)
        url = canonical_url(url)
        with self.transaction():
            alias = self.db.execute('SELECT event FROM aliases WHERE account=? AND url=?', (c['account'], url)).fetchone()
            eid = alias['event'] if alias else hashlib.sha256((c['account'] + '\n' + url).encode()).hexdigest()[:24]
            self.db.execute('INSERT OR IGNORE INTO events(id,account,url,metadata) VALUES(?,?,?,?)',
                            (eid, c['account'], url, json.dumps(metadata)))
            self.db.execute('INSERT OR IGNORE INTO members VALUES(?,?)', (campaign, eid))
            # A preexisting success in this account still needs exporting for this campaign.
            status = self.db.execute('SELECT status FROM events WHERE id=?', (eid,)).fetchone()['status']
            if status in TRACKED:
                self.db.execute('INSERT OR IGNORE INTO sync(campaign,event) VALUES(?,?)', (campaign, eid))
        return eid

    def event(self, eid):
        row = self.db.execute('SELECT * FROM events WHERE id=?', (eid,)).fetchone()
        if not row:
            raise ValueError('Unknown event')
        return dict(row, metadata=json.loads(row['metadata']))

    def alias(self, eid, url):
        e = self.event(eid)
        url = canonical_url(url)
        with self.transaction():
            other = self.db.execute('SELECT id FROM events WHERE account=? AND url=?', (e['account'], url)).fetchone()
            if other and other['id'] != eid:
                raise ValueError('Existing event: reconcile records before aliasing')
            self.db.execute('INSERT INTO aliases VALUES(?,?,?)', (e['account'], url, eid))

    def review(self, eid, status, evidence, metadata=None):
        if status not in ('ready', 'skipped', 'needs_input', 'closed') or not evidence.strip():
            raise ValueError('Review needs a supported status and evidence')
        with self.transaction():
            e = self.event(eid)
            if e['status'] in TRACKED or e['status'] == 'submitting':
                # A cancelled registration is never reapplied to automatically.
                raise ValueError('Do not overwrite a submission with review state')
            data = e['metadata']
            if metadata:
                data.update(metadata)
            if status == 'ready' and not (data.get('free') is True and data.get('eligible') is True and data.get('service')):
                raise ValueError('Ready requires verified free, eligible and service')
            self.db.execute('UPDATE events SET status=?,evidence=?,metadata=? WHERE id=?',
                            (status, evidence, json.dumps(data), eid))

    def gate(self, campaign, now=None):
        now = time.time() if now is None else now
        c = self.campaign(campaign)
        account = c['account']
        if c['complete']:
            # A finished campaign still follows through on RSVPs for registrations it holds.
            return self.rsvp_work(account, now, campaign) or {'action': 'idle', 'reason': 'complete'}
        if not c['active']:
            return {'action': 'idle', 'reason': 'draft_or_paused'}
        unknown = self.db.execute("SELECT id FROM events WHERE account=? AND status='submitting' LIMIT 1", (account,)).fetchone()
        if unknown:
            return {'action': 'reconcile', 'event': unknown['id']}
        work = self.rsvp_work(account, now)
        if work:
            return work
        prefs = json.loads(c['config']).get('preferences', {})
        unanswered = self.unanswered_rsvps(account, now)
        if len(unanswered) >= prefs.get('max_unanswered_rsvps', RSVP_LIMIT):
            # Quiet: the user was asked when each admission was recorded.
            return {'action': 'idle', 'reason': 'awaiting_rsvp', 'events': [eid for eid, _ in unanswered]}
        ready, deadlines, needs_review = [], [], False
        for r in self.db.execute('SELECT e.* FROM events e JOIN members m ON e.id=m.event WHERE m.campaign=? ORDER BY e.rowid', (campaign,)):
            if r['status'] == 'discovered':
                needs_review = True
            if r['status'] != 'ready':
                continue
            service = json.loads(r['metadata'])['service']
            hold = self.db.execute('SELECT until FROM cooldowns WHERE account=? AND service=?', (account, service)).fetchone()
            if hold and hold['until'] > now:
                deadlines.append(hold['until'])
            else:
                ready.append(r['id'])
        if ready:
            return {'action': 'apply', 'event': ready[0]}
        config = json.loads(c['config'])
        if needs_review or not config.get('discovery_complete', False):
            # Optional low-resource mode suppresses discovery while a known service is cooling down.
            holds = self.db.execute('SELECT until FROM cooldowns WHERE account=? AND until>?', (account, now)).fetchall()
            if not config.get('review_during_cooldown', True) and holds:
                deadlines.extend(h['until'] for h in holds)
            else:
                return {'action': 'review'}
        if deadlines:
            return {'action': 'wait', 'retry_at': min(deadlines)}
        return {'action': 'idle', 'reason': 'no_actionable_events'}

    def reserve(self, campaign, eid, now=None):
        now = time.time() if now is None else now
        with self.transaction():
            gate = self.gate(campaign, now)
            if gate != {'action': 'apply', 'event': eid}:
                raise ValueError('Submission blocked: ' + json.dumps(gate))
            self.db.execute("UPDATE events SET status='submitting' WHERE id=?", (eid,))
            return self.db.execute('INSERT INTO attempts(event,started) VALUES(?,?)', (eid, now)).lastrowid

    def result(self, eid, outcome, evidence, now=None, retry_after=None):
        now = time.time() if now is None else now
        if outcome not in OUTCOMES | {'rate_limited', 'not_submitted'} or not evidence.strip():
            raise ValueError('Explicit observed outcome and evidence required')
        with self.transaction():
            e = self.event(eid)
            if e['status'] != 'submitting':
                raise ValueError('No reserved/uncertain submission to reconcile')
            status = 'ready' if outcome in ('rate_limited', 'not_submitted') else outcome
            self.db.execute('UPDATE events SET status=?,evidence=? WHERE id=?', (status, evidence, eid))
            self.db.execute('UPDATE attempts SET finished=?,outcome=?,evidence=? WHERE event=? AND finished IS NULL',
                            (now, outcome, evidence, eid))
            service = e['metadata']['service']
            if outcome == 'rate_limited':
                # Retry-After is an absolute UTC epoch; never shorten a server deadline.
                if retry_after is not None and retry_after < now:
                    raise ValueError('Retry-After must be in the future')
                until = max(now + 1200, retry_after or 0)
                self.db.execute('''INSERT INTO cooldowns VALUES(?,?,?,?) ON CONFLICT(account,service)
                    DO UPDATE SET until=MAX(until,excluded.until),evidence=excluded.evidence''',
                    (e['account'], service, until, evidence))
            elif outcome in OUTCOMES:
                self.db.execute('DELETE FROM cooldowns WHERE account=? AND service=?', (e['account'], service))
                if outcome in ADMITTED and not started(e['metadata'], now):
                    self.db.execute("UPDATE events SET rsvp='needs_rsvp' WHERE id=? AND rsvp IS NULL", (eid,))
                self._resync(eid)

    def rsvp_work(self, account, now, campaign=None):
        """Tracker sync and RSVP follow-through, account-wide or for one finished campaign."""
        scope = None if campaign is None else {r['event'] for r in self.db.execute('SELECT event FROM members WHERE campaign=?', (campaign,))}
        for r in self.db.execute('SELECT sync.event,sync.campaign FROM sync JOIN campaigns c ON c.id=sync.campaign WHERE c.account=? AND sync.pending=1 ORDER BY sync.rowid', (account,)):
            if campaign is None or r['campaign'] == campaign:
                return {'action': 'sync', 'event': r['event'], 'campaign': r['campaign']}
        # Release spots the user will not use before taking any new ones.
        for r in self.db.execute("SELECT id,metadata FROM events WHERE account=? AND rsvp='cancel_pending' AND status IN ('pending','waitlisted','going','approved') ORDER BY rowid", (account,)):
            if (scope is None or r['id'] in scope) and not started(json.loads(r['metadata']), now):
                return {'action': 'cancel', 'event': r['id'], 'reason': 'not_attending'}
        # The deadline only prompts a live tracker check; cancelling still needs a not_attending RSVP.
        for eid, _ in self.deadline_releases(account, now):
            if scope is None or eid in scope:
                # The user may have answered in any campaign's tracker; every one must be read.
                holders = [r['campaign'] for r in self.db.execute('SELECT campaign FROM members WHERE event=? ORDER BY campaign', (eid,))]
                return {'action': 'rsvp_deadline', 'event': eid, 'campaigns': holders}
        return None

    def unanswered_rsvps(self, account, now):
        """Admitted upcoming events whose attendance the user has not confirmed."""
        out = []
        for r in self.db.execute("SELECT id,metadata FROM events WHERE account=? AND rsvp='needs_rsvp' ORDER BY rowid", (account,)):
            start = start_epoch(json.loads(r['metadata']).get('start'))
            if start is None or start > now:
                out.append((r['id'], start))
        return out

    def admission(self, eid, outcome, evidence, now=None):
        """Record a later organizer decision on a pending or waitlisted request."""
        now = time.time() if now is None else now
        if outcome not in OUTCOMES or not evidence.strip():
            raise ValueError('Explicit observed outcome and evidence required')
        with self.transaction():
            e = self.event(eid)
            if e['status'] not in ('pending', 'waitlisted') or e['rsvp'] == 'cancelled':
                raise ValueError('Only an open pending or waitlisted request can change admission')
            rsvp = e['rsvp']
            if outcome in ADMITTED and rsvp is None and not started(e['metadata'], now):
                rsvp = 'needs_rsvp'
            elif outcome not in HELD:
                rsvp = None  # The organizer closed the request; there is no spot left to release.
            self.db.execute('UPDATE events SET status=?,evidence=?,rsvp=? WHERE id=?', (outcome, evidence, rsvp, eid))
            self._resync(eid)

    def rsvp(self, eid, intent, evidence, now=None):
        """Record the user's own attendance answer. not_attending queues an automatic release."""
        now = time.time() if now is None else now
        if intent not in ('attending', 'not_attending') or not evidence.strip():
            raise ValueError('RSVP needs attending or not_attending and the user\'s answer as evidence')
        with self.transaction():
            e = self.event(eid)
            if e['status'] not in HELD or e['rsvp'] == 'cancelled':
                raise ValueError('RSVP applies only to a registration the user still holds')
            if started(e['metadata'], now):
                raise ValueError('The event has started; there is no spot left to release')
            rsvp, decision = ('attending', ATTEND_DECISION) if intent == 'attending' else ('cancel_pending', DECLINE_DECISION)
            notes = (e['notes'] + '\n' if e['notes'] else '') + 'RSVP: ' + evidence
            self.db.execute('UPDATE events SET rsvp=?,decision=?,notes=? WHERE id=?', (rsvp, decision, notes, eid))
            self._resync(eid)

    def cancelled(self, eid, evidence):
        """Record an observed cancellation of a registration the user will not attend."""
        if not evidence.strip():
            raise ValueError('Visible cancellation evidence required')
        with self.transaction():
            e = self.event(eid)
            if e['rsvp'] != 'cancel_pending':
                raise ValueError('Cancel only after a recorded not_attending RSVP')
            self.db.execute("UPDATE events SET status='cancelled',rsvp='cancelled',decision=?,evidence=? WHERE id=?",
                            (DECLINE_DECISION, evidence, eid))
            self._resync(eid)

    def deadline_releases(self, account, now):
        """Unanswered admissions inside an RSVP deadline the user opted into for an authorized campaign."""
        out = []
        for eid, start in self.unanswered_rsvps(account, now):
            configs = [json.loads(r['config']) for r in self.db.execute(
                'SELECT c.config FROM campaigns c JOIN members m ON m.campaign=c.id WHERE m.event=?', (eid,))]
            # Opt-in only: silence counts as not attending only where the user set a deadline
            # in an authorized campaign. Application consent alone never covers cancellation.
            hours = [h for c in configs if c.get('authorization')
                     for h in [c.get('preferences', {}).get('rsvp_deadline_hours')]
                     if type(h) in (int, float) and h > 0]
            if start is not None and hours and start - max(hours) * 3600 <= now:
                out.append((eid, start))
        return out

    def _resync(self, eid):
        self.db.execute('INSERT OR REPLACE INTO sync(campaign,event,pending) SELECT campaign,event,1 FROM members WHERE event=?', (eid,))

    def ack(self, campaign, eid, evidence):
        if not evidence.strip():
            raise ValueError('Tracker read-back evidence required')
        with self.transaction():
            self.db.execute('UPDATE sync SET pending=0,evidence=? WHERE campaign=? AND event=?', (evidence, campaign, eid))

    def listing(self, campaign):
        self.campaign(campaign)
        return [self.event(r['event']) for r in self.db.execute('SELECT event FROM members WHERE campaign=?', (campaign,))]

    def question(self, eid, text):
        self.event(eid)
        with self.transaction():
            return self.db.execute('INSERT INTO questions(event,question) VALUES(?,?)', (eid, text)).lastrowid

    def answer(self, qid, answer, source):
        if not source.strip():
            raise ValueError('Answer provenance required')
        with self.transaction():
            row = self.db.execute('SELECT * FROM questions WHERE id=?', (qid,)).fetchone()
            if not row:
                raise ValueError('Unknown question')
            self.db.execute('UPDATE questions SET answer=?,source=? WHERE id=?', (answer, source, qid))
        # Does not make the event ready or promote an event-specific answer into a global fact.

    def configure(self, campaign, changes):
        allowed = {'discovery_complete', 'review_during_cooldown', 'tracker', 'sources', 'preferences'}
        if set(changes) - allowed:
            raise ValueError('Unknown or protected configuration fields')
        with self.transaction():
            c = self.campaign(campaign)
            config = json.loads(c['config'])
            config.update(changes)
            self.db.execute('UPDATE campaigns SET config=? WHERE id=?', (json.dumps(config), campaign))

    def finish(self, campaign):
        with self.transaction():
            c = self.campaign(campaign)
            if not json.loads(c['config']).get('discovery_complete'):
                raise ValueError('Discovery not complete')
            if any(e['status'] in ('discovered', 'ready', 'submitting', 'needs_input') for e in self.listing(campaign)):
                raise ValueError('Unresolved events remain')
            events = self.listing(campaign)
            now = time.time()
            if any(e['rsvp'] == 'cancel_pending' and not started(e['metadata'], now) for e in events):
                raise ValueError('Cancellations the user requested remain')
            mine = {e['id'] for e in events}
            if any(eid in mine for eid, _ in self.unanswered_rsvps(c['account'], now)):
                raise ValueError('Upcoming admissions still need an RSVP')
            if self.db.execute('SELECT 1 FROM sync WHERE campaign=? AND pending=1', (campaign,)).fetchone():
                raise ValueError('Tracker sync pending')
            self.db.execute('UPDATE campaigns SET complete=1,active=0 WHERE id=?', (campaign,))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--home', type=Path, default=DEFAULT_HOME)
    p.add_argument('command', choices=['init','authorize','profile','fact','add','alias','review','gate','reserve','result','ack','list','question','answer','configure','finish','pause','admission','rsvp','cancelled'])
    p.add_argument('--campaign'); p.add_argument('--account'); p.add_argument('--event'); p.add_argument('--url')
    p.add_argument('--json', default='{}', help='JSON data, or @path for a private JSON file')
    a = p.parse_args()
    data = json.loads(Path(a.json[1:]).read_text() if a.json.startswith('@') else a.json)
    s = Store(a.home)
    cmd = a.command
    if cmd == 'init': out = s.init(a.campaign, a.account, data)
    elif cmd == 'authorize': out = s.authorize(a.campaign, data['evidence'])
    elif cmd == 'profile': out = s.profile()
    elif cmd == 'fact': out = s.fact(**data)
    elif cmd == 'add': out = s.add(a.campaign, a.url, data)
    elif cmd == 'alias': out = s.alias(a.event, a.url)
    elif cmd == 'review': out = s.review(a.event, **data)
    elif cmd == 'gate': out = s.gate(a.campaign)
    elif cmd == 'reserve': out = s.reserve(a.campaign, a.event)
    elif cmd == 'result': out = s.result(a.event, **data)
    elif cmd == 'ack': out = s.ack(a.campaign, a.event, data['evidence'])
    elif cmd == 'list': out = s.listing(a.campaign)
    elif cmd == 'question': out = s.question(a.event, data['question'])
    elif cmd == 'answer': out = s.answer(**data)
    elif cmd == 'configure': out = s.configure(a.campaign, data)
    elif cmd == 'finish': out = s.finish(a.campaign)
    elif cmd == 'admission': out = s.admission(a.event, **data)
    elif cmd == 'rsvp': out = s.rsvp(a.event, **data)
    elif cmd == 'cancelled': out = s.cancelled(a.event, data['evidence'])
    elif cmd == 'pause':
        s.campaign(a.campaign)
        with s.transaction(): s.db.execute('UPDATE campaigns SET active=0 WHERE id=?', (a.campaign,))
        out = None
    print(json.dumps(out if out is not None else {'ok': True}, indent=2))

if __name__ == '__main__':
    main()
