# AI-Assisted Development Approach and Engineering Methodology

**v2 — October 2026.** Supersedes the v1 document of the same title. Changes from v1 are
marked [NEW] in each section. Every code snippet is drawn verbatim from the PGR Platform
repository and can be opened at the file path shown above it.

---

## 1. Purpose

This document describes how we currently build new functionality within the existing Fusion
SaaS framework.

Its purpose is to make clear:

- How a new requirement is analysed before development
- How the technical approach is researched and selected
- How architecture and project context are maintained
- How development is divided into controlled phases
- How AI-assisted development is constrained and directed
- How frontend, backend, API and database changes are coordinated
- How machine-based and human testing are performed
- How functionality is validated against real business scenarios
- How we minimise uncontrolled or unsupported AI-generated changes
- **[NEW] How every change we ship can be reversed**
- **[NEW] How work in progress is isolated from live data**

The objective is not to treat AI as an independent developer. AI is used as a development
capability inside an established engineering process, architecture and set of controls.

---

## 2. Overall Development Methodology

For a new requirement or feature our process is:

```
Requirement
   ↓
Research existing solutions
   ↓
Evaluate available approaches
   ↓
Define / refine the proposed approach
   ↓
Question, test and validate the approach
   ↓
Finalise architecture and implementation plan
   ↓
Phase-wise development planning
   ↓
Isolate the work (branch + database copy)         [NEW]
   ↓
Controlled AI-assisted development
   ↓
Independent review (code + security)              [NEW]
   ↓
Build, type check and migration round trip        [NEW]
   ↓
Machine regression testing
   ↓
Human / developer testing
   ↓
Next development phase
   ↓
End-to-end feature testing
   ↓
Business scenario / edge-case testing
   ↓
Feature completion
   ↓
Record decisions and known limits                 [NEW]
```

Coding does not begin because a requirement arrived.

---

## 3. Requirement and Existing Architecture

When a new feature is identified, the first step is to understand how it fits the existing
application.

We maintain architectural documents that define the overall structure and principles:

```
PGR_Platform_Technical_Architecture.pdf   — the architecture spec
docs/PGR_IMPLEMENTATION.md                — how modules are built
docs/PGR_DATABASE_AND_API_MAP.md          — tables, endpoints, who owns what
docs/DECISIONS.md                         — standing technical decisions
```

They establish:

- Application architecture (modular monolith; FastAPI + SQLAlchemy 2.0 async + Postgres 16
  + Alembic on the backend, Next.js 14 on the frontend)
- Separation of responsibilities and frontend / backend / database boundaries
- API principles and database principles
- Component structure
- Architectural constraints and development conventions

A new feature is implemented as part of the existing system, not as an isolated piece of
functionality.

---

## 4. Research Before Implementation

Once the requirement is understood we research how similar problems are currently solved:
industry approaches, comparable systems, framework capabilities, security and scalability
considerations, usability patterns and the limitations of each.

The intention is **not to copy** an existing implementation but to **understand the available
approaches** so we can pick the one that best fits our application. Where appropriate we
combine approaches into a hybrid solution.

---

## 5. Challenge and Validate the Proposed Approach

The proposed solution is questioned before it becomes the plan. It is assessed against:

- Functional completeness
- Security
- Scalability
- Maintainability
- Compatibility with the existing architecture and existing functionality
- Database, API and frontend implications
- Potential regression risks
- Future extensibility
- Overall technical feasibility

Only when the direction is clear is the approach finalised.

---

## 6. Project Context

The application maintains a **Project Context** that carries the evolving context of the
project across development tasks. It records:

- Requirements
- Technical decisions
- Changes
- Development context
- Important constraints
- Architectural decisions
- Relevant conclusions
- Major prompts and instructions where appropriate

Without it, AI-assisted development loses context between tasks and risks reinterpreting
requirements, forgetting decisions, introducing unsupported functionality, architectural
drift and inconsistent decisions.

### 6.1 How we store it

The repository holds the live store under `.project-memory/` (append-only event log plus a
searchable index). An extract is checked into git as `PGR_context_matrix.tar.gz`.

