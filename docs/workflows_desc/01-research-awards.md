# 01 · Research awards — create one live

## What it is

A funder gives the institution money for research. In this demo we create a real award for a fictional grant — funder, value, term, headcount — and save it. That saved record becomes the top of everything downstream: the opportunities we post in the next chapter, the funding arrangements each student will have, the audit trail the compliance officer follows a year later. Awards move through their own lifecycle: **draft → active → closed**.

## The clicks

**Step 01 · Open the awards list.**
- **WHERE** — Sidebar → **Research** (flask icon) → **Awards** tab.
- **DO** — Land on the awards list. Note the counts at the top: total awards, active, closed.
- **SEE** — Existing awards as rows with funder, value, term, headcount, status pill.
- **SAY** — *"Every research grant the institution has won is here. I'm going to add a new one live."*

**Step 02 · Start a new award.**
- **WHERE** — Top-right of the list → **+ New award** button.
- **DO** — Click. A form drawer slides in.
- **SEE** — Blank form: funder, reference, title, value, currency, valid_from, valid_to, studentships_funded, research_area, notes.
- **SAY** — *"Everything about the grant is one form. No email attachments to chase."*

**Step 03 · Fill the award.**
- **WHERE** — In the form.
- **DO** — Type these values:
  - **Funder** — `UKRI EPSRC`
  - **Reference** — `EP/Z000000/1`
  - **Title** — `CDT in Applied AI · Cohort 2027`
  - **Value** — `1,860,000`  **Currency** — `GBP`
  - **Valid from** — `2026-10-01`  **Valid to** — `2030-09-30`
  - **Studentships funded** — `10`
  - **Research area** — pick `Machine Learning`
  - **Notes** — `Four-year full-time studentships. Includes stipend, fees, RTSG.`
- **SEE** — Value auto-formats with commas. Field validation ticks green as each required field is filled.
- **SAY** — *"Ten studentships, four years each, £1.86m in total. Real numbers a funder would recognise."*

**Step 04 · Save and see it become real.**
- **WHERE** — Bottom-right → **Save award** button.
- **DO** — Click. Wait a beat.
- **SEE** — Drawer closes. New row appears at the top of the awards list with status pill "Active" and a green flash on the row.
- **SAY** — *"The award is live. Any admin can now attach opportunities to it. The audit log has already recorded who created it and when — I can prove that at any point."*

**Step 05 · Show the audit trail.**
- **WHERE** — On the new award row → click into detail → **History** section at the bottom.
- **DO** — Point at the "created" row that just landed.
- **SEE** — One audit row: my actor id, timestamp, action `award.create`, request id.
- **SAY** — *"Before I do anything else — this award is already audit-trailed. Everything downstream will be too."*

## The line

Every funded student's story starts here — one grant, one form, one row, dated and audited.
