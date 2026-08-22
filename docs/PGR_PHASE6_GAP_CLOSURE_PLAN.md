# Phase 6 — Vision Gap Closure

**Source:** `PGR_Vision_Implementation_Gap_Analysis.docx` (Jonathan Monk CIO vision vs implementation)
**Status:** ✅ **ALL BACKEND SLICES COMPLETE** (2026-08-22). UI for 6.3/6.4/6.6 in progress.
**Assessment date:** 2026-08-22

## Locked decisions
1. **Sequence** — 6.0 validate first, then **6.5 suspensions/extensions pulled forward**, then
   6.1 demand→position, 6.2 routes, 6.3 lineage, 6.4 employee, 6.6 statutory.
2. **Research awards** — **integration-sourced from the Research system as source of truth, with a
   manual fallback** while no integration exists. Award records stay a *reference*; we never manage
   grants.
3. **Suspensions require formal approval** — raising a suspension creates a task; an approver must
   sign off before it takes effect and before dates recalculate.
4. **First statutory profile = HESA Student return.**

---

## 0. First finding: the gaps are smaller than the analysis could see

The gap analysis was assessed against `PGR_IMPLEMENTATION.md`, not the source code. Its AMBER items
are phrased carefully — *"the reference does not prove…"* — and that caution was justified. I have
now checked the code directly. **Three of the six HIGH gaps are substantially built already.**

| Gap | Analysis said | Code actually contains | Real remaining work |
|---|---|---|---|
| **GAP-01** Research Demand → Position | "not enough detail to prove a distinct position object" | `research_opportunity` already has research_area, department, principal_supervisor, stipend + currency, eligibility, start_date, **expected_duration_months**, **positions_available**, status FSM | Only the **upstream link**: research award/project + places-filled tracking |
| **GAP-02** Two entry routes | "does not prove distinct funded-position and student-led journeys" | **`ApplicationRoute` enum exists** (`opportunity_led` \| `student_led`), `application.route` is a stored column, `research_opportunity_id` is nullable, and `proposal_document_ref` + `research_area_id` support the student-led path | **Model is complete.** Needs enforcement rules, an end-to-end test, and UI for the student-led path |
| **GAP-03** Award ↔ funding lineage | "does not prove a complete traceable lineage" | `funding_arrangement` has cost_centre/project_code/funder_reference; `funding_source` exists | **Genuine gap** — `research_project` has only topic + group, with **no award entity and no FK chain** |
| **GAP-04** Person ↔ employee | "does not establish the depth of employee identity handling" | `PersonRelationshipType` **already includes `employee` and `researcher`**; `person_relationship` has valid_from/valid_to/source_system; `transition_identity()` performs history-preserving swaps | Mostly **verification + a small API**; the mechanism exists |
| **GAP-05** Statutory as evolving layer | "CSV exports present, needs configurability" | 2 export kinds with columns hard-coded in Python | **Genuine gap** — needs a mapping/versioning layer |
| **GAP-06** Suspension / extension | "listed as not started" | `StudentStatus` **already has `on_leave`, `suspended`, `terminated`** | **Genuine gap** — states exist but there are no **periods, reasons, or date recalculation** |

**Consequence for planning:** GAP-02 and GAP-04 are largely *evidence* problems, not build problems.
Doing that verification first (Slice 6.0) is cheap, and it prevents building things twice. This
matches the analysis's own recommended step 1: *"Validate the current domain model against the six
priority gaps."*

---

## 1. Guardrails (from the analysis — binding on every slice)

The platform **integrates with** enterprise systems; it does not replace them.

- ❌ Do not become **grants management** → `ResearchAward` is a *reference* record (award ref, title,
  funder, dates, value) **sourced from the Research system**, never managed here
- ❌ Do not become **Finance/payroll** → we schedule and record stipends; Finance disburses
- ❌ Do not become **HR** → we record the employee *relationship*, not employment terms
- ❌ Do not recreate an **undergraduate SIS**
- ❌ Do not make an **LLM the source of truth** for academic or financial decisions
- ✅ Keep the PGR lifecycle and person identity as the central domain
- ✅ **No new generic AI features** until the gaps close (analysis §1, explicit)

