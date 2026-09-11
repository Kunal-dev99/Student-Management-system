# 09 · Thesis — intent to submit, nominate examiners, catch the CoI, schedule the viva

## What it is

Priya has passed all her milestones. She signals intent to submit. In this chapter we record that intent, nominate two examiners (internal + external), watch the conflict-of-interest check refuse one and accept the other, schedule the viva, record the outcome, track corrections, and land at "award ready". The corrections have their own sub-workflow; the award button only unlocks when they close.

## The clicks

**Step 01 · Record the intent to submit.**
- **WHERE** — Priya's student page → **Thesis** panel → **+ Record intent to submit**.
- **DO** — Fill: intended submission date (three months out), working title `Explainable Reinforcement Learning for Clinical Decision Support`.
- **SEE** — A thesis row appears with status "Intent recorded". A task appears for the graduate school: "Start examiner nomination for Priya Nair".
- **SAY** — *"Student signals intent, and the examiner nomination workflow starts. No one waits for the deadline."*

**Step 02 · Nominate an internal examiner (that conflicts).**
- **WHERE** — Same panel → **Examiners** section → **+ Nominate internal**.
- **DO** — Type `Prof. Roland Vega` (Priya's former co-supervisor).
- **SEE** — Red banner: *"Cannot nominate — served as co-supervisor on this thesis."*
- **SAY** — *"The system knows. Roland was on the record as co-supervisor — he can't examine his own student."*

**Step 03 · Try a plausible but conflicted external.**
- **WHERE** — Same field, or **+ Nominate external**.
- **DO** — Type `Prof. Jian Kwan` (fictional external, has co-authored with Roland).
- **SEE** — Amber warning: *"Co-authored with Prof. Vega in 2024 — reviewer discretion required."* Approve or reject buttons appear.
- **SAY** — *"Not disqualifying, but flagged. Prof. Vega's on the record, and Kwan's on a paper with him — worth knowing before the viva."*

**Step 04 · Nominate a clean external.**
- **WHERE** — Same field.
- **DO** — Type `Prof. Aisha Adekunle` (no prior links). Click **Save nomination**.
- **SEE** — Green tick badge. Examiner-invitation workflow task appears in the outbox.
- **SAY** — *"Green. Nomination saved. Invitation goes out automatically — no email chain to chase."*

**Step 05 · Schedule the viva.**
- **WHERE** — Thesis panel → **Viva** section → **Schedule viva**.
- **DO** — Fill: date, chair, mode (in-person / hybrid). Save.
- **SEE** — Viva row appears with "Scheduled" pill. Calendar invites emit through the outbox.
- **SAY** — *"Viva scheduled. Every party gets a calendar invite via the integration outbox — retried if a partner is slow."*

**Step 06 · Record the viva outcome.**
- **WHERE** — After the viva (simulate) → **Viva** section → **Record outcome**.
- **DO** — Fill: outcome `Pass with minor corrections`, deadline for corrections (3 months out), notes.
- **SEE** — Viva status flips to "Outcome recorded". Corrections sub-workflow opens with state "Not started".
- **SAY** — *"Outcome preserved. The corrections sub-workflow opens — the award button stays greyed until they close."*

**Step 07 · Simulate corrections landing.**
- **WHERE** — **Corrections** block → **Upload correction response**.
- **DO** — Upload a PDF, mark as submitted. Then as internal examiner: **Approve corrections**.
- **SEE** — Corrections status flips to "Approved". The **Record award** button in the Completion panel turns Redwood red.
- **SAY** — *"Corrections approved. The state machine unlocks the next step. No admin discretion — the button was greyed for a reason."*

## The line

The most compliance-heavy stretch of the arc has the least paperwork — because the state machine does the checking.