Querying it from the command line, for example to see every recorded decision:

```bash
"Project context system/.venv/Scripts/python.exe" -m pcs.cli query --type decision
```

### 6.2 [NEW] When it must be updated

Project Context is updated at phase completion and whenever a decision is confirmed, not
"continuously" in general. Enforcement is explicit:

- A git post-commit hook records every commit (`pcs track-commit`) so no code change is
  invisible.
- A session hook records the chat transcript (`pcs track-session`).
- A manual `pcs record` and `pcs checkpoint` is required at the end of each phase for the
  decision, acceptance criteria and known limits.

---

## 7. Phase-wise Development

Once the overall approach is finalised the feature is divided into **phase-wise tasks**.

A phase is intentionally small, but not necessarily limited to one technical layer. A single
phase may contain frontend, backend, API and database changes, so each phase is a small but
meaningful end-to-end slice.

### Example: custom-attribute governance (seven phases, one commit each)

```
P1  Request → maker-checker → active                 (commit 835d772)
P2  Deterministic duplicate + HESA assessment        (commit a67d228)
P3  Review / keep / retire / restore (no deletion)   (commit ca51e10)
P4  Profile-aware picker + obsolete mapping block    (commit e4b1792)
P5  Return loads only mapped attributes              (commit ba06600)
P6  Usage tracking + review candidates               (commit 762c6a0)
P7  Production hardening                             (commit dafca50)
```

Every phase includes model + migration + service + API + UI + tests. The next phase only
builds on the validated output of the previous one.

---

## 8. Controlled AI-Assisted Development

Coding is controlled through named agents with written **scope**, **tools**, **sources
of truth** and **boundaries**. The agent definitions themselves live in the repository
under `.claude/agents/` and are reviewed like any other code.

### 8.1 Where the agents are defined

```
.claude/agents/
    solution-architect.md     (100 lines)
    backend-engineer.md       (148 lines)
    frontend-engineer.md      (95  lines)
```

Each file carries YAML frontmatter the host reads to constrain the agent (which tools it
may call, which model to use), followed by a role instruction the agent reads at the start
of every session. Because these are text files in git, their changes are visible, reviewed
and reversible like any other change.

### 8.2 The three core agents, with their real scope and boundaries

#### solution-architect — plans, decomposes, verifies. Does not write code.

```yaml
# .claude/agents/solution-architect.md (frontmatter)
---
name: solution-architect
description: >
  Reads the PGR Platform Technical Architecture spec and turns it into a phase-wise,
  verifiable task breakdown split into Frontend and Backend workstreams.
  It plans and coordinates; it does not write application code itself.
tools: Read, Grep, Glob, Write, Edit
model: inherit
---
```

Observe the **tools** line: `Bash` is absent. The architect cannot run migrations, delete
files or execute arbitrary shell commands. Its `Write` and `Edit` are used only against
the plan and decision log, not against application code.

Sources of truth it is instructed to read **before planning anything** (quoted verbatim
from the file):

```
1. Architecture spec — PGR_Platform_Technical_Architecture.pdf (42 pages:
   system overview, 12 capability→module map (§7), full PostgreSQL data model
   (§8), workflow/task/notification engine (§9), integration/outbox (§10),
   API catalog (§11), authn/authz/RBAC/row-scoping (§12), reporting (§13),
   frontend contract (§14), NFRs (§15), MVP scope & phasing (§21)).
2. Design system — fp_design_system_template/ ("Redwood Professional"):
   INSTRUCTIONS.md, tokens.md, README.md.
3. The living plan — docs/PGR_DELIVERY_PLAN.md. The architect is its owner.
```

Hard rules the architect must follow (quoted):

```
- Every task is a single checkbox line `- [ ] BE-1.3 …` or `- [ ] FE-1.3 …`
  with a stable ID. IDs never get renumbered once issued.
- Each task states its Done-when acceptance criterion in one line — something
  the user can literally check.
- When work is reported complete, you tick the box only after confirming the
  acceptance criterion against the actual code/tests — never on assertion alone.
```

