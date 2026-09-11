# 23 · Pattern Lab (ML) — run a prediction batch, review, approve, watch it reach the student page

## What it is

The quiet corner where machine-learning predictions live. A model produces predictions (say, submission-timeliness scores); an analyst reviews them; an approver signs them off; only then do the predictions become visible to end users. Permissions gate every step. Nothing an ML pipeline emits reaches a supervisor's screen without a human on the approval chain. In this chapter we open a recent batch, review it, approve one prediction, and then jump to that student's page to see the approved prediction appear.

## The clicks

**Step 01 · Open Pattern Lab.**
- **WHERE** — Sidebar → **Pattern Lab** (under `ADVANCED`).
- **DO** — Show the runs list.
- **SEE** — Rows: model name, run date, prediction count, review status.
- **SAY** — *"Every ML run is a row here. Nothing gets promoted to production without going through review and sign-off."*

**Step 02 · Open a recent batch.**
- **WHERE** — Latest "submission timeliness" batch → click.
- **DO** — Show the predictions table.
- **SEE** — Columns: student, prediction (e.g. `Likely to miss submission window`), confidence (0.72), reviewer, approver, status.
- **SAY** — *"Every row is a prediction on one student. Confidence beside the label — nothing hidden."*

**Step 03 · Review one prediction.**
- **WHERE** — One row → **Review** button.
- **DO** — Read the input features shown, then click **Accept** or **Reject** with a note.
- **SEE** — Row's review status flips to "Reviewed" with my name and comment.
- **SAY** — *"Analyst pass. Confidence and features are visible — no black box."*

**Step 04 · Approve to promote.**
- **WHERE** — Same row → **Approve for release** (approver role, or same session with the right permission).
- **DO** — Click. Confirm.
- **SEE** — Row status flips green "Approved". A visible-to-users flag appears on the record.
- **SAY** — *"Approver signs off. Nothing reached an end user before this click."*

**Step 05 · See it on the student page.**
- **WHERE** — Sidebar → **Students** → open the student the prediction was about → **Predictions** panel.
- **DO** — Point at the new prediction card.
- **SEE** — Badge with the prediction, confidence, and "Approved by: <name>" attribution.
- **SAY** — *"Every prediction the supervisor sees has a human name attached — the person who approved it. No black-box surprises."*

## The line

Nothing an ML pipeline emits reaches an end user without a human on the approval chain.
