# Private state and commands

All commands accept --home /absolute/private/state (default ~/.local/share/eventmaxxer).
SQLite stores facts/history, campaigns, events, URL aliases, attempts, questions, service
cooldowns and tracker sync. Use one home across campaigns on the same registration account.
The scripts do not navigate sites, send applications, interpret eligibility or grant consent.

Use --json @/absolute/private/input.json for longer data; never interpolate untrusted
form text into shell commands. Every mutation is transactional. A new init never overwrites
an existing campaign.

    python3 scripts/state.py init --campaign conference --account primary --json '{"sources":[],"discovery_complete":false,"review_during_cooldown":false,"preferences":{"goal":"Meet people building community projects","location":"San Francisco","date_scope":"October 2026","free_only":true,"allow_overlaps":true,"product_marketing":false}}'
    python3 scripts/state.py authorize --campaign conference --json '{"evidence":"User authorized free eligible networking applications on YYYY-MM-DD; no purchases or new accounts."}'
    python3 scripts/state.py fact --json '{"name":"job_title","value":"Founder","source":"User on YYYY-MM-DD","share":"routine"}'
    python3 scripts/state.py profile
    python3 scripts/state.py add --campaign conference --url https://events.example.org/one --json '{"title":"Founder Meetup","service":"events.example.org"}'

An empty sources list starts goal-driven web discovery. Save discovered source URLs with
configure, keeping the goal and constraints in preferences. Supplied websites can also
be used as the initial sources. No event category is excluded by default.

The add command returns the stable event ID. Save that ID and use it for later operations.
Known tracking query keys are stripped; other query parameters are preserved. Use alias
only after evidence establishes that another registration URL is the same event.

    python3 scripts/state.py review --event EVENT_ID --json '{"status":"ready","evidence":"Page explicitly free and open to founders","metadata":{"free":true,"eligible":true,"service":"events.example.org","start":"2026-10-07T17:30:00-07:00","end":"2026-10-07T20:30:00-07:00","offers":"Talks and networking","fit":"Meet founders","location":"Published venue","hosts":"Published host"}}'
    python3 scripts/state.py gate --campaign conference
    python3 scripts/state.py reserve --campaign conference --event EVENT_ID

Only reserve when the form is ready for its final submission. Complete that action with
the agent's supported browser. Then use one observed result:

    python3 scripts/state.py result --event EVENT_ID --json '{"outcome":"pending","evidence":"Visible confirmation: request sent; awaiting approval"}'
    python3 scripts/state.py ack --campaign conference --event EVENT_ID --json '{"evidence":"Read back matching event key and Pending row from tracker"}'

Rate-limit result instead: outcome rate_limited, evidence, optional retry_after absolute
UTC epoch. Without an explicit deadline, the script uses 20 minutes. Unknown result:
leave submitting; gate returns reconcile until actual state is established. not_submitted
requires evidence that it did not submit, not just lack of a confirmation.

Admission and RSVP:

    python3 scripts/state.py admission --event EVENT_ID --json '{"outcome":"approved","evidence":"Approval email for the matching event"}'
    python3 scripts/state.py rsvp --event EVENT_ID --json '{"intent":"attending","evidence":"User on YYYY-MM-DD: will attend"}'
    python3 scripts/state.py rsvp --event EVENT_ID --json '{"intent":"not_attending","evidence":"User on YYYY-MM-DD: cannot attend"}'
    python3 scripts/state.py cancelled --event EVENT_ID --json '{"evidence":"Visible confirmation: registration cancelled"}'

admission records a later organizer decision on a pending or waitlisted request. Going or
approved sets rsvp to needs_rsvp. rsvp records only the user's answer and can also withdraw
a pending or waitlisted request. not_attending sets cancel_pending; gate then returns
{"action":"cancel"} before any new application, as it does for an unanswered admission
inside preferences.rsvp_deadline_hours (default 24) of its start. Record cancelled only from
visible evidence; status becomes cancelled and the event cannot be reviewed again. With
preferences.max_unanswered_rsvps (default 3) upcoming admissions unanswered, gate returns
idle/awaiting_rsvp. Existing databases migrate admitted events to needs_rsvp and queue tracker sync on first open.
finish refuses while upcoming admissions are unanswered or cancellations are queued.

Missing facts:

    python3 scripts/state.py question --event EVENT_ID --json '{"question":"Exact required question and choices"}'
    python3 scripts/state.py review --event EVENT_ID --json '{"status":"needs_input","evidence":"Required factual answer missing"}'
    python3 scripts/state.py answer --json '{"qid":1,"answer":"User answer","source":"User on YYYY-MM-DD"}'

Answer does not auto-promote a fact or make the event ready. Read open questions from the
private SQLite database as needed, or maintain the user-facing question list in checkpoint.md.
A facts entry has share routine/ask/never, source, updated timestamp, optional expires epoch,
and a complete version history. Stale values are flagged by profile; they are not safe to
reuse silently. Runtime approval rules always apply.

Use configure for sources, tracker, preferences, discovery_complete and review_during_cooldown.
Use list for all campaign records, pause to deactivate, authorize to resume within scope,
and finish after source coverage and unresolved/sync queues have been checked. Date metadata
uses offset-aware ISO timestamps; exports select the user's requested timezone.

Discovery checkpoints (private Markdown beside the database) hold the scoped search plan,
queries and their coverage, discovered source URLs, pagination
and filter cursor, observed counts, pending source questions and last verified source pass.
Mark discovery_complete only after completing the scoped search plan and exhausting all
selected sources; this does not mean the entire web has been searched. Reopen it when the
user adds a new source or explicitly requests a fresh scan.
