# PGR Platform — AI Delivery Team

Three specialised Claude Code subagents (defined in `.claude/agents/`) build the PGR platform
from two sources of truth: the architecture spec (`PGR_Platform_Technical_Architecture.pdf`)
and the FP "Redwood Professional" design system (`fp_design_system_template/`).

## The team

| Agent | Role | Aligned to | Writes |
|---|---|---|---|
| **solution-architect** | Reads the spec, breaks work into phase-wise FE/BE tasks, sequences, and verifies completion. Plans — never writes app code. | The full architecture PDF (§21 phasing) | `docs/PGR_DELIVERY_PLAN.md`, `docs/DECISIONS.md` |
| **backend-engineer** | Builds FastAPI + PostgreSQL exactly per the spec (modular monolith, layered, RBAC + row-scoping, workflow/outbox). | Arch §4–§13, Appendices A–C | `backend/**` |
| **frontend-engineer** | Builds the Next.js 14 UI aligned verbatim to Redwood Professional. | `fp_design_system_template/` + arch §11/§14 | `frontend/**` |

## How the loop works (verifiable by design)

1. **Plan** — the architect owns `docs/PGR_DELIVERY_PLAN.md`: every task is a checkbox with a
   stable ID (`FE-1.4`, `BE-1.4`) and a one-line **Done-when** acceptance criterion.
2. **Build** — you assign a task to the matching engineer. They implement it and report the
   exact test/build output plus how they met the Done-when line.
3. **Verify** — the architect checks the criterion against real code/tests and only then ticks
   the box and updates the progress rollup. Boxes are never ticked on assertion alone.

So at any moment the plan tells you exactly what is done (`[x]`), in progress (`[~]`), and not
started (`[ ]`) — split by frontend vs backend, per phase.

## How to drive them (examples)

```text
Use the solution-architect to review and refine docs/PGR_DELIVERY_PLAN.md, then give me the
first 3 backend and 3 frontend tasks to start Phase 0.
```
```text
Use the backend-engineer to implement BE-0.1 through BE-0.4.
```
```text
Use the frontend-engineer to do FE-0.1 and FE-0.2 (install the design system).
```
```text
Use the solution-architect to verify BE-1.4 and update the plan.
```

You can run backend and frontend tasks **in parallel** when they don't depend on each other
(dependencies are marked `(needs BE-x.y)` in the plan).

## Guardrails baked into each agent
- **architect** never touches source; routes coding to the engineers; logs decisions.
- **backend** keeps SQLAlchemy models out of the API layer, fails closed on authz, writes
  audit + outbox in the same transaction, keeps external systems authoritative via adapters.
- **frontend** uses design-system components verbatim (no restyling), all data via `/api/v1`,
  nav driven by `/api/v1/me`, types generated from the backend OpenAPI contract.

## Files
- `.claude/agents/solution-architect.md`
- `.claude/agents/backend-engineer.md`
- `.claude/agents/frontend-engineer.md`
- `docs/PGR_DELIVERY_PLAN.md` — the phased task board (your verification surface)
- `docs/DECISIONS.md` — decision log
