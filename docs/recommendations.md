# Attendance recommendations

Phase one builds options. Phase two helps the user spend limited time meeting the people
who matter for their current goal. Run this workflow when asked to prioritize attendance;
it grants no application, cancellation, outreach or scheduling authority.

## Establish the goal

Read the selected campaign's existing profile, preferences and live tracker first. Reuse
known facts. Ask which people the user needs to meet and what relationship outcome they
want, then ask about available attendance capacity if unknown. Keep questions individual.
Useful specificity includes role, organization type, stage/domain and why a conversation
would help. Do not assume that every founder wants investors, customers or cofounders.

Save a user-grounded `preferences.networking_goal` string in private campaign configuration.
Include the priority order of target audiences and desired outcomes in that goal. Read and
merge existing preferences when configuring: `configure` replaces the preferences object.
Change the goal when the user's priorities change; previous assessments then require review.
Store capacity and the intended date window in private preferences/checkpoints as well.
Never commit the real goal, tracker ID, research or personal notes to this repository.

## Research the options

Use the existing tracker as the inventory, preserving canonical event keys and actual
registration status. For legacy campaigns, continue in their current tracker and ledger;
do not manufacture submissions or migrate merely to run the helper.

Read event descriptions, organizer pages, agendas and accessible attendee information
through supported tools. Record source URLs, concrete observations and offset-aware
`checked_at` timestamps. Separate those observations from inferred networking fit.
A sponsor or speaker listing is not evidence that someone is accessible for conversation.
An audience described as founders is not evidence of a particular named attendee.
Do not interpret an application approval as a networking endorsement.

Assess each option against the same goal:

| Dimension | 0 | 1 | 2 | 3 |
| --- | --- | --- | --- | --- |
| Audience fit | Evidence of unrelated audience | Broad adjacent audience | Explicit target audience | Strong evidence of concentrated target audience |
| Conversation access | Evidence of no interaction opportunity | General mingling or Q&A | Dedicated networking or small-group interaction | Structured direct interaction with the target audience |

Unknown is not zero. Leave unresearched events without an assessment. If evidence supports
only a tentative judgment, record low confidence and explain the missing facts. High
confidence requires direct, specific evidence for both dimensions; medium allows clearly
identified inference. These are qualitative judgments, not calibrated probabilities.

Each assessment needs target people, a plain-language reason, a useful conversation plan,
confidence and sources. Identify the most important uncertainty in the reason. Recheck
outdated sources and registration status before a final attendance decision; the local
helper does not browse, detect changed pages or expire evidence automatically.

## Local helper

For campaigns already using SQLite, store an assessment separately from event application
state. Assessments belong to one campaign and goal, even when campaigns share an event.

```sh
python3 scripts/recommend.py --home /absolute/private/state --campaign conference --event EVENT_ID --json @/absolute/private/assessment.json
python3 scripts/recommend.py --home /absolute/private/state --campaign conference --limit 3
python3 scripts/export.py --home /absolute/private/state --campaign conference --output /absolute/private/events.csv --recommendations --limit 3
```

Fictional assessment JSON:

```json
{
  "audience_fit": 3,
  "conversation_access": 2,
  "confidence": "medium",
  "target_people": "Robotics procurement leads",
  "reason": "The agenda includes buyer roundtables; the attendee mix is not confirmed.",
  "conversation_plan": "Ask buyers where pilot procurement stalls and whether a follow-up would help.",
  "sources": [{
    "url": "https://events.example.org/robotics-roundtable",
    "observation": "The published agenda lists buyer roundtables.",
    "checked_at": "2026-10-02T10:00:00-07:00"
  }]
}
```

The transparent fit score is `2 × audience fit + conversation access` (0–9). It gives
more weight to who is there than format. It is a ranking aid, not the probability of
meeting someone. Audience fit below 2 or conversation access below 1 is low priority.
Low-confidence assessments and missing dates require research. Expired events and
unavailable registrations are excluded. Pending, waitlisted and other unconfirmed
registrations are conditional, even when fit is high.

The helper greedily selects up to `--limit` admitted events, highest fit first, and flags
known overlapping alternatives. The cap applies to the campaign's upcoming options,
not automatically to each week. Unknown end times require a schedule check. It does not
optimize travel, fatigue, repeated audiences or a globally optimal combination. Before
presenting a final shortlist, the agent must apply the requested date window, available
hours, travel time, existing commitments and diversity of target audiences using the live
tracker. Ask for missing constraints only when needed. Explain any departure from score
order. Existing Attend decisions count toward capacity; they are not silently reversed.

## Present in the tracker

Keep registration status and user decision intact. Add recommendation, fit score,
confidence, target people, why recommended, conversation plan, evidence links and known
conflicts. Offer views for Shortlist, Conditional, Research and lower-priority alternatives.
The CSV helper reads the live CSV decisions before ranking; explicit Skip, Decline,
Declined, Not attending and No decisions are excluded. Other decision vocabularies and fixed
Attend commitments must be reconciled by the agent before finalizing the shortlist.

For Google Sheets, use its skill and connector, inspect the actual schema first, and add
only agent-owned recommendation columns or a separate linked view. Preserve formulas,
registration fields, user decisions and notes. Join on canonical keys, never row numbers.
Read back every updated key and recommendation. Do not replace/import the workbook.
Recommendation writes must not acknowledge pending application sync unless application
fields were also independently verified. The local helper does not include a Sheets client.

Give the user a small actionable set: why attend, who to seek, what to ask, the evidence
and the main uncertainty. Keep conditional backups separate from admitted choices.
After attendance, use explicit feedback about people met, useful conversations and
follow-ups to refine the next assessment. Do not equate attendance or approval with success.