Explicit boundaries (quoted):

```
- You never edit files under backend/ or frontend/ source. You route that work
  to backend-engineer and frontend-engineer.
- You keep external systems (Research, Finance, HR, IdP) as integration
  boundaries per §10 — never plan the platform to become a system of record.
- When the spec is ambiguous, you record the question in docs/DECISIONS.md
  with a recommendation and surface it to the user rather than guessing silently.
```

#### backend-engineer — builds FastAPI + Postgres inside a strict layered monolith.

```yaml
# .claude/agents/backend-engineer.md (frontmatter)
---
name: backend-engineer
description: >
  Builds the PGR Platform backend exactly per PGR_Platform_Technical_Architecture.pdf:
  FastAPI (Python 3.12) + SQLAlchemy 2.0 async + PostgreSQL 16 + Alembic, as a modular
  monolith with strict layering.
tools: Read, Write, Edit, Bash, Grep, Glob
model: inherit
---
```

Fixed **repository shape** (quoted) — the agent builds into this layout and no other:

```
backend/app/
  main.py                      # app factory, router registration
  core/      config.py database.py security.py dependencies.py authorization.py …
  modules/<name>/   router.py schemas.py models.py service.py repository.py events.py constants.py
  api/v1/routes.py             # aggregates module routers under /api/v1
  db/        base.py session.py migrations/   # Alembic
  workers/   app.py schedules.py tasks/…
  tests/     unit/ integration/ e2e/ conftest.py
```

> *"Every module has the same 7 files. A module's only public surface is `router.py` and
>  `service.py`."*

Strict **layering** rule (quoted) — the agent is forbidden from reaching around a layer:

```
Router (Pydantic validation + authz dep)
   → Service (business rules, transactions, events)
      → Repository (SQLAlchemy queries)
         → Database

- Routers: no business logic — validate, resolve current user, call service, shape response.
- Services: own transactions/unit-of-work; write domain events to the outbox in the
  same transaction as the state change; then commit.
- Repositories: queries only; return domain objects/rows, never HTTP concerns.
- Cross-module: call person_service.get_or_create, never a peer module's tables.
- Fail closed on authorization. No matching permission ⇒ deny.
```

Hard **data model rules** (excerpt):

```
- UUIDv4 PKs. created_at/updated_at timestamptz UTC. Soft delete only where history matters.
- Money: numeric(14,2) + separate currency char(3). The platform records funding
  *relationships*, not payments.
- Identity rule: when an applicant converts to a student, reuse the same person_id —
  never create a new person.
- History rule: supervisor and funding changes close one row (valid_to) and open
  another rather than editing in place.
```

Explicit boundaries (quoted):

```
- You do not build UI.
- You keep external systems (Research, Finance, HR, IdP, document repo) authoritative
  and reach them only through adapters — the platform never becomes them.
- No secrets in code — all config via env vars into a typed settings object.
- Report the completed BE-* and how the Done-when was verified. Do not tick the plan
  checkbox — the solution-architect verifies and ticks.
```

#### frontend-engineer — builds Next.js 14 verbatim to the Fusion design system.

```yaml
# .claude/agents/frontend-engineer.md (frontmatter)
---
name: frontend-engineer
description: >
  Builds the PGR Platform React frontend on Next.js 14, aligned verbatim to the
  "Redwood Professional" FP design system.
tools: Read, Write, Edit, Bash, Grep, Glob
model: inherit
---
```

Design system is the **non-negotiable source of truth** (quoted):

```
Bundle: fp_design_system_template/fp_design_system_template/
Read INSTRUCTIONS.md, tokens.md, and README.md in full before writing UI.
```

Hard rules from the bundle (quoted) — the agent is prevented from inventing look & feel:

```
- Logo always renders on a bg-[#15171A] rounded plate, both themes.
- Status is shown with the five status-pill utilities / <Badge variant> — low-opacity
  colored fills, never solid blocks.
- Don't change localStorage['fp_theme'] / fp_sidebar_open keys without changing both
  the store and the pre-hydration script.
- Do not invent new components or restyle beyond the bundle. The bundle is the look.
- components.json must keep baseColor: slate and cssVariables: true.
```

