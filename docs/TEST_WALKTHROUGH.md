# Test walkthrough — drive the recruitment → student pipeline

Reproduce the applicant-to-student conversion yourself, in the browser.

## 0. Start
- If not already running: double-click **`start-all.bat`**, wait for the browser to open.
- Sign in: **admin@example.com** / **admin123**.

## 1. Dashboard
- Note the tiles: **Students** and **Applications in pipeline** show live counts.
- "Signed in as admin@example.com · Institution Administrator".

## 2. Recruitment → Applications
- Left nav → **Recruitment** → **Applications** tab.
- You'll see **pipeline counts by stage** and a table of applications.
- Fresh test applicants **Riya Sharma** and **Tom Fisher** are at stage `applicant`.
- Click an application row (the `xxxxxxxx…` link) to open its detail.

## 3. Application detail — assess & advance
- **Record assessment** (optional): pick a decision (e.g. `recommended`), type a rationale, click **Record**. The stage moves to `under assessment`.
- **Advance stage**: pick `selected` (or `shortlisted`/`interview`), optional reason, click **Advance**.
- Watch the **Stage history** timeline at the bottom update.

## 4. Make an offer (this is the key bit)
- In the **Offer** panel: click **Create offer** → status `draft`.
- Click **Issue** → status `issued`.
- Click **Accept → create student**.
- A toast confirms: *"Student PGR-… created (same person)."*
- The application stage flips to **converted**, the offer shows **accepted**.

## 5. See the student (the payoff)
- Left nav → **Students** → the new student appears (e.g. `PGR-2026-…`, `registered`).
- Open the student → the **Person** panel says *"the same person record carried over from their
  application (one person_id across identities)"* → click the person link.
- On the **person 360**, the **Lifecycle timeline** now shows **Applicant → Student** for that person.

## 6. Make your own opportunity
- **Recruitment → Opportunities → New opportunity** → give it a title (+ optional stipend) → **Create**.
- It appears in the list with a status pill.

## 7. (Optional) Verify in DBeaver
Open the `pgr` connection → `public` schema → **View Data** on:
- `application` — the row's `current_stage` is now `converted`
- `offer` — `status` = `accepted`
- `student` — the new row; its `person_id` matches the applicant's
- `person_relationship` — the person has `applicant` (closed, `valid_to` set) + `student` (current, `valid_to` null)

## 8. Supervision & row-scoping (see security in action)
This shows that **a supervisor only sees their own students**, enforced on the server.

1. As **admin**, open a student (e.g. Marcus, `PGR-2026-1586FA`) → the **Supervisors** panel.
   - Assign a supervisor: pick a person + role → **Assign**. End one with **End** (history is kept).
2. Note how many students admin sees on the **Students** page (all of them).
3. **Log out** (sidebar footer) and **sign in as the supervisor**:
   > **elena.ford@example.com** / **super123**
4. Open **Students** — you now see **only the students Elena supervises** (not all of them).
5. Open **Supervision** (left nav) — her **caseload** lists exactly those students.
6. Sign back in as **admin** to see everything again.

The same `/api/v1/students` endpoint returns different rows depending on who's logged in — the
filter runs in the database query, so it can't be bypassed from the browser.

## 9. Progression milestones
1. Open a **student** → the **Progression milestones** panel. The first milestone (Induction Review)
   is generated automatically.
2. Click **Submit** on a milestone (marks it submitted).
3. Pick a **Panel outcome** (e.g. `progress`) → **Decide**.
   - If the outcome lets them continue, the **next milestone appears automatically** (e.g. Confirmation
     Review → Annual Progress Review).
4. See the configured flow under **Progression** (left nav): each programme's milestone definitions.

## 10. Thesis → graduation (close the lifecycle loop)
On a **student** page, the **Thesis & completion** panel runs the final stretch:
1. **Declare intention** → **Submit thesis**.
2. Pick an **Examination outcome** = `pass` → **Record outcome** (thesis becomes *approved*).
3. **Confirm completion** → **Graduate**.
   - Graduation records the award (Doctor of Philosophy), **closes the student's funding**, sets the
     student to **completed**, and **opens an `alumni` identity on the same person**.
4. Click through to the **person 360** — the timeline now shows **Student → Alumni**, the same
   person record we started with as an applicant. Loop closed.

## Notes
- Creating a brand-new *application* isn't in the UI yet (they come from the applicant portal / API),
  so use the seeded Riya/Tom, or ask me to add more test applicants.
- Everything you do is real data on PostgreSQL — visible immediately in DBeaver.
