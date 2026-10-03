# Eventmaxxer

<p align="center">
  <a href="#architecture"><img src="https://img.shields.io/badge/Agent-Distro-6366f1" alt="Agent Distro"></a>
  <a href="#start"><img src="https://img.shields.io/badge/Python-3.9%2B-3776AB?logo=python&amp;logoColor=white" alt="Python 3.9+"></a>
  <a href="#start"><img src="https://img.shields.io/badge/Runner-macOS%20%7C%20Linux-555555" alt="Runner: macOS or Linux"></a>
  <a href="#three-core-features"><img src="https://img.shields.io/badge/Events-Any%20type-0d9488" alt="Events: any type"></a>
  <a href="#start"><img src="https://img.shields.io/badge/Auto%20registration-Free%20events-2563eb" alt="Automatic registration: free events"></a>
  <a href="#validation"><img src="https://img.shields.io/badge/Status-Experimental-f4a7c3" alt="Status: experimental"></a>
</p>

https://github.com/user-attachments/assets/1c31d9b3-0cf7-4643-a9a0-9776463e8cca

<p align="center"><sub>45 minutes of me afk sped up 10x</sub></p>

**Give your agent an event goal. It finds matching events and applies in bulk.**

Meetups, conferences, workshops, dinners, hackathons—any event type. Start with a goal,
a website, or both. Your agent handles discovery, applications and tracking.

## Start

Open this repo in an agent with computer-use tools and say:

> Find robotics events in San Francisco next month. Apply to every eligible free event
> and track the results by date.

Working elsewhere? Ask your agent to read [EVENTMAXXER.md](EVENTMAXXER.md).
It reuses your profile and asks only for missing details. To enable automatic resume, add:

> Keep this running and resume after rate limits. Set up the scheduler for me.

**Requires:** an authenticated browser supported by your agent. The optional local runner
uses Python 3.9+ on macOS/Linux; Google Sheets needs a connector.

## Results

An event calendar full of options:

<p align="center">
  <img src="assets/eventmaxxer-outcome.png" width="100%" alt="Event dashboard welcoming James and showing 564 upcoming events.">
  <br><sub>left to go watch jojo's, but we keep eventmaxxing</sub>
</p>

## Three core features

| | What it does |
| --- | --- |
| 👤 **Reusable profile** | Saves verified facts so you do not repeat the same answers. |
| 🌐 **Discover and apply** | Searches websites, checks fit and eligibility, and applies to matching free events. |
| ⏱ **Resume automatically** | Saves cooldowns and wakes the agent when it can retry. |

## Architecture

Your agent operates the browser. Local helpers preserve state and coordinate retries.
**🤖 = agent-controlled step · ⚙ = local helper · 👤 = you**

```mermaid
flowchart TB
    Goal("👤 Set your goal<br/>Scope + permission")

    subgraph Agent["AGENT · browser + connected tools"]
        direction LR
        Find("🤖 Discover<br/>Search + scan") --> Qualify("🤖 Qualify<br/>Fit + eligibility")
        Qualify --> Apply("🤖 Apply<br/>Fill + submit")
        Apply --> Verify("🤖 Verify & track<br/>Outcome + sync")
    end

    Goal --> Find
    Verify -->|Next event| Qualify

    State[("⚙ Private state<br/>Profile · duplicates · reservations")]
    Wait("⚙ Cooldown gate<br/>Wait locally → wake agent")
    Qualify -.->|Check + reserve| State
    Verify -.->|Save outcome| State
    Apply -->|Rate limited| Wait
    Wait -->|Due: one retry| Apply

    classDef human fill:#fef3c7,stroke:#d97706,color:#78350f,stroke-width:2px
    classDef agent fill:#eef2ff,stroke:#818cf8,color:#312e81,stroke-width:2px
    classDef local fill:#ecfdf5,stroke:#34d399,color:#064e3b,stroke-width:1.5px
    class Goal human
    class Find,Qualify,Apply,Verify agent
    class State,Wait local
    style Agent fill:#f8fafc,stroke:#cbd5e1,color:#334155
```

- **Apply once:** deduplicate events, reserve each submission, and reconcile uncertain results.
- **Verify before continuing:** pending, waitlisted and admitted stay distinct; sync each result.
- **Resume cheaply:** the optional local runner waits without model calls. A desktop heartbeat
  is an alternative when CLI browser access is unavailable and does invoke the model.

Profiles and campaign records stay in `~/.local/share/eventmaxxer/`, outside the repo.
Use one scheduler per account; local locks do not coordinate separate machines.
Sites may still require missing answers, login or manual steps.

[Agent workflow](.agents/skills/eventmaxxer/SKILL.md) ·
[State & commands](docs/state.md) · [Scheduling](docs/scheduling.md) ·
[Tracking & exports](docs/tracking.md)

## Validation

```sh
python3 -m unittest discover -s tests -v
```

Tests use temporary state and fake agents, with no live applications.

Inspired by [Continual Outreach](https://github.com/giga-james/continual-outreach).