---

## 2. Phase 6 slices

Ordered to follow the analysis's recommended delivery order, with verification pulled to the front.

### Slice 6.0 — Validate & evidence ✅ **COMPLETE (2026-08-22)**
Prove what already exists so effort goes where it is genuinely needed.

| Task | Status | Evidence |
|---|---|---|
| **BE-6.0.1** End-to-end test for the **student-led** route | ✅ | `tests/integration/test_vision_gaps.py::test_route_b_student_led_reaches_student` — person → application (`student_led`, **no** opportunity, with proposal) → offer → issue → accept → `student`, same `person_id` |
| **BE-6.0.2** End-to-end test for **person → employee continuity** | ✅ | `test_pgr_becomes_employee_without_a_second_identity` — one `person_id`, `student` **and** `employee` both current simultaneously, `applicant` retained as history; plus effective dates + `source_system` asserted |
| **BE-6.0.3** Route-integrity rules | ✅ | `recruitment/service.create_application` now enforces: `opportunity_led` **requires** a real opportunity; `student_led` **must not** carry one and **must** have a research area or proposal. 3 tests |
| **DOC-6.0.4** Re-issue the gap matrix with code evidence | ✅ | This document + `PGR_IMPLEMENTATION.md` §14 |

**Result: GAP-02 and GAP-04 are CLOSED at the model/behaviour level.** 8 new tests; suite **138 passing**.
Remaining for those two gaps is presentation only (route badges/filters in the UI, an employee-relationship
endpoint) — moved into slices 6.2 and 6.4 respectively.

> **A rule change worth noting:** an existing test created a `student_led` application with neither a
> research area nor a proposal, purely as scaffolding. That is now rejected — a student-led
> application is *defined* by carrying research intent — so the test's setup was corrected rather
> than the rule relaxed.

---

### Slice 6.1 — Research Demand → PGR Position *(GAP-01)* ✅ **BACKEND COMPLETE (2026-08-22)**
The vision starts *before the student exists*: the institution knows it needs a researcher because of
an award or planned activity.

New module **`app/modules/research/`** owning `research_award` + `research_demand`.

| Task | Status | Evidence |
|---|---|---|
| **BE-6.1.1** `research_award` reference table | ✅ | award_ref (unique), title, funder → `funding_source`, PI, dates, value, currency, status, plus `source_system`/`external_ref`/`synced_at`. **Externally-mastered awards are read-only** — a PATCH returns 409 *"maintained in the Research system"*, and the API exposes `readOnly` so the UI hides the edit form. `upsert_from_research_system()` is the integration entry point. Deliberately no budget lines/claims/expenditure — **not grants management**. |
| **BE-6.1.2** `research_demand` | ✅ | Optional award link (strategic demand is legitimate), research area, department, requested places, justification, target start, FSM `identified → approved → positioned → filled` (+ `withdrawn`), enforced with a helpful error listing the allowed moves. |
| **BE-6.1.3** Position provenance + places | ✅ | `research_opportunity` gains `research_demand_id`, `research_award_id`, `positions_filled`. Accepting an offer **takes a place**; an over-filled position returns 409; the position auto-moves to `filled`; and when every position answering a demand is full the **demand itself becomes `filled`**. |
| **BE-6.1.4** Lineage endpoint | ✅ | `GET /opportunities/{id}/lineage` → award → funder → demand → position (with places remaining) → applications → students, and a **`gaps` list** that names broken links rather than hiding them. |
| **BE-6.1.6** Derived expected end date | ✅ | *(folded in from 6.5)* Accepting an offer now derives `expected_end_date` from `expected_duration_months`, doubled for part-time, and seeds `original_expected_end_date` — so suspensions finally have a baseline to adjust. Month arithmetic clamps to month length. |
| **FE-6.1.5** UI | ✅ | New **`/research`** page (Tabs: Research demand \| Awards) with FSM-aware transitions, raise-demand and record-award dialogs; externally-mastered awards carry a muted **"Research system"** badge and expose no edit control. Recruitment gains demand/award pickers, a **Places** column (`filled/available` + `full` badge), and a per-row **Lineage** dialog rendering award → funder → demand → position → students, with `gaps` shown as warnings. "Research" nav item added. |

