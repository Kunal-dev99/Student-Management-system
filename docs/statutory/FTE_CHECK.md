# Student FTE vs module FTE check

HESA expects a student's FTE (study intensity) in a year not to exceed the total FTE of the
modules they take that year (Demo 2 item 1.5). The platform checks this from one rule in two
places, and each institution decides how strict it is.

## Settings

**Settings → Institution policy → Statutory reporting**

| Setting | Values | Default |
|---|---|---|
| Student FTE vs module FTE check | Off, Warn, Stop | Warn |
| FTE check tolerance (percentage points) | 0–100 | 0 |
| Apply the FTE check to research students | On / Off | Off |

## Where it applies

| Place | Warn | Stop |
|---|---|---|
| Statutory return validation (per record, field `FTE`) | Warning; sign-off allowed | Error; blocks sign-off |
| Approving an intensity change | Approved, with a warning shown to the approver | Refused (409); the request stays pending |

## How it is worked out

- **Student FTE:** the intensity % on the record's date (return), or the requested new % (approval).
- **Module FTE:** the sum over the student's module enrolments in the academic year, using the
  version of the run they took; a version without its own FTE is credits ÷ the home programme's
  full-time credits (180 if not set). Withdrawn modules are left out.
- **Not checked:** students with no module FTE in the year (nothing to compare yet), and research
  students unless the research setting is on. A student is treated as taught when their programme
  type is *taught*.
- **Breach:** student FTE > module FTE + tolerance.

## Code

| Piece | File |
|---|---|
| Rule, settings, module FTE for a year | `backend/app/modules/student_record/fte_check.py` |
| Return validation | `StatutoryEngine.generate` in `backend/app/modules/exports/statutory.py` |
| Approval | `LifecycleService.approve_event` in `backend/app/modules/student_record/lifecycle.py` |
| Settings | `backend/app/modules/settings/registry.py` |
| Tests | `backend/tests/integration/test_fte_check.py` |