Contract with the backend (quoted):

```
- All data access goes through /api/v1. No direct DB or third-party calls from the browser.
- On load, call GET /api/v1/me to shape nav and hide actions the user can't perform.
  Client hiding is convenience, not security — the server always enforces.
- Types come from the backend contract. Generate the API client + types from the
  backend's /api/v1/openapi.json. Never hand-maintain request/response shapes.
```

Explicit boundaries (quoted):

```
- You do not design or migrate the database, write FastAPI services, or change API contracts.
  If a screen needs an endpoint that doesn't exist, flag it to the solution-architect for the
  backend-engineer — don't fake data silently (a clearly-labelled mock is fine while blocked).
- Do not tick the plan checkbox yourself — the solution-architect verifies and ticks.
```

### 8.3 How the three constrain each other

The three agents are deliberately set up so that **none of them can act alone**:

```
Plan comes from solution-architect, as a task with an ID and a Done-when.
      │
      ▼
Build is done by backend-engineer or frontend-engineer, inside their layout
and rules. They may NOT tick the box as done.
      │
      ▼
Verification goes back to solution-architect, who confirms the Done-when
against the real code or tests before ticking.
```

This is why no single agent can "silently refactor" the application. The architect can
plan but not write; the engineers can write but only inside their layout and only against
a planned task; neither declares its own work done.

### 8.4 Supporting read-only and review agents

In addition to the core three, these agents run inside the same session with limited
scope:

| Agent / skill | Can write? | Purpose |
|---|---|---|
| **Explore** | No | Broad fan-out search over the codebase. Used before planning to confirm what already exists. |
| **Plan** | No | Produces an implementation plan for a task without writing code. |
| **code-reviewer** | No | Reads the diff on a fresh session; comments on correctness, N+1 queries, naming. |
| **security-reviewer** | No | Focused SAST / OWASP review of the diff. |
| **test-master** | Yes (tests only) | Writes unit, integration and E2E tests with mocking strategy. |

The read-only agents are important precisely because they **cannot change code**. Their
output is advisory, not an edit.

### 8.5 Why this prevents the usual AI failure modes

| Failure the client is worried about | What stops it |
|---|---|
| AI invents architecture | Architect reads the PDF + delivery plan before planning. |
| AI writes code wherever it wants | Backend/frontend engineers must build into the fixed layout. |
| AI reaches around the layering | Layering rules are written; code review and type checks catch violations. |
| AI invents look & feel | Design-system bundle is the source of truth; "do not invent new components". |
| AI silently changes external systems | External systems are integration boundaries; adapters only. |
| AI declares its own work done | The implementer cannot tick the plan; the architect verifies first. |
| AI loses secrets into code | Explicit rule: no secrets in code, env vars only. |
| AI goes outside the scoped area | File boundaries + the tools list; e.g. the architect has no `Bash`. |

---

## 9. Controlled Execution and File Boundaries

The agents operate within defined boundaries: the frontend agent knows which areas of the
application it may touch, the backend agent similarly. The solution-architect agent
coordinates the work and directs it to the right implementation area.

The process is **not** `Requirement → AI writes whatever code it thinks is appropriate`.
It is:

```
Approved requirement
   → researched approach
   → validated technical plan
   → defined phase
   → architectural delegation
   → controlled implementation
   → review and testing
   → validation
```

### 9.1 [NEW] Isolation of in-progress work

Every feature is built in a **separate git worktree outside the running application
folder**, with its own **database copy**. The dev database is never migrated from a
feature branch — a lesson learned when switching branches in the running folder once broke
a demo mid-preparation.