**12 tests**; suite **163 passing**. Migration `62447855ae7e`.

**Verified live:** award `EP/LIVE/2026` (funder UKRI EPSRC) → demand `positioned` → position with 1 place
→ lineage returned the complete chain with **no gaps**.

> **Bug caught by the tests:** the new `researchDemandId`/`researchAwardId` were added to the model but
> not to `OpportunityCreate`, so Pydantic silently dropped them and positions were created unlinked.
> Fixed, and `positionsFilled` is now exposed on `OpportunityOut` too.

---

### Slice 6.2 — Two entry routes, made explicit *(GAP-02 remainder)*
| Task | Done-when |
|---|---|
| **FE-6.2.1** Route selector on application creation, with the correct fields per route (position picker vs research area + proposal upload) | Both routes creatable from the UI |
| **FE-6.2.2** Route shown as a badge throughout the pipeline; filter applications by route | A user can see at a glance how each applicant arrived |
| **BE-6.2.3** Route carried into reporting (Enterprise 360 student lens + statutory extract) | Route appears in exports and analytics |

**Status: BE-6.2.3 ✅** — `entryRoute` now appears on the Enterprise 360 student lens and as an
`entry_route` column on the statutory export (test asserts both). FE route selector/badges remain;
route *integrity* is already enforced server-side from Slice 6.0, so this is presentation only.

---

### Slice 6.3 — Research ↔ Award ↔ Funding ↔ Student lineage *(GAP-03)*
The single trace the CIO asked for: **Student → Research Project → Research Award → Funder → Funding Arrangement → Stipend.**

| Task | Done-when |
|---|---|
| **BE-6.3.1** Extend `research_project`: link to `research_award`, research area, and the originating position; add project dates | A student's project can name its award |
| **BE-6.3.2** Link `funding_arrangement` → `research_award` (optional) alongside the existing funder reference | Arrangements can be attributed to an award |
| **BE-6.3.3** **Lineage endpoint** `/students/{id}/funding-lineage` returning the full chain with every hop, and flagging breaks ("arrangement has a project code but no linked award") | One call answers "where does this student's money come from?" |
| **BE-6.3.4** Funding **integrity checks**: gaps between arrangements, overlaps, funding ending before expected end date, stipend total vs award value | Each issue is reported with the dates that caused it |
| **FE-6.3.5** Lineage view on the student record (chain + integrity warnings) | Visible, explainable trace |

**Status: BACKEND ✅ (12 tests).** `research_project` links to award/area/originating position with
dates; `funding_arrangement` links to award through create *and* change; `GET
/students/{id}/funding-lineage` returns every hop with per-arrangement paid/committed roll-up and a
`complete` flag. **Integrity checks**: `funding_gap` (days + both dates), `funding_ends_before_expected_end`
(shortfall days), `funding_overlap` (only when contributions exceed 100%), `funding_outlives_award`,
`funding_precedes_award`, `arrangement_award_unlinked`, `stipend_exceeds_award_value`, `no_project` —
each carrying the values that produced it. **Cohort view** `GET /reports/funding-integrity` lists every
student whose chain has a problem, errors first, row-scoped — *the question with no screen*. Accepting
an offer now creates the research project already linked to the position's award, so lineage populates
with no manual step.

**No new dependencies.** The gap analysis suggested pandas + intervaltree; for the handful of
arrangements a student holds, a sorted list and plain date arithmetic is clearer, faster and easier
to audit.

---

