# 07 · Funding — see the arrangement that spawned, add a stipend payment, reconcile

## What it is

When we registered Priya in chapter 04, the platform auto-created a **funding arrangement** against the award we made in chapter 01. That arrangement carries the stipend schedule; every month, a payment row lands. In this chapter we open the arrangement, look at the schedule, mark a payment as landed, then find and clear a reconciliation row on the funding-integrity page.

## The clicks

**Step 01 · Open Priya's funding.**
- **WHERE** — Priya's student page → **Funding** panel (or Sidebar → **Funding** → filter by her name).
- **DO** — Show the arrangement that auto-created on registration.
- **SEE** — One arrangement row: type `Research council`, source `UKRI EPSRC — EP/Z000000/1`, valid_from today, valid_to +4 years, status active.
- **SAY** — *"The arrangement spawned automatically. Award → opportunity → registration → arrangement. Zero admin action."*

**Step 02 · Show the funding lineage tree.**
- **WHERE** — Same page → **Funding lineage** panel.
- **DO** — Point at the tree: **UKRI EPSRC** (top) → **EP/Z000000/1** (award) → **arrangement** → **Priya Nair** (bottom).
- **SEE** — Four-tier tree, edges labelled "funds".
- **SAY** — *"Four levels: funder, award, arrangement, student. Trace this £74,400 for me — the graph is the answer."*

**Step 03 · Open the stipend schedule.**
- **WHERE** — Click the arrangement → **Stipend schedule** section.
- **DO** — Show the auto-generated monthly rows for the four-year term.
- **SEE** — 48 rows, one per month, each with due_date and amount (`£1,552`).
- **SAY** — *"Payments schedule themselves. No one types 48 rows."*

**Step 04 · Mark a payment as landed.**
- **WHERE** — Any past-due payment row → **Mark paid**.
- **DO** — Click. Enter reference: `UKRI-PAY-2027-02-4471`. Confirm.
- **SEE** — Row flips to green "Paid". Total-paid count on the arrangement goes up by £1,552.
- **SAY** — *"Real payment reference from the funder. Every payment traceable to a real transfer."*

**Step 05 · Find a reconciliation gap.**
- **WHERE** — Sidebar → **Funding integrity** (shield-alert icon).
- **DO** — Filter to Priya's arrangement. Point at any amber row.
- **SEE** — Row showing paid-so-far vs expected-so-far with the delta.
- **SAY** — *"If UKRI paid less than the arrangement says, it shows here. Every mismatch surfaces."*

**Step 06 · Clear the reconciliation.**
- **WHERE** — Amber row → **Resolve**.
- **DO** — Add a resolution note ("timing difference, will land next month") and save.
- **SEE** — Row flips to green with the note. Audit row lands under the arrangement.
- **SAY** — *"Nothing sits open. Every gap either gets resolved or turns into a follow-up task."*

## The line

Every pound has a paper trail — from the funder, through the award, through the arrangement, to the payment.
