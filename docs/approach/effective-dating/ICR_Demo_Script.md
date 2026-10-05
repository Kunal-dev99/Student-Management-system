# Effective dating — ICR demo script (5 Oct 2026)

Internal. Use with `Effective_Dating_Asked_vs_Built.pdf` (share that one with ICR).
Log in as the institution admin (Default Institution). About 20 minutes.

## Demo data (already set up in the dev database)

| Who | Ref | Open at | Story |
|---|---|---|---|
| Alex Dated (demo) | ED-DEMO-01 | `/students/98f75b69-6d86-44b8-9e0a-04902042c84d` | Alistair's example: live Aug 2025, 60% from 5 Jan 2026, interrupted 2 Mar, back 1 Jun, interrupted again 7 Sep 2026 |
| Sam Transfer (demo) | ED-DEMO-02 | `/students/b76e6065-0538-4d90-8ad5-76975a4c39fa` | ICR PhD → MD(Res) on 2 Feb 2026 |
| HESA Student Return 2025/26 | — | Statutory → HESA_STUDENT 2025/26 | Cloned from 2026/27 for this demo; STULOAD mapped to the day-weighted load |

Or search for "ED-DEMO" in Students.

---

## 1. History "like an HR system" (items 1.4 / 4.3)

1. Open **ED-DEMO-01** → **Journey** tab → **Lifecycle changes**.
   - Show the four approved changes, each with requester, approver and reason.
   - Show that the expected end moved (originally 30 Sep 2028 → now Jan 2031) and why.
2. Go to the **Dated history** tab.
   - The timeline: status active → suspended → active → suspended, intensity 100% → 60%. Each entry shows who recorded it and when.
   - Say: nothing is overwritten. A wrong entry is corrected; the old one is kept, superseded.
3. Point out that the header still shows today's value: **Suspended**, part time. Lists and search read that, so they're unchanged.

## 2. Alistair's 1 August example: "as at" (item 1.12)

Stay on **Dated history** → **As of a date**.

| Type the date | It shows | Say |
|---|---|---|
| 2025-08-01 | Active, full time | Live in August |
| 2026-04-01 | Suspended, 60% | Inside the March–June interruption |
| 2026-07-31 | Active, 60% | Back since June; September is next year |
| today | Suspended | Interrupted again in September |

## 3. The return reads the history (items 1.12 and 1.13)

1. **Statutory** → **HESA Student Return 2025/26** → **Validate**: 0 errors.
2. Click **Review workbook (Excel)**. In the Return sheet, filter OWNSTU on `ED-DEMO`:
   - **ED-DEMO-01:** STULOAD **62**, which is day-weighted. 100% to January, then 60%, nothing while interrupted. MODE 02 (part time).
   - **ED-DEMO-02:** **two rows**, PhD 01/08/2025–01/02/2026 and MD(Res) 02/02/2026–31/07/2026. This is the programme change ICR said was missing (1.13).

## 4. Snapshot "as known at" and protecting a signed-off return (item 1.12)

This changes demo data. Use **Unsign** afterwards if you want to repeat it.

1. In the 2025/26 return → **Sign off**. Set **Snapshot as at** = 2026-07-31 and add a note. Confirm.
2. Show **Frozen returns**: v1, as at 2026-07-31. Download its Excel.
3. Go back to **ED-DEMO-01** → **Journey** → **Lifecycle changes** → **Request…**. Request an **intensity change** to 80% from **2026-06-15**, inside the signed-off year.
   - The pending row shows the warning that it reaches the signed-off 2025/26 return.
4. **Approve** it. You can because your role has the returns permission; a PGR Administrator would be refused.
5. **Statutory** → 2025/26: the amber box says **1 student changed since sign-off**. Expand it to see ED-DEMO-01.
6. Re-download **v1**: unchanged. STULOAD is still 62, because late changes don't bleed into a signed-off return.

## 5. Module FTE check (item 1.5)

1. **Statutory** → **HESA Student Return 2026/27** → **Validate**.
   - **17 warnings**, field **FTE**.
   - Most are MSc Clinical Oncology students at **83.33%**. They take ONC501–504 (66.67%), and the dissertation adds 16.67%. But they aren't enrolled on the core module **RES701**, so they're genuinely 30 credits short.
   - The MSc Clinical Neurology students show 50%: that programme has no total credits set, so its dissertation can't be worked out.
   - The dissertation counts automatically: it's worth the credits the programme's core modules don't cover.
2. **Settings** → **Institution policy** → **Statutory reporting** → set **Student FTE vs module FTE check** to **Stop**.
3. Validate again: the same 17 are now **errors**, and sign-off is blocked. Mention the tolerance setting and that research students are skipped by default.
4. Set it back to **Warn**.

## 6. Versions and units of assessment (items 1.3 and UOA): quick tour

- **Settings** → **Programmes** → a programme → **Versions**: each cohort is pinned to its version (CMA), and a version with students can't be edited.
- In the same place, the modules editor shows **module versions**, each with credits and FTE.
- **Settings** → **Units of assessment**: the list. A supervisor's UOA is dated on their person page.

## 7. Close

Show "Still to do" in the PDF:
- amend and resubmit (1.11)
- XML (1.10)
- attendance and VLE evidence
- FEESTAT codes

Ask ICR for:
- the FEESTAT coding
- which engagement evidence feeds they want

---

### Reset after the demo (optional)

- Statutory → 2025/26 → **Unsign**.
- The demo students and the 2025/26 profile can stay; they're labelled "(demo)".
