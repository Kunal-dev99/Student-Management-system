# 05 · Supervisor allocation — assign primary, add co, later change

## What it is

Priya is registered. The supervisor from her opportunity (Elena Ford) auto-attaches as primary at 100%. Now we add a methods co-supervisor (Prof. Roland Vega, 40%) and, later in the demo, we simulate a change-of-supervisor request. Every action is a dated fact with a reason; weightings count against the supervisor's cap on the workforce lens.

## The clicks

**Step 01 · Open Priya's supervision panel.**
- **WHERE** — Sidebar → **Students** → Priya Nair → scroll to **Supervisors** panel.
- **DO** — Show the current state: Elena as primary at 100%.
- **SEE** — One row with role "Primary", weighting "100%", valid_from today.
- **SAY** — *"Elena auto-attached because the opportunity was under her name. That's the default — we can add and adjust."*

**Step 02 · Add a co-supervisor.**
- **WHERE** — Top-right of the panel → **+ Add supervisor**.
- **DO** — In the form: pick `Prof. Roland Vega`, role `Co-supervisor`, weighting `40%`, reason `Methods expertise for RL work`. Save.
- **SEE** — Elena's weighting auto-adjusts from 100% to 60%. New row appears for Roland at 40%. Total = 100%.
- **SAY** — *"Weightings have to sum to 100. The platform rebalances Elena's automatically."*

**Step 03 · Verify Roland's caseload updated.**
- **WHERE** — Sidebar → **Workforce** → find Roland's row.
- **DO** — Point at his current load and headroom.
- **SEE** — Load went up by 0.4 of a student. Headroom column reflects it.
- **SAY** — *"40% on Priya counts as 0.4 against Roland's cap. Real, weighted, department-wide."*

**Step 04 · Simulate a change request (later in the demo).**
- **WHERE** — Back on Priya's record → **Supervisors** panel → Roland's row → **Request change**.
- **DO** — Fill form: proposed new supervisor `Dr. Anna Costa`, reason `Roland moving institutions`, end_date old = start_date new.
- **SEE** — Change request row appears with amber "Pending review" pill.
- **SAY** — *"Every change carries a reason. The old relationship's end-date and the new one's start-date move together."*

**Step 05 · Approve it in the requests queue.**
- **WHERE** — Sidebar → **Supervision** → **Requests** tab → open the request.
- **DO** — Click **Approve**. Confirm.
- **SEE** — Roland's row on Priya's panel shows valid_to = today. Anna's row appears with valid_from = tomorrow, same 40% weighting.
- **SAY** — *"Roland is off, Anna is on, both dated. Priya's supervision history is intact — nothing overwritten."*

## The line

Every supervision decision is a dated fact with a reason attached — never an "as-of-today" guess.
