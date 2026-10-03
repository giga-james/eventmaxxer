# Contributing

Help improve discovery, application reliability, tracking or documentation for any event
type. Keep changes portable across agents and instructions short enough to follow.

## Get started

Fork and clone the repository, then create a branch for your change. Use Python 3.9+
on macOS or Linux; the local helpers and tests need no third-party packages.

Read [AGENTS.md](AGENTS.md) for project rules and [README.md](README.md#architecture)
for the architecture. Development does not require a browser login or a live campaign.

```sh
python3 -m unittest discover -s tests -v
```

## Where to make changes

| Area | Files |
| --- | --- |
| Onboarding and application workflow | [EVENTMAXXER.md](EVENTMAXXER.md), [eventmaxxer skill](.agents/skills/eventmaxxer/SKILL.md) |
| Private state and submission gates | [scripts/state.py](scripts/state.py) |
| Scheduled recovery | [scripts/wake.py](scripts/wake.py) |
| CSV exports | [scripts/export.py](scripts/export.py) |
| Regression tests | [tests/test_workflow.py](tests/test_workflow.py) |
| Operational references | [State](docs/state.md), [scheduling](docs/scheduling.md), [tracking](docs/tracking.md) |

## Keep these guarantees

- **Private data stays private.** Use fictional examples and temporary test state. Never
  commit profiles, registration answers, application history, logs, credentials or tracker IDs.
  Never point tests at an existing campaign.
- **Applications use supported computer use.** No hidden RSVP APIs, credential extraction,
  detection evasion or headless application scripts. Never submit real applications to test code.
- **Submissions remain accountable.** Preserve authorization checks, duplicate protection,
  durable reservations, outcome verification and tracker sync. Reconcile uncertain results
  before retrying; keep pending, waitlisted and admitted distinct.
- **Recovery respects existing work.** Preserve campaigns, cooldowns and schedulers.
  A schedule grants no new authority; do not install a second scheduler for the same account.

## Send a pull request

Keep each PR focused. Describe the problem, resulting behavior and validation performed.
For behavior changes, add regression coverage using temporary state and fake agent processes.
Update the relevant instructions when the workflow changes.

Before submitting, run the test command above and `git diff --check`. Review the diff for
private data and unrelated files. For documentation changes, check links and diagram rendering.

For bug reports, include expected behavior, actual behavior and reproducible steps with
fictional data. Share sanitized errors rather than raw campaign files or logs.