```powershell
# Create an isolated worktree for the feature
git worktree add -b feat/custom-attr-governance C:/Users/KunalSharma/pgr-work/custom-attr master

# Copy the dev database so the branch is tested against real-shaped data
#   PGOPTIONS=-c app.bypass_tenant=on   bypasses row-level security for the dump/restore,
#   --enable-row-security forces pg_dump to emit the policy-aware form.
$env:PGOPTIONS = '-c app.bypass_tenant=on'
& "$PG\pg_dump.exe"     --enable-row-security -Fc -d pgr -f pgr.dump
& "$PG\createdb.exe"    pgr_custattr
& "$PG\pg_restore.exe"  --no-owner -d pgr_custattr pgr.dump
```

The branch's `backend/.env` points at `pgr_custattr`. The main app on `localhost:3000`
keeps running against the real dev database `pgr`; the preview on `localhost:3001` runs the
branch against the copy. Nothing the branch does can touch live data.

---

## 10. Development of an Individual Phase

Once a phase is defined, the work is delegated to the appropriate agents:

```
Phase N
  solution-architect  → determines the required implementation
  frontend-engineer   → performs frontend work
  backend-engineer    → performs backend / API work
                      → database changes implemented where required
```

Each agent works within its defined boundaries and the project context. Implementation
complete → the phase enters review and testing.

---

## 11. [NEW] Independent Review Step

After implementation and before human testing, the diff is reviewed by an **independent
review agent** on a fresh session, so the agent that implemented the code is not the one
that judges it. Two reviews run in parallel:

```bash
# .claude/commands/
/code-review          # correctness, N+1, simplification, test coverage
/security-review      # OWASP, authn/authz, injection, data exposure
```

Review findings land as inline comments on the diff. Issues are either fixed before the
phase closes, or recorded as a known limit (§15A) with a follow-up task raised.

---

## 11A. [NEW] Build, Type-check and Migration Round Trip

Before machine regression tests, every phase passes three structural gates:

```powershell
# 1. TypeScript strict (fails on `any`, missing props, unused imports)
cd frontend
node node_modules/typescript/bin/tsc --noEmit -p .

# 2. Production build (catches runtime wiring the compiler misses)
node node_modules/next/dist/bin/next build

# 3. Database migration round trip — up, down, up again — on a throwaway DB copy
cd ../backend
alembic upgrade   head
alembic downgrade <previous-head>
alembic upgrade   head
```

A phase that passes all three has at least no structural breakage before any test runs.

---

## 12. Machine Regression Testing

After implementation we run machine-level regression. The purpose is to determine whether
the new implementation behaves as expected and whether the changes have introduced
unintended issues. The suite covers:

- API behaviour
- Backend business logic
- Database interactions
- Frontend behaviour where testable (type check, unit)
- Integration between layers
- Existing functionality affected by the change
- Expected error handling
- Regression conditions

Example from the current project (84+ tests on each custom-attribute phase, running against
a dev-database copy):

```
tests/integration/test_custom_attr_governance_p1.py     6 passed
tests/integration/test_custom_attr_governance_p2.py     8 passed
tests/integration/test_custom_attr_governance_p3.py     4 passed
tests/integration/test_custom_attr_governance_p4.py     3 passed
tests/integration/test_custom_attr_governance_p5.py     4 passed
tests/integration/test_custom_attr_governance_p6.py     3 passed
tests/integration/test_custom_attr_governance_pg.py     3 passed  (Postgres isolation + concurrent approval)
tests/integration/test_custom_attr_governance_matrix.py 6 passed  (permission matrix)
```

The implementation agent runs the tests; the review agent (§11) reviews the diff
independently, so the two activities are separated.

---

## 13. Human / Developer Testing

Machine testing is not sufficient by itself. The implementation is also reviewed and tested
manually by a developer:

- Does the feature behave as expected?
- Has the business logic been implemented correctly?
- Does the UI behave correctly?
- Do APIs return the expected results?
- Do database changes behave correctly?
- Does unexpected behaviour occur?
- Is the implementation consistent with the intended requirement?

A human validation layer sits over the automated testing.

---

## 14. Phase Completion

A phase is complete only after the relevant implementation and validation activities are
done. The general cycle is:

```
Development → Machine testing → Human testing → Fixes (if required) → Re-testing → Phase Complete
```

