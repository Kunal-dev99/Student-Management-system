# 03 · Recruitment — an application arrives and gets triaged

## What it is

The opportunity is live. Now an applicant applies to it. In this chapter we submit an application against our published posting, then switch personas (admin) and triage it through the pipeline: **submitted → shortlisted → in review → offered**. Every state change is a dated fact with an actor. The application record we create here is the same row that will become a student's record two chapters from now.

## The clicks

**Step 01 · Submit an application (applicant view).**
- **WHERE** — Public opportunity page (from previous chapter) → **Apply** button.
- **DO** — Fill the applicant form: name `Priya Nair`, email `priya.nair@example.com`, nationality `Indian`, previous degree, motivation statement, references.
- **SEE** — Progress bar showing 5/5 sections complete. Submit button enables.
- **SAY** — *"An applicant applies once. Everything they type here is the same record we'll manage all the way through their PhD."*

**Step 02 · Submit and get the reference.**
- **WHERE** — Bottom of the form → **Submit application**.
- **DO** — Click. Confirmation page appears with a reference number and a "check status" link.
- **SEE** — Reference like `APP-2026-004871`.
- **SAY** — *"The reference is the applicant's tracking id. The record is already on our side, in the pipeline."*

**Step 03 · Switch to admin. See the application land.**
- **WHERE** — Log in as admin → Sidebar → **Recruitment** → main pipeline.
- **DO** — Filter by opportunity: `PhD in Explainable Reinforcement Learning`. Find Priya Nair's row.
- **SEE** — New row with "submitted" status pill, timestamp, opportunity link, applicant name.
- **SAY** — *"The pipeline is one screen for every application across the department. New submissions come in with a submitted pill."*

**Step 04 · Open the application, decide to shortlist.**
- **WHERE** — Click Priya's row.
- **DO** — Read the application. In the top-right action bar → **Shortlist**. Add a reason: "Strong motivation statement, previous ML work matches area".
- **SEE** — Status pill flips to amber "Shortlisted". A new row appears in the state timeline on the right.
- **SAY** — *"Every state change is a dated fact with a reason. Auditors love this."*

**Step 05 · Move to "in review", assign the panel.**
- **WHERE** — Same action bar → **Send to review**.
- **DO** — Assign a reviewer (Dr. Elena Ford as supervisor is default) and any panel members. Confirm.
- **SEE** — Status pill "In review". A task appears in Elena's task inbox: "Review application from Priya Nair".
- **SAY** — *"The task fires automatically. Elena will see it when she opens the platform tomorrow morning."*

**Step 06 · Move to "offered".**
- **WHERE** — After review is done (or skip to it in the demo) → action bar → **Issue offer**.
- **DO** — Confirm.
- **SEE** — Status pill flips to blue "Offered". Application is now ready for admissions to take over.
- **SAY** — *"That's the seam. Recruitment ends here. Admissions picks up in the next chapter — same record, no data re-entry."*

## The line

Every application is a dated row on one pipeline. Every state change carries an actor and a reason.