### Slice 6.4 — Person ↔ Employee/Researcher depth *(GAP-04 remainder)*
| Task | Done-when |
|---|---|
| **BE-6.4.1** Endpoints to open/close `employee` and `researcher` relationships with effective dates + source system | A PGR can become an employee without a second identity |
| **BE-6.4.2** HR adapter maps inbound employee records onto an existing `person` by deterministic match; unmatched records are queued, never auto-merged | Ambiguity becomes a task, not a silent merge |
| **BE-6.4.3** Enterprise 360 workforce lens reads the relationship (currently person-id based) | Workforce lens reflects real employee relationships |
| **FE-6.4.4** Person timeline shows concurrent relationships with dates | Student + employee visible together |

**Status: BACKEND ✅ (7 tests).** `POST /persons/{id}/relationships` opens a relationship **without
closing** existing ones, so student + employee are concurrent under one person_id;
`POST .../{type}/close` ends one while keeping the record. HR matching is **deterministic only**
(email, then exact full name) — anything ambiguous or unmatched becomes a **task**, never a merge,
because a wrong merge silently joins two people's records and is very hard to undo. The Enterprise 360
workforce lens already read the relationship (verified, no change needed).

---

### Slice 6.5 — PGR exception lifecycle *(GAP-06)* ✅ **BACKEND COMPLETE (2026-08-22)**
Suspensions and extensions materially change research timelines — the highest *day-to-day* functional gap.

| Task | Status | Evidence |
|---|---|---|
| **BE-6.5.1** `student_lifecycle_event` | ✅ | Types `suspension`/`extension`/`mode_change`; statuses `requested`/`approved`/`rejected`/`cancelled`; reason **required**; requester *and* approver both recorded; `days_applied` stores the exact arithmetic. `student.original_expected_end_date` added as an immutable baseline. |
| **BE-6.5.2** Timeline recalculation | ✅ | `student_record/lifecycle.py`. Recomputes **from the baseline** (`original + Σ days_applied`) rather than nudging incrementally, so it is idempotent and a rejected/corrected event leaves no residue. Shifts **undecided milestones only** — a decided milestone is a historical fact. Returns the itemised breakdown and a plain-English note. |
| **BE-6.5.3** Transitions + guards + auto-return | ✅ | Approval required before anything moves; overlapping suspensions → 409; backwards dates and missing reasons → 422; double approval → 409; worker `_auto_return_suspensions()` returns students whose window has passed. |
| **BE-6.5.4** Paused students are not chased | ✅ | Scheduler skips funding-expiry flagging and overdue-task escalation for `suspended`/`on_leave` students (milestone generation already filtered them). |
| **FE-6.5.5** UI panel | ✅ | `features/lifecycle/LifecyclePanel.tsx` on the student record: status badge, **original vs adjusted end date with the delta** ("Originally 2030-02-19 → now 2030-04-02 · +42 days"), event table with reasons and days applied, request dialog whose fields swap by event type, approve/reject gated on `student.lifecycle.approve` (non-approvers see "Awaiting approval"), and a Record-return action when suspended. The Record panel's status badge now turns `warning` when suspended instead of always `success`. |

**13 tests**; suite **151 passing**. Migration `bc175392603e`. New permission
**`student.lifecycle.approve`** — separate from `student.write`, because approving is what moves dates.

**Verified live:** requested (nothing changed) → approved (91 provisional days) → returned early on
15 Oct → **corrected to 44 days**, expected end 2029-08-21 → 2029-10-04, 1 undecided milestone shifted.

> **Data gap found while testing:** students created by accepting an offer never get an
> `expected_end_date`, so there is nothing for recalculation to move. `research_opportunity` already
> carries `expected_duration_months` — the admission flow should derive the expected end from it.
> **Folded into Slice 6.1** (it belongs with the position model).

---

### Slice 6.6 — Statutory reporting as an evolving layer *(GAP-05)*
Treat HESA as an **external specification**, not core domain logic.

