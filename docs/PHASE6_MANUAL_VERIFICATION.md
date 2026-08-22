# Phase 6 — Manual verification guide

Everything below is **automated-tested and live-verified by me**. This guide covers what a human
should confirm, because it depends on institutional judgement, real data, or a browser.

**Start everything:** `start-all.bat` — then sign in as `admin@example.com` / `admin123`.

> ⚠️ **If a new screen or button is missing, sign out and back in.** Permissions live in the JWT
> (a deliberate performance choice), so a session started before Phase 6 will not carry
> `student.lifecycle.approve`. Tokens refresh within 15 minutes; re-login is instant.

**Load the demo data first** (idempotent, safe to re-run) from `backend/`:

```bash
PYTHONPATH=. .venv/Scripts/python.exe scripts/seed_phase6_demo.py
```
```bash
PYTHONPATH=. .venv/Scripts/python.exe scripts/seed_hesa_profile.py
```

---

## 1. Suspensions & extensions (GAP-06) — the highest day-to-day impact

**Where:** any student record → *Lifecycle changes* panel.

| # | Check | What should happen |
|---|---|---|
| 1.1 | Request a suspension (start + end + reason) | Status stays **active**; dates do **not** move; the event shows `requested` |
| 1.2 | Look at your task list | An *"Approve suspension request"* task appears |
| 1.3 | Approve it | Student becomes **suspended**; the panel shows *Originally X → now Y* with the day delta |
| 1.4 | Open the student's milestones | Undecided ones moved by the same number of days; **decided ones did not** |
| 1.5 | Record a return **earlier** than planned | Days recalculate to the actual figure, and the end date shrinks accordingly |
| 1.6 | Try a second suspension overlapping the first | Refused with an explanation naming the clashing dates |

**Judgement calls for you:**
- Is **90 days** the right supervision-meeting expectation for your institution?
- Should a **mode change** to part-time really double the remaining time? (Currently `PART_TIME_FACTOR = 2.0` in `student_record/constants.py`.)
- Should the approver be forbidden from being the requester? Both are recorded, but I did **not** block it — small teams often need the same person to do both. Say the word and I'll enforce separation.

---

## 2. Research demand → position (GAP-01)

**Where:** new **Research** nav item; then **Recruitment**.

| # | Check | What should happen |
|---|---|---|
| 2.1 | Research → Awards tab | `MRC/2026/0087` shows a **"Research system"** badge and **no edit control**; the other two are editable |
| 2.2 | Research → Demand tab | Transitions offer only legal next states (identified → approved → positioned) |
| 2.3 | Create a position from a demand (Recruitment → New opportunity) | Demand and award pickers are available |
| 2.4 | Recruitment table | **Places** column shows `filled / available` |
| 2.5 | Fill the last place | Position flips to **filled**; the demand becomes **filled** too |
| 2.6 | Try to accept another offer for it | Refused: *"already full"* |
| 2.7 | Row → **Lineage** | Award → Funder → Demand → Position → Students; a position with no demand/award shows **"not linked"** plus explicit warnings |

**Judgement call:** is the demand FSM (`identified → approved → positioned → filled`) the right shape
for your governance, or do you need an extra approval state?

---

## 3. Funding lineage & integrity (GAP-03)

**Where:** student record → *Funding lineage* panel; and the new **Funding integrity** admin page.

| # | Check | What should happen |
|---|---|---|
| 3.1 | Open a student's lineage | Project → Award → Funder → Arrangements → totals; missing hops read "not linked" |
| 3.2 | Funding integrity page | Lists only students with problems; **errors sort above warnings** |
| 3.3 | End a student's funding a year before their expected end | `funding_ends_before_expected_end` appears with the exact shortfall in days |
| 3.4 | Create two arrangements with a gap between them | `funding_gap` appears naming both dates and the day count |

> **Expected on current data:** Marcus Bell and Tom Fisher show *"no research project record"* warnings.
> That is correct — they were created before Phase 6 auto-linking. **Any student admitted from now on
> gets their project and award linked automatically.** Worth confirming you're happy to leave the
> historic ones, or whether you want a backfill script.

**Judgement calls:**
- Is a **7-day** gap the right threshold before flagging? (`MIN_GAP_DAYS`)
- Should overlapping arrangements be an error rather than a warning when contributions exceed 100%?

