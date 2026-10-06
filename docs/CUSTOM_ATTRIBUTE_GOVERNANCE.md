# Custom attribute governance

Implements `HESA_Custom_Attribute_Phasewise_Implementation_Plan.md` (phases 1–7) on branch
`feat/custom-attr-governance`. Custom student attributes (EAV: `student_custom_field` /
`student_custom_value` / `student_custom_value_history`, read by HESA mappings as `custom.<key>`)
are now requested, checked, approved, used, reviewed and retired under control.

## Lifecycle

```
request ─► pending ─► approved ─► active ◄──────────── restore ─┐
              │                     │  ▲                         │
              └► rejected           ▼  └ keep                    │
           (withdraw: pending only) review ─► retired ────────────┘
```

| Status | Takes values | Mappable | Read by a return |
|---|---|---|---|
| pending / approved / rejected | no | no | no |
| active, review ("live") | yes | yes | yes |
| retired | no (values kept, readable) | no | no |

Rules: requester ≠ approver (403); rejection, retirement and restoration need a reason; whoever
started a review can't retire it; an attribute mapped in an active, not-signed-off return can't be
retired (signed-off returns are frozen snapshots); nothing is ever deleted by the lifecycle — a
pending request can be withdrawn, everything else is kept. Existing attributes were migrated as
`active`. Every transition is in `student_custom_field_event` and the audit log.

## Permissions

| Permission | Granted to | Allows |
|---|---|---|
| `custom_attribute.request` | Institution Administrator, dev, PGR Administrator | request, withdraw own, see queue/catalogue/usage, start a review |
| `custom_attribute.approve` | Institution Administrator, dev | approve/reject (not own), activate, keep, retire, restore |
| `student.write` | as before | enter values for live attributes |
| `admin.configure` | as before | switch on dated history |

## Necessity check (Phase 2)

Deterministic, no AI (`student_record/custom_attr_assessment.py`): word-level duplicate check
against the core record catalogue and other attributes (exact / near), HESA match against the
effective spec packs (baseline + accepted advisory versions; a field code named in the reason
matches directly), requirement status, suggested type and coding frame. Verdict
`duplicate | review | supported | no_hesa_basis`. Runs on request (a failure never blocks the
request), re-runnable, stored in `student_custom_field_assessment`. Approving a `duplicate` needs
an override reason.

## Mapping and runtime (Phases 4–5)

`exports/custom_mapping.py`: profile-aware picker (live attributes only, HESA relevance to the
return, where already mapped), pre-save validation (errors block, warnings inform), obsolete
mapping detection — a mapping to a retired / non-live / missing attribute blocks sign-off and is
reported when a profile is cloned. Core paths are unchanged (unknown ones only warn).

`build_records(custom_keys=…)` loads only the attributes the return maps; every caller passes
them. `generate` returns `runtime` (keys loaded/skipped, values loaded, build time).

## Usage and review (Phase 6)

`student_custom_field_usage` records each real use (generate, download, sign-off — not
validate). `student_record/custom_attr_usage.py` computes, per attribute: mappings, uses, fill
rate among current students, last change, HESA field still in the newest spec. Review rules:
live mapping → protected; unmapped and < 10% filled → review; nothing for 365 days → review;
HESA field removed → review. Candidates are suggestions only.

## API (all under `/api/v1/students` unless noted)

- `POST custom-attribute-requests` · `GET custom-attribute-requests[?status=]` · `GET …/{id}` ·
  `POST …/check` · `POST …/{id}/assess` · `GET …/{id}/assessment` ·
  `POST …/{id}/approve|reject|activate` · `DELETE …/{id}` (withdraw)
- `GET custom-attributes[?status=]` · `GET custom-attributes/catalogue|dashboard|review-candidates` ·
  `GET custom-attributes/{id}` · `GET …/{id}/dependencies|usage|health` ·
  `POST …/{id}/review|keep|retire|restore`
- `GET custom-attribute-events` · existing `custom-fields/{id}/values` (GET/PUT), `…/track-history`
- `GET /hesa/specifications[/{CODE:YYYY-YY}/fields[/{FIELD}]]`
- `GET /report-profiles/{id}/record-schema|custom-attributes|dependencies` ·
  `POST /report-profiles/{id}/fields/validate`

## Migrations

`ca1_custom_attribute_governance` (status + decision columns, events table, permissions, existing
attributes → active) → `ca2_custom_attribute_assessment` → `ca3_custom_attribute_usage`. All new
tables are tenant-owned with forced fail-closed RLS. Down-migrations drop the governance columns and
tables (the attributes and their values are kept; statuses are lost and come back as `active`).

## Release gate (Phase 7) — results

| Gate | Result |
|---|---|
| Existing HESA returns unchanged | All returns on a copy of the dev DB generated with master and with this branch: identical rows (697 / 700 / 696, same 13 validation errors) |
| Cross-tenant visibility | Postgres test: all five tables have forced RLS; another tenant reads 0 rows and can't write into or update a different tenant |
| Unauthorised approval | Permission matrix (23 endpoints × reader / maker / approver) + maker-checker tests |
| Uncontrolled creation | One-step create removed; only `custom_attribute.request` creates, as pending |
| Retired data not processed | Not mappable, no value entry, not loaded by `build_records` |
| Historical values preserved | Retire/restore keep every value and dated-history row |
| Concurrent approval | Postgres test: two simultaneous approvals → exactly one decision (row lock) |
| Migrations | up → down → up on a restored dev-DB copy: clean, data preserved, tenant guard clean |
| Runtime scalability | `scripts/bench_custom_attributes.py`: 3,000 students × 100 attributes, return mapping 3 → 9.1× faster, 17.5× less memory, identical values. Governance screens over 1,000 attributes / 1M values: 3, 8 and 3 queries |

## Known limits / follow-ups

- Spec resolver falls back to the latest accepted year when a year has no accepted version of its
  own, instead of that year's baseline (pre-existing; affects compile, sign-off and the Phase 4/6
  HESA signals). Raised as a separate task.
- Pydantic body-validation errors app-wide return FastAPI's `{"detail": …}` rather than the error
  envelope (pre-existing). The governance endpoints validate in the service instead. Raised as a
  separate task.
- Review thresholds (10%, 365 days) are constants in `custom_attr_usage.py`.
