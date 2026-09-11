# 20 · Composer — ask a question, get a live dashboard, prove the citations

## What it is

Freeform question → planner picks data functions → they run against live data → the model composes a JSON render spec → the frontend validates it against 17 block types and renders. Every value in the prose has to appear in the underlying data — grounding is a mechanical check. If the model refuses or invents, a deterministic KPI-plus-table fallback renders instead. In this chapter we ask a per-student question that pulls a full progress dashboard for Priya, then a shape-different question about caseloads.

## The clicks

**Step 01 · Open Composer.**
- **WHERE** — Sidebar → **Composer** (under `ADVANCED`, wand icon).
- **DO** — Land on the empty ask page.
- **SEE** — Big question box, list of example queries below.
- **SAY** — *"Ask a question. Get a dashboard. The model doesn't write SQL — it picks from a fixed catalogue."*

**Step 02 · Ask a full-student dashboard.**
- **WHERE** — Question box.
- **DO** — Type: `Give me a full progress dashboard for Priya Nair`. Press Enter.
- **SEE** — Trace ticks: *planning → calling functions → composing*. Blocks render one at a time — narrative paragraph, KPIs, timeline, milestones panel, funding lineage tree.
- **SAY** — *"Everything on this page was validated on the way in. The model picked the blocks — but the values came from typed data functions."*

**Step 03 · Prove the grounding.**
- **WHERE** — Any figure in the narrative (e.g. "£1,552 monthly stipend").
- **DO** — Point at it. Then point at the funding-lineage tree beside it — the same figure appears there verbatim.
- **SEE** — Same number twice — prose and evidence.
- **SAY** — *"Every number in the paragraph appears in the data — grounding is a mechanical check. If the model invents, the grounded version doesn't render."*

**Step 04 · Ask a shape-different question.**
- **WHERE** — Same page.
- **DO** — Type: `Show me supervisor caseloads against their caps`. Press Enter.
- **SEE** — Different block (bar chart) with real caseload numbers.
- **SAY** — *"Bar chart because the functions returned rows with a limit. Composer picks the shape from the data, not from the phrasing."*

**Step 05 · Reveal the citations.**
- **WHERE** — Below the composition → **Why this layout** toggle.
- **DO** — Click.
- **SEE** — List of function names that were called, each block titled with its function.
- **SAY** — *"Every value has a citation. If a number's wrong, we know exactly which function produced it."*

## The line

The composer can't invent a number — every value has a citation in the data.