Only after a phase is validated do we move to the next. Multiple small development cycles
can occur inside a larger feature.

---

## 15. Complete Feature Validation

Once all phases are complete, the whole feature is tested again as a unit. Phases may work
in isolation while interactions between them expose issues. We perform another end-to-end
validation covering the complete feature, assessed as a whole.

---

## 15A. [NEW] What We Defer and How We Track It

Not every issue found during a phase is fixed in that phase. If an issue is out of scope
for the current task, we **do not quietly fix it**; we record a follow-up task with the
context the next person needs. During the custom-attribute work, three such items were
raised and later fixed:

1. **Spec resolver cross-year fallback** — a 2026/27 return was being checked against a
   2029/30 test version; fixed in a later commit (`b33ebef`) once scoped.
2. **Validation-error envelope** — pydantic errors returned FastAPI's bare `{detail:…}`
   format instead of the application's standard `{error: {code, message, requestId}}`.
3. **Tenant leak sweep** on `/admin/users` and `/audit` (pre-existing, present on master).

A deferred task has: title, concrete symptom, where the next session must build (worktree
rule), and acceptance criteria.

---

## 16. Business Scenario and Edge-Case Testing

In addition to machine regression and standard developer testing we test realistic business
scenarios: normal cases, boundary conditions, invalid inputs, missing information,
unexpected behaviour, permission scenarios, data consistency scenarios, edge cases, and
interactions with existing functionality.

A feature can pass a technical test while still failing to address an actual business
scenario. Scenario testing is a separate layer.

---

## 17. Why We Use Multiple Testing Layers

| Layer | What it checks |
|---|---|
| **0 — Build & type check** [NEW] | Compiles, types match, migration round-trips cleanly |
| **1 — Machine regression** | Technical and regression issues against the test suite |
| **2 — Independent review** [NEW] | A separate agent challenges the diff for correctness and security |
| **3 — Human / developer testing** | Engineering and functional perspective |
| **4 — End-to-end feature test** | After all phases are integrated |
| **5 — Business scenario / edge-case** | Realistic user and business scenarios |

AI is part of the implementation process; verification is a separate, multi-layered
activity.

---

## 18. [NEW] Reversibility as a Design Constraint

Every change we ship can be put back the way it was, without data loss. This is one of the
strongest protections against both bad AI output and bad human output.

Three concrete rules:

### 18.1 Every database migration has a tested downgrade

Alembic migrations ship a working `downgrade()` in the same file as the `upgrade()`. The
Phase 1 governance migration is an example (`backend/app/db/migrations/versions/
ca1_custom_attribute_governance.py`):

```python
def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        disable_rls((_EVENT,))
    op.drop_table(_EVENT)
    op.drop_index(op.f(f"ix_{_FIELD}_status"), table_name=_FIELD)
    op.drop_constraint("fk_custom_field_decided_by", _FIELD, type_="foreignkey")
    for col in ("decision_reason", "decided_at", "decided_by_user_id", "status"):
        op.drop_column(_FIELD, col)
    for code in _PERMISSIONS:
        bind.execute(sa.text("DELETE FROM role_permission WHERE permission_id IN "
                             "(SELECT id FROM permission WHERE code = :code)"),
                     {"code": code})
        bind.execute(sa.text("DELETE FROM permission WHERE code = :code"),
                     {"code": code})
```

The round trip `up → down → up` is **tested on a database copy before the branch is
merged** (§11A).

### 18.2 Lifecycle actions never delete data

Retire, deactivate, archive and rename **hide** rather than **delete**, and keep enough
state to undo. From the custom attribute lifecycle (`custom_fields.py`):

```python
class Status:
    """Lifecycle of a custom attribute (plan §5). Stored as plain strings."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    ACTIVE = "active"
    REVIEW = "review"
    RETIRED = "retired"

    # Live = takes values, mappable, read by a return. "review" is still live.
    LIVE = (ACTIVE, REVIEW)
```

