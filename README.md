# Eventmaxxer

<p align="center">
  <a href="#architecture"><img src="https://img.shields.io/badge/Agent-Distro-6366f1" alt="Agent Distro"></a>
  <a href="#start"><img src="https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&amp;logoColor=white" alt="Python 3.9+"></a>
  <a href="#start"><img src="https://img.shields.io/badge/Runner-macOS%20%7C%20Linux-555555" alt="Runner: macOS or Linux"></a>
  <a href="#core-features"><img src="https://img.shields.io/badge/Events-Any%20type-0d9488" alt="Events: any type"></a>
  <a href="#start"><img src="https://img.shields.io/badge/Auto%20registration-Free%20events-2563eb" alt="Automatic registration: free events"></a>
  <a href="#validation"><img src="https://img.shields.io/badge/Status-Experimental-f4a7c3" alt="Status: experimental"></a>
</p>

https://github.com/user-attachments/assets/1c31d9b3-0cf7-4643-a9a0-9776463e8cca

<p align="center"><sub>left to go watch jojo's, but we keep eventmaxxing</sub></p>

**Give your agent an event goal. It finds matching events and applies in bulk.**

Meetups, conferences, workshops, dinners, hackathons—any event type. Start with a goal,
a website, or both. Your agent handles discovery and applications, then keeps a
spreadsheet so you can review your options and decide what to attend later.

## Start

Open this repo in an agent with computer-use tools and say:

> Help me find events that match my goals. Apply to eligible free events and keep a
> spreadsheet so I can review them and decide which to attend later.

Tell it your interests, location and dates—or let it ask for the missing details.
You can also supply specific websites to scan.

Working elsewhere? Ask your agent to read [EVENTMAXXER.md](EVENTMAXXER.md).
It reuses your profile and asks only for missing details. To enable automatic resume, add:

> Keep this running and resume after rate limits. Set up the scheduler for me.

**Requires:** an authenticated browser supported by your agent. The optional local runner
uses Python 3.9+ on macOS/Linux; Google Sheets needs a connector.

## Results

An event calendar full of options:

<p align="center">
  <img src="assets/eventmaxxer-outcome.png" width="100%" alt="Event dashboard welcoming James and showing 621 upcoming events.">
</p>

## Core features

| | What it does |
| --- | --- |
| 👤 **Reusable profile** | Saves verified facts so you do not repeat the same answers. |
| 🌐 **Discover and apply** | Searches websites, checks fit and eligibility, and applies to matching free events. |
| 📊 **Review and decide later** | Keeps Google Sheets or a CSV sorted by date, with event details, registration status, your attendance decisions and notes. |
| 🎯 **Prioritize attendance** | Builds an evidence-backed shortlist around the people you want to meet, with confidence, conversation plans and known overlaps. |
| ⏱ **Resume automatically** | Saves cooldowns and wakes the agent when it can retry. |

## Architecture

Each **campaign** has a goal and scope, its own tracker, and recommendations built on
that tracker. The agent builds a broad set of event options, then helps you choose where
to spend your time. Local helpers preserve state and coordinate retries.

![Eventmaxxer layered architecture: human campaign goals guide agent discovery, qualification, application and verification into a tracker. Agent assessments feed deterministic ranking rules and an attendance shortlist. Human feedback returns to the tracker. Private storage and recovery software support all campaigns.](assets/architecture.svg)

The diagram separates **agent judgments**, **deterministic software**, **stored data** and
**human decisions**. Recommendations combine agent-researched assessments with heuristic
scoring and filtering; there is no trained ML ranking model. Attendance feedback informs
future assessments rather than automatically training a model.

- **Ask when needed:** missing answers return to you. The agent saves confirmed reusable facts
  to your profile and re-reviews the event; event-specific answers stay with that event.
- **Apply once:** deduplicate events, reserve each submission, and reconcile uncertain results.
- **Keep options reviewable:** sync verified results to the spreadsheet, preserving your
  decisions and notes. Pending, waitlisted and admitted stay distinct.
- **Recommend within the campaign:** rank tracker options against the people you want to
  meet, explain the evidence and uncertainties, and build a shortlist within your capacity.
- **Learn from attendance:** use your decisions and feedback about useful conversations
  to improve later recommendations.
- **Resume cheaply:** the optional local runner waits without model calls. A desktop heartbeat
  is an alternative when CLI browser access is unavailable and does invoke the model.

Profiles and campaign records stay in `~/.local/share/eventmaxxer/`, outside the repo.
Use one scheduler per account; local locks do not coordinate separate machines.
Sites may still require missing answers, login or manual steps.

[Agent workflow](.agents/skills/eventmaxxer/SKILL.md) ·
[State & commands](docs/state.md) · [Scheduling](docs/scheduling.md) ·
[Tracking & exports](docs/tracking.md)

## Choose what to attend

Ask your agent to prioritize the tracker around the people you need to meet and the
outcome you want. It assesses audience fit and opportunities for conversation, explains
each recommendation, and keeps unconfirmed admission separate. Tell it how many events
you have capacity for. Your decisions and notes remain yours.

See [Attendance recommendations](docs/recommendations.md). The local helper ranks
agent-researched assessments; it does not infer attendees from event titles or fetch
guest lists. Google Sheets updates use the agent's supported connector.

## Validation

```sh
python3 -m unittest discover -s tests -v
```

Tests use temporary state and fake agents, with no live applications.

## Contributing

See the [contributing guide](CONTRIBUTING.md) for setup, project rules and pull requests.

Inspired by [Continual Outreach](https://github.com/giga-james/continual-outreach).
