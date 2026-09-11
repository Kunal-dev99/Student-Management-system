# 14 · Statutory reporting — draft a HESA return, reconcile, sign off, file

## What it is

HESA (Higher Education Statistics Agency), OfS, research council returns — all built from the same Enterprise 360 read model that runs internal analytics. In this chapter we open the current-cycle HESA return draft (Priya's registration in this demo has already contributed a row), check the reconciliation banner, sign it off, and watch the filing task land in the integration outbox.

## The clicks

**Step 01 · Show the shared source of truth.**
- **WHERE** — Sidebar → **Analytics** (globe icon).
- **DO** — Show the five-lens tabs across the top of the table: Student / Research / Funding / Workforce / Statutory.
- **SEE** — One row per person. Switching tabs re-projects the same rows through different fields.
- **SAY** — *"One row per person. Five lenses. Every internal report and every statutory return draws from this same view."*

**Step 02 · Open the HESA draft.**
- **WHERE** — Sidebar → **Statutory** → **HESA Student return** → **Current cycle**.
- **DO** — Show the draft return.
- **SEE** — One row per student in scope, statutory fields down the columns, reconciliation banner at the top.
- **SAY** — *"Draft return. Fields are the HESA schema; rows come straight off the 360 view."*

**Step 03 · Reconcile.**
- **WHERE** — Top of the return page.
- **DO** — Point at the reconciliation row: "Matches operational totals" in green.
- **SEE** — Green tick. Deltas column empty.
- **SAY** — *"The return numbers reconcile with operational screens by construction — because there's only one source."*

**Step 04 · Sign it off.**
- **WHERE** — Top-right → **Sign off** button.
- **DO** — Click. Modal asks for a sign-off note ("reviewed against operational totals, no outstanding queries"). Confirm.
- **SEE** — Status flips from "Draft" to "Signed off" with your name and timestamp.
- **SAY** — *"Sign-off is a workflow transition. Preserved forever with who and when."*

**Step 05 · Confirm the filing task in the outbox.**
- **WHERE** — Sidebar → **Integration** → **Outbox** → filter by "HESA".
- **DO** — Show the filing task row.
- **SEE** — Event `hesa.return.file`, target `HESA adapter`, queued for delivery.
- **SAY** — *"Filing goes through the outbox like any other partner emission. Retried if HESA's endpoint is slow — we don't have to babysit."*

## The line

The dashboard and the HESA return are the same numbers, always. No sub-reports drifting from the source.