Retire moves `active → retired`; **no row is deleted**, no value is dropped. **Restore**
moves `retired → active` and the attribute's values are back on the next return run.

The ICR tenant rename kept the subdomain and the old institution row (deactivated), with
the exact undo SQL recorded alongside the change:

```sql
-- Undo (recorded at change time, never applied)
UPDATE tenant SET name='Default Institution',
                  branding='{"logoText":"PGR","primaryColor":"#C74634","tagline":"Default Institution"}'::json
 WHERE subdomain='default';
UPDATE tenant SET name='Institute of Cancer Research', deactivated_at=NULL
 WHERE subdomain='icr';
```

### 18.3 New behaviour ships behind a switch

Features ship behind a migration or a setting, so turning them off restores the previous
behaviour exactly. The custom-attribute governance only activates when `ca1`–`ca3` have run;
existing attributes migrate as `active`, so returns produce byte-identical output. Verified
by generating every return on master and on the branch against the same database copy — the
two outputs matched row for row.

### 18.4 Why ICR cares

The three worries this answers:
- A change silently loses student data → **data is never deleted as a side effect**.
- A bad release cannot be rolled back without a weekend of recovery → **every schema change
  has a one-command undo, tested first**.
- Once a feature ships it is permanent → **features can be switched off by downgrading
  the migration or flipping the setting**.

---

## 19. [NEW] Three-Layer Isolation Guarantees in a Multi-Tenant SaaS

Every tenant-scoped request is isolated at three layers. If any one of them fails, the
other two still refuse the request.

### 19.1 Account → URL subdomain → database row

```
Account (users.tenant_id)
   —one tenant per user, enforced on every sign-in—
URL subdomain (icr.app.example.com → tenant 'icr')
   —checked against the account's tenant on every request—
Database row-level security (RLS on every tenant-owned table)
   —the database refuses to return another tenant's rows even if the app forgets—
```

### 19.2 Row-level security is fail-closed

Policies installed by `backend/app/db/tenant_ddl.py`:

```python
FAIL_CLOSED  = "tenant_id = NULLIF(current_setting('app.current_tenant', true), '')::uuid"
SYSTEM_BYPASS = "current_setting('app.bypass_tenant', true) = 'on'"

def apply_policies(table: str, owner: str | None = None) -> None:
    """Install the fail-closed policy pair on `table`."""
    for name in ("tenant_isolation", "tenant_isolation_app", "tenant_isolation_system"):
        op.execute(f"DROP POLICY IF EXISTS {name} ON {table}")
    op.execute(f"CREATE POLICY tenant_isolation ON {table} "
               f"USING ({FAIL_CLOSED}) WITH CHECK ({FAIL_CLOSED})")
    op.execute(f"CREATE POLICY tenant_isolation_system ON {table} TO {owner or 'CURRENT_USER'} "
               f"USING ({SYSTEM_BYPASS}) WITH CHECK ({SYSTEM_BYPASS})")
```

**Fail-closed** means that with no tenant set, no rows are returned at all. The
`SYSTEM_BYPASS` is deliberately explicit so only migrations and seeds can read across
tenants, and only under an obvious guard.

### 19.3 Sign-in refuses an account from a different institution

If the sign-in page offers an institution picker (demo / shared address), the server checks
it after the password check and refuses when the account doesn't belong (from
`backend/app/modules/identity/service.py`):

```python
# The institution picked at sign-in must be the account's own. Checked only after the
# password is verified, so the message can't be used to discover which institution an
# email belongs to; not counted as a failed attempt (the credentials were right).
if expected_tenant_id is not None and user.tenant_id != expected_tenant_id:
    picked = await self.repo.session.get(Tenant, expected_tenant_id)
    logger.info("sign-in refused: user %s picked tenant %s, belongs to %s",
                user.id, expected_tenant_id, user.tenant_id)
    raise AuthError(
        f"This account isn't registered with {picked.name if picked else 'the selected institution'}. "
        "Choose your own institution and sign in again."
    )
```

### 19.4 Verified by a Postgres isolation test

