# Scheduling and recovery

The agent owns setup. Reuse the current campaign's scheduler rather than creating a second
one. Ask for cadence or missing access, not routine configuration. No private network
polling: cooldown checks only read local state; the agent performs one due submission.

## Local gate: no model tokens while waiting

Discover the user's chosen agent executable and inspect its installed help for
noninteractive prompt input. Do not guess command flags, switch agents, disable approvals
or assume the CLI inherits desktop browser access. Create a private runner.json:

    {
      "state_home": "/absolute/private/state",
      "campaign": "conference",
      "workspace": "/absolute/workspace",
      "argv": ["/absolute/discovered-agent", "documented-arguments"],
      "timeout_seconds": 1800,
      "capability_probe_verified": false
    }

The runner sends a prompt on stdin; argv can contain {prompt_file} for runtimes that
accept a file. Commands execute without a shell. Use the same private state home for all
campaigns on an account. Never put credentials in argv or this config.

Before setting capability_probe_verified to true, run the exact agent command under the
intended scheduler environment with a read-only probe. Verify private state access,
supported computer-use browser access, authenticated account identity and tracker read
access. Do not make applications or live sheet edits during the probe. Record evidence
in the private checkpoint. An exit code is not a capability test.

Once verified, install the platform's supported scheduler to call:

    /absolute/python3 /absolute/eventmaxxer/scripts/wake.py --config /absolute/private/runner.json

A one-minute scheduler tick is cheap: while waiting, the Python process reads SQLite and
exits without invoking the agent or browser. It therefore avoids missing a retry deadline
by an entire 20-minute tick. Do not use an always-running browser or model-based polling.
For cron/launchd use correct platform quoting, preserve unrelated jobs, and verify the
installed job, environment and next run. Only one scheduler per account.

The runner holds an account lock during the agent process, saves private prompt/output
logs, and kills the process group on timeout. A failed or interrupted run leaves a .hold
file. Inspect its logs and reconcile any submitting records before manually removing the
specific hold. Do not automatically loop on failed agent invocations. A successful process
exit says nothing about application success; the ledger must contain UI evidence.

## Desktop heartbeat fallback

If only the current app has browser tools, use its supported automation API. Save campaign
ID and state home in the prompt. On wake, run gate first. Wait/idle means quiet exit with
no browser work. Apply means one reserved application, verify, sync, and continue until
blocked. Reconcile means inspect the existing uncertain attempt before applying again.
Sync means repair the tracker first. Cancel means release that registration on the event
site, verify it and record cancelled before applying. Rsvp_deadline means refresh the live
tracker before recording the user's answer or a deadline not_attending. Idle/awaiting_rsvp is quiet; the user
was already asked for those RSVPs.

This fallback consumes a model turn per wake; be explicit about that limitation. Do not
claim the local gate is installed or token-free if using an app heartbeat.

## Rate limits

Only an observed submission failure establishes a rate limit. Record outcome rate_limited,
exact evidence and any server Retry-After as an absolute UTC epoch. The gate uses the later
of that deadline and 20 minutes after failure. It gates all campaigns sharing the same
account and service. Once due, a single reservation allows one submission. Another failure
sets a new deadline. A successful verified submission clears the cooldown.

There is no exponential backoff by default. Do not shorten server deadlines, rotate
accounts, bypass restrictions or treat a successful page load as submission permission.
Configure review_during_cooldown=false for minimal-memory mode. Unaffected ready services
can still proceed; discovering new pages during a service hold follows campaign policy.

When all source coverage, applications and sync are resolved, use finish and disable the
existing scheduler through its supported interface. Unanswered questions are not completion.
