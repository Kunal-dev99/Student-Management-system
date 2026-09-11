# 04 · Admissions — issue a conditional offer, clear the conditions, register

## What it is

The application is at "offered". Now we issue a conditional offer with typed conditions (English test, transcripts, references), watch them clear one by one, and — when the last one ticks — press **Register** and turn the applicant into a real student. Same record the whole time. Downstream, a funding arrangement will spawn against the award because the opportunity was funded.

## The clicks

**Step 01 · Open the admissions queue.**
- **WHERE** — Sidebar → **Admissions** (file-check icon).
- **DO** — Filter by "Offered". Find Priya Nair's row.
- **SEE** — Row with amber pill and a "Draft conditional offer" button.
- **SAY** — *"Applications that reach 'offered' land here. Admissions turns them into offers."*

**Step 02 · Draft the conditional offer.**
- **WHERE** — Priya's row → **Draft conditional offer**.
- **DO** — On the form, tick the conditions to attach: `English language (IELTS 7.0)`, `Certified transcripts`, `Two academic references`. Set offer expiry: 4 weeks.
- **SEE** — Three condition rows appear, each with a status pill: "Open".
- **SAY** — *"Conditions are typed, not free-text. English test, transcripts, references — three items, three clearing gates."*

**Step 03 · Send the offer.**
- **WHERE** — Bottom of the form → **Send offer to applicant**.
- **DO** — Click. Confirm.
- **SEE** — Status flips to "Offer sent". An email row appears in the outbox — the offer letter, ready to deliver.
- **SAY** — *"The offer is out. Everything from here — applicant accepting, conditions clearing — updates the same record."*

**Step 04 · Applicant accepts (simulate).**
- **WHERE** — On the offer detail → **Simulate: applicant accepts**.
- **DO** — Click. (In production this arrives via the applicant's portal or an inbound webhook.)
- **SEE** — Offer status flips to "Accepted". Three conditions still amber.
- **SAY** — *"Acceptance is one dated fact. The registration is still gated on the conditions."*

**Step 05 · Clear the conditions one by one.**
- **WHERE** — Each condition row → **Upload evidence** button.
- **DO** — Upload the applicant's IELTS certificate (any PDF), tick "Verified". Repeat for transcripts and references.
- **SEE** — Each condition pill flips to green "Cleared". The **Register** button, previously greyed, turns Redwood red on the last tick.
- **SAY** — *"Conditions clear as evidence lands. The Register button unlocks itself — no admin discretion."*

**Step 06 · Press Register — the seam.**
- **WHERE** — Top-right → **Register**.
- **DO** — Click. Confirm.
- **SEE** — Modal shows registration event: student ref auto-generated (e.g. `PGR-2026-A9F102`), start date today, expected end four years out. Confirm.
- **SAY** — *"One click. The applicant becomes a student. Same row all along."*

**Step 07 · Follow through.**
- **WHERE** — After registration → **View student** link appears.
- **DO** — Click. Land on the student's fresh record.
- **SEE** — Journey tracker showing four dots: applicant → offer holder → **registered** (highlighted) → progressing. Funding lineage already populated: the award we created feeds the arrangement that feeds Priya.
- **SAY** — *"Registered. Funding auto-attached from the award. Ready for the supervisor to onboard her."*

## The line

The seam between applicant and student is one click. Everywhere else, it's a fresh spreadsheet.
