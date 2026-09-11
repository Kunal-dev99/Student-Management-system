# 16 · Audit — answer an auditor's question by URL, not by spreadsheet

## What it is

Every write, every state change, every login, every export — one immutable log row with actor, entity, action, timestamp, request id, before/after payload. Filter by any axis (who did what, or what was done to whom); export a slice; share a URL that preserves the filter. In this chapter we play out a real auditor's question — *"who registered student PGR-2026-A9F102, and did the funding attach correctly?"* — and answer it with two filters and a copied URL.

## The clicks

**Step 01 · Open Audit.**
- **WHERE** — Sidebar → **Audit** (under ADMINISTRATION).
- **DO** — Land on the table with today's activity.
- **SEE** — Rows: time, actor, action, entity, before/after link.
- **SAY** — *"Every write in the system is here. Nothing bypasses this log."*

**Step 02 · Filter by our new student.**
- **WHERE** — Filter bar → **Entity type = Student**, **Entity ID/ref = PGR-2026-A9F102** (Priya's ref from chapter 04).
- **DO** — Apply.
- **SEE** — Rows: registered by (admin), supervisors added, funding arrangement auto-created, milestones auto-created — all chronological, all from this demo.
- **SAY** — *"Every state change on Priya's record. Who moved her, when, with what request id."*

**Step 03 · Zoom into one row.**
- **WHERE** — Any row → click.
- **DO** — Show the before/after payload preview.
- **SEE** — Two JSON blobs side by side — the field values before and after the change.
- **SAY** — *"Before and after. If someone asks 'what changed?', it's literally right there."*

**Step 04 · Change axis to actor.**
- **WHERE** — Same filter bar.
- **DO** — Clear entity filter; set **Actor = admin@example.com**, **Date = today**.
- **SEE** — Every action that admin took today — award created, opportunity published, application shortlisted, offer issued, student registered.
- **SAY** — *"The other axis. Auditors ask "who did what today?" — this is the answer."*

**Step 05 · Send the auditor a URL, not a spreadsheet.**
- **WHERE** — Browser address bar.
- **DO** — Copy the current URL. Paste it into an email to the auditor.
- **SEE** — URL contains the filter — when the auditor opens it, they see exactly the same rows.
- **SAY** — *"The auditor doesn't get a spreadsheet — they get a live filtered URL. If new data lands, they see it too."*

## The line

The auditor doesn't send you a spreadsheet request — you filter this page and send them the URL.