| Task | Done-when |
|---|---|
| **BE-6.6.1** `report_profile` + `report_field_mapping` — versioned, effective-dated: profile (e.g. HESA Student 2026/27), target field, source expression, transform, required flag | Adding a return means adding configuration, not code |
| **BE-6.6.2** **Mapping engine** resolving source expressions against the read models, with per-field transforms and defaults | Export produced entirely from configuration |
| **BE-6.6.3** **Validation rules** per profile (required, allowed values, cross-field); export produces a validation report before the file | Errors listed per student per field, with the record link |
| **BE-6.6.4** Export profiles versioned by academic year; regenerating a prior year uses that year's mapping | A past return reproduces byte-identically |
| **FE-6.6.5** Profile admin UI (view/clone/edit mappings) + validation report view | An administrator can adjust a return without a developer |

**Status: BACKEND ✅ (10 tests).** `report_profile` + `report_field_mapping`, versioned by
`(code, academic_year, version)`. The engine (`exports/statutory.py`) resolves a **dotted path** over
one flat per-student record — deliberately *not* an expression language, since executable
configuration is both a security and an operations problem. 8 pure transforms; an unknown transform is
refused **at configuration time**, not at generation. Validation reports errors **per student per
field**, naming the `sourceExpression` to fix, and `GET .../validate` produces the report without
generating a file. `POST .../clone` carries a return to a new academic year leaving the prior year
regenerable.

**Worked example seeded** (`scripts/seed_hesa_profile.py`): HESA Student 2026/27, **12 mapped fields,
3 rows generated, 0 validation errors — entirely from configuration, no Python per return.**

---

## 3. Phase 7 — Python intelligence *(only after gap closure)*
Per the analysis: deterministic and explainable first, ML later.

| Priority | Capability | Approach |
|---|---|---|
| HIGH | Funding lineage & integrity validation | pandas + interval logic (largely delivered by BE-6.3.4) |
| HIGH | Timeline recalculation | dateutil + rules (delivered by BE-6.5.2) |
| HIGH | Position/demand validation | pydantic + rules |
| HIGH | Statutory mapping engine | pydantic + pandas (delivered by 6.6) |
| MEDIUM | Research/supervisor matching with explainable scores | sentence-transformers + scikit-learn |
| MEDIUM | Relationship graph visualisation | networkx |
| MEDIUM | Risk enhancement | only once deterministic signals are stable |

**Note:** four of the seven "Python opportunities" are delivered as a by-product of Phase 6 slices —
they are the *same work*, not an extra phase. Only matching, graph views and ML risk are additional.

---

## 4. Recommended sequence

```
6.0 Validate & evidence      (small)   ← start here; may close 2 gaps outright
      ↓
6.5 Exception lifecycle      (medium)  ← recommended pull-forward: daily operational impact
      ↓
6.1 Demand → Position        (medium)
      ↓
6.2 Two routes explicit      (small)
      ↓
6.3 Award/funding lineage    (med-large)
      ↓
6.4 Person ↔ employee        (small-med)
      ↓
6.6 Statutory mapping engine (large)
      ↓
7.x Python intelligence (matching, graph)
```

**Where I differ from the analysis's order:** it places suspensions sixth. I recommend second,
because it is the only gap that affects students *every week*, and because milestone-date
recalculation touches progression — better to land it before more objects hang off the schema.
Everything else follows the analysis's ordering.

---

## 5. Open questions
1. **Sequence** — accept my pull-forward of 6.5 (suspensions), or keep the analysis's order?
2. **Award source of truth** — should `research_award` be *read-only from the Research system* via the
   integration hub, or manually creatable in the PGR platform when no integration exists?
3. **Statutory scope** — is HESA the first target profile, and is there a specific return year to model?
4. **Suspension approval** — does a suspension need a formal approval step (task + approver), or is it
   recorded by an administrator as fact?
5. Does this phase need to be **demonstrable to the CIO** at a checkpoint — which would argue for
   doing 6.1/6.2 (visible lineage) before 6.5 (operational depth)?