---

## 4. Person ↔ employee continuity (GAP-04)

**Where:** any person record → *Identities* section.

| # | Check | What should happen |
|---|---|---|
| 4.1 | Add an `employee` identity to a current PGR | **Student and employee are both current** — one person, two identities, no duplicate record |
| 4.2 | Close the employee identity | It gains an end date but **remains visible** as history |
| 4.3 | Person timeline | Shows both identities with their date ranges |

**Judgement call — worth a real decision:** inbound HR records match **deterministically only**
(email, then exact full name). Anything ambiguous becomes a task instead of merging. That is
deliberately conservative, because a wrong merge silently joins two people's records and is very hard
to undo. Confirm your HR feed carries a reliable email, or tell me what identifier to match on
(staff number? payroll ID?).

---

## 5. Statutory reporting — HESA (GAP-05)

**Where:** new **Statutory** admin page.

| # | Check | What should happen |
|---|---|---|
| 5.1 | Open `HESA_STUDENT 2026/27` | 12 mapped fields with source expressions and transforms |
| 5.2 | **Validate** | Errors listed per student per field, naming the mapping to fix |
| 5.3 | **Generate** then download | CSV with HESA-style headers; `COMDATE` as `20261001`, surnames uppercased |
| 5.4 | Add a field with a bad transform | Refused **at configuration time**, listing valid transforms |
| 5.5 | Clone to `2027/28` | New profile with the same fields; **2026/27 remains untouched and regenerable** |

**This is the one needing real domain review.** My 12 fields are a *worked example*, not a compliant
return. A HESA specialist should confirm:
- the correct field names and coding frames for your return year
- which fields are genuinely mandatory
- whether `student_led` / `opportunity_led` maps onto the right HESA value set
- what to do about students missing nationality (currently an error; a `defaultValue` can fill it)

---

## 5b. Inbound partner messages (gap matrix #12)

Signed webhooks now **apply** recognised messages, not merely log them:

| System | eventType | Effect |
|---|---|---|
| `research` | `award.created` / `award.updated` | Upserts the award, marks it externally mastered (read-only here) |
| `hr` | `employee.appointed` / `employee.updated` | Links an `employee` identity to the matching person; ambiguous → a task |
| anything else | — | Still recorded, reported as `logged_only` |

**Verified live** with real signed payloads. A malformed payload is recorded as `failed` with the
error, so it is visible for triage rather than silently dropped.

**Judgement call for you:** your partner systems must send `X-Signature` as HMAC-SHA256 of the raw
body using `APP_SECRET_KEY`, and a stable `sourceId` for idempotency. Confirm both are feasible.

---

## 6. Regression sweep (quick)

| # | Check |
|---|---|
| 6.1 | Full lifecycle still works: applicant → offer → accept → student, same person |
| 6.2 | New students now arrive with an **expected end date** derived from the position's duration |
| 6.3 | Ask PGR (Cmd+K) still answers "my tasks", "who is at risk", a student ref |
| 6.4 | Dashboard, Analytics and Enterprise 360 still load |
| 6.5 | Start the worker (`start-worker.bat`) and confirm scheduled jobs run |

---

## Known limitations (deliberate, not defects)

1. **No live partner feed is connected.** The mappings are built, tested and verified with signed
   payloads, but no Research or HR system is actually pointed at the webhook yet.
2. **Finance messages have no handler** — they are recorded (`logged_only`) but change nothing.
   Add one when you decide what an inbound Finance message should do.
3. **Historic students lack research projects**, so their lineage shows warnings (see §3).
   Everyone admitted from now on is linked automatically.
4. **The statutory profile is illustrative**, not a certified HESA return (see §5).
5. **FE for 6.2** (route badges/filters in the recruitment pipeline) was not built — route integrity
   is enforced server-side and the route already appears in reporting and exports.
6. Deployment (Docker/CI/K8s) and SSO remain parked, as agreed in Phase 4.

---

## If something looks wrong

- **A screen is missing** → sign out and back in (JWT permissions, see the note at the top).
- **A panel is empty** → run the two seed scripts above.
- **Ports already in use** → `stop.bat`, or `Get-Process python,node | Stop-Process -Force`.
- **Backend won't start** → check `backend/.env` has the Postgres DSN; migrations are at head
  `4b42a8cd5de3` (`alembic current`).
