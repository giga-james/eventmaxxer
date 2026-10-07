# Track applications for attendance decisions

For each verified application, keep canonical event key, title, local date/day/start/end,
timezone, hosts, location, source link, actual application status, source-grounded offer,
inferred networking fit, verification evidence, user decision and user attendance notes.
Unknown end/venue stays unknown. Multi-day end dates remain explicit. Do not imply named
investors or customers are guaranteed attendees.

The decision column carries the RSVP: RSVP needed, Attend or Not attending, and status
becomes cancelled after a release. The CSV export first reads decisions the user changed
since its last write: Attend, Attending, Going or Yes confirms (and reverses a cancellation
not yet performed); Skip, Decline, Declined, Not attending or No queues an automatic
cancellation. An unchanged cell never overrides a newer RSVP recorded in chat. For Google Sheets the agent reads that column and records rsvp.

For attendance prioritization, use [recommendations.md](recommendations.md). Recommendation
and registration status are separate fields. CSV exports opt into recommendation columns
with `--recommendations --limit 3`; later exports retain and refresh those columns.
An original-schema CSV upgrades without losing decisions or notes. Other schemas still
require reconciliation rather than overwriting.

## CSV

Configure tracker as {"kind":"csv","path":"/absolute/private/applications.csv"}.
Run scripts/export.py --home PRIVATE_HOME --campaign CAMPAIGN --output ABSOLUTE_CSV.
It writes atomically, sorts by date/start, preserves existing decision/notes by stable
event key, reads back the file, and acknowledges sync only for that configured CSV.
A malformed or duplicate-key existing file fails instead of overwriting user decisions.

## Google Sheets

Use the runtime's Sheets skill and connector. Configure tracker with destination and schema
in private state. Read live metadata, canonical keys and user-owned fields before writing.
Upsert one event by canonical identity, never replace/import the workbook. Preserve user
decision and personal notes. Write numeric date/time cells in the intended timezone, extend
the table if needed, and sort complete rows by date/start. Update the count and read back
the key/status/row before ack. Pending and waitlisted are never accepted/approved.
On failure leave sync pending; fix it before another application. Connector setup is owned
by the agent; do not pretend this repo includes a standalone Google authentication client.

## Existing campaigns

Do not restart an existing event campaign or blindly parse a historical narrative into
successful applications. Preserve its original profile, ledger, tracker and scheduler.

1. Inventory verified canonical event keys and statuses from the live tracker and ledger.
2. Import facts with their original provenance and sharing boundaries. Keep expired facts
   and per-event consent scoped, not broadly reusable.
3. Reconcile every existing registration and alias before enabling new submissions.
   Use reserve/result only after documenting the existing observed outcome; draft mode
   may need a separate migration script for a large historical import. Do not bypass gates
   or mark failed/prepared forms as successful.
4. Preserve pending questions, source cursors, actual retry deadline, count distinction
   between new and preexisting registrations, and any unknown results.
5. Compare counts and canonical identities with the source. Preserve user decisions/notes.
6. Only then switch the existing scheduler to the new state; never run both.

This first release does not automatically migrate legacy Markdown ledgers. Until a tested
migration is performed, an existing live campaign continues using its original ledger and
automation. Installing the distro alone must not submit duplicates or reset cooldowns.
