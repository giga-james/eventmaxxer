# Eventmaxxer

**An agent distro that finds events, completes applications, and keeps your options organized.**

Open this repo in Codex, Claude Code, or another agent with computer-use tools and say:

> Find events where I can meet founders, investors and potential customers. Apply to
> eligible free events, skip hackathons, and keep a tracker sorted by day and time.

Or, from another workspace, tell your agent to read this clone's **EVENTMAXXER.md**.
The agent handles setup and asks only for missing information.

An agent distro is a portable bundle of instructions, skills, scripts and state conventions.
Your chosen agent supplies the model, browser and connected tools. Eventmaxxer supplies
the event workflow and reliable local state. Inspired by
[Continual Outreach](https://github.com/giga-james/continual-outreach).

## Three core features

1. **A maintained applicant profile.** Reuse verified professional facts, preserve their
   source and history, flag stale facts, and ask missing questions individually. Keep
   event-specific answers and consent separate from reusable facts.
2. **Computer-use applications across event sites.** Review calendars and registration
   pages using the current agent's browser tools. Check cost and eligibility, deduplicate
   alternate links, complete forms and verify the actual result.
3. **Wakeups after rate limits.** A tiny Python process checks local deadlines without
   calling a model or opening a browser. Once due, it invokes the configured agent for
   one real retry. Successful submissions resume continuous work; another limit saves a
   new deadline and closes the tab.

The local runner does **not** ping private RSVP endpoints. Only a real submission can
establish that a submission limit cleared. Default retry spacing is 20 minutes, or longer
when the service specifies a later Retry-After.

## What stays reliable

- SQLite transactions and durable submission reservations prevent simultaneous local
  submissions and accidental retries after an ambiguous result.
- Account-wide URL identities and explicit aliases prevent duplicate applications across
  campaigns sharing the same state home.
- Cooldowns are scoped by account and registration service.
- One application at a time, maximum three event tabs, and no live-tab backlog.
- Verified applications must be synced before the next submission.
- CSV exports preserve attendance decisions and notes, and sort by local date/time.
  Google Sheets is supported through the agent's connector workflow.
- Pending, waitlisted and admitted are different outcomes.

## Start

Requires Python 3.9+ on macOS/Linux for the optional local runner; no third-party Python
packages are needed. The agent runtime must provide an authenticated supported browser.
Spreadsheet integration additionally requires a Sheets connector.

No personal data ships in this repository. State defaults to
~/.local/share/eventmaxxer/ and should be backed up privately. The same profile and
account labels should be reused when switching agents or campaigns.

New campaigns begin in draft mode. Tell the agent the sources, goals, constraints and
permission to apply; it saves the configuration and profile. Existing authorization
carries forward within scope.

> Keep this running and resume after rate limits. Set up the scheduler for me.

The agent discovers its runtime, probes scheduled tool access, and installs one suitable
scheduler. A desktop heartbeat is a fallback where CLI browser access is unavailable;
unlike the local gate, a heartbeat already invokes the model. Neither scheduler is
installed merely by cloning this repo.

## Architecture

User goals + profile → computer-use discovery → eligibility review → reserved application
→ visible confirmation → verified tracker → next event.

When limited: save deadline → close tabs → cheap local checks → one due retry.

| File | Purpose |
| --- | --- |
| EVENTMAXXER.md | Portable conversational entrypoint |
| .agents/skills/eventmaxxer/SKILL.md | Application workflow |
| scripts/state.py | Profile, events, questions, reservations, cooldowns, sync gates |
| scripts/wake.py | Zero-model cooldown checks and serialized agent invocation |
| scripts/export.py | Verified CSV export with preserved user choices |
| docs/scheduling.md | Agent-managed scheduler setup |
| docs/state.md | State and command reference |
| docs/tracking.md | Sheet sync and legacy campaign migration |

## Validation

Run:

    python3 -m unittest discover -s tests -v

Tests use temporary state and fake agents, with no live RSVP requests.

This is an initial implementation. Generic computer use supports reviewing arbitrary
sites, but cannot guarantee access, eligibility or automatic completion of every form.
Tool access in a scheduled CLI can differ from the desktop. Local locks do not coordinate
different machines/state homes. Do not run two schedulers against the same account.