```
# backend/tests/integration/test_custom_attr_governance_pg.py (3 tests)
test_every_governance_table_has_forced_fail_closed_rls      PASSED
test_tenants_cannot_see_or_write_each_others_attributes     PASSED
test_concurrent_approvals_produce_exactly_one_decision      PASSED
```

---

## 20. How This Addresses AI-Generated Code Risk

Our approach addresses it through controls working together:

| Control | What it prevents |
|---|---|
| Architecture spec + conventions | AI inventing architecture |
| Project Context (§6) | AI forgetting decisions between tasks |
| Solution-architect agent (§8) | AI choosing what to change on its own |
| Agent file boundaries (§9) | AI touching areas it should not |
| Isolated worktree + DB copy (§9.1) [NEW] | AI accidentally changing live data |
| Phase-wise development (§7) | Large unreviewable changes |
| Independent review (§11) [NEW] | AI reviewing its own output |
| Build + type + migration round trip (§11A) [NEW] | Structural breakage reaching tests |
| Machine regression (§12) | Logic regressions |
| Human validation (§13) | Behaviour the tests miss |
| Scenario testing (§16) | Technically-correct but business-wrong behaviour |
| Reversibility (§18) [NEW] | Any mistake becoming permanent |
| Deferred-task record (§15A) [NEW] | Issues being quietly fixed outside scope |

---

## 21. Overall Development Model

```
 1. Requirement
 2. Understand existing architecture
 3. Research existing solutions
 4. Evaluate available approaches
 5. Develop proposed approach
 6. Challenge / question the approach
 7. Validate security, scalability, compatibility and completeness
 8. Finalise technical direction
 9. Update project context
10. Create phase-wise development plan
11. Isolate work (worktree + database copy)                            [NEW]
12. Solution architect delegates the phase
13. Frontend / backend / API / database implementation
14. Independent review (code + security)                               [NEW]
15. Build, type check and migration round trip                         [NEW]
16. Machine-level regression testing
17. Human / developer testing
18. Fix and re-test where required
19. Complete phase
20. Move to next phase
21. Complete all phases
22. End-to-end feature testing
23. Human scenario / edge-case testing
24. Feature completion
25. Record decisions, known limits and deferred tasks in project context   [NEW]
26. Reversibility check: downgrade proven on the branch's DB copy       [NEW]
```

---

## 22. Relationship Between AI and the Engineering Process

The key principle: AI does not independently determine the architecture, requirements or
scope of the application.

The engineering process determines:
- What needs to be built
- Why it needs to be built
- Which approach should be used
- Which architecture it must follow
- Which parts of the system should change
- How the work is divided
- How the implementation is tested
- Whether the implementation is acceptable

AI is used to accelerate implementation and analysis **inside those boundaries**.

---

## 23. What to Share With a Client (ICR's Transparency Question)

The important artefacts are:

- The requirements
- The Architecture spec
- The Project Context extract
- Technical decisions
- Phase-wise development plans
- Testing approach
- Validation results
- The git history (every commit is signed and tagged with the phase it belongs to)
- The final implementation

Prompts are internal working instructions (exploratory research, feasibility, testing,
debugging, intermediate reasoning, iterative correction). Sharing them does not add
assurance; the git history and the Project Context already tell the client *what was built
and why*, with signatures.

### Recommended position

We use AI-assisted development inside a controlled engineering process. Requirements and
architecture are established first, solutions are researched and evaluated, implementation
is divided into controlled phases, different agents operate within defined boundaries, and
every phase undergoes independent review, machine regression and human validation before
the next phase proceeds. **The completed feature is then subjected to end-to-end and
business-scenario testing, every change we ship is reversible, and work in progress is
isolated from live data by construction.**

This is an accurate representation of how the system is actually being developed. It also
demonstrates that AI-generated implementation is not accepted without engineering
oversight and validation.

---

*Document path: `docs/AI_Assisted_Development_Framework_v2.md`.*
*Supersedes v1 ("AI assisted Developement Framework.odt"). Numbered sections match v1
where possible; sections marked [NEW] did not appear in v1.*
