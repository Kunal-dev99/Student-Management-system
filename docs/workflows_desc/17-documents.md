# 17 · Documents — upload a chapter draft, watch it scan, download and see the log

## What it is

Documents get uploaded, virus-scanned by a background worker, stored in object storage, and linked to the business entity that owns them (a person, a milestone, a thesis, an offer condition). Every download is logged with the actor and the timestamp. Visibility follows the entity's permissions — if you can't open the entity, you can't open the file. In this chapter we upload a real PDF against Priya's Chapter 2 revision, watch the scan complete, download the file, and confirm the download shows up in the audit log.

## The clicks

**Step 01 · Find the right document panel.**
- **WHERE** — Priya's student page → **Documents** panel (or her milestone that requires the chapter revision).
- **DO** — Show the panel with any existing files.
- **SEE** — Rows with filename, uploaded by, timestamp, status pill.
- **SAY** — *"Every entity has a documents panel. Uploads live with the record they're about — not on a shared drive."*

**Step 02 · Upload a file.**
- **WHERE** — Panel → **+ Upload** button.
- **DO** — Pick a real PDF from disk (any small one). Add a description: "Chapter 2 revision, addressing panel conditions".
- **SEE** — New row appears with status "Scanning". Progress ring.
- **SAY** — *"Uploads are queued for virus scanning by a background worker — no synchronous surprise."*

**Step 03 · Watch the scan complete.**
- **WHERE** — Same row.
- **DO** — Wait a second or two. Refresh if needed.
- **SEE** — Status pill flips from amber "Scanning" to green "Available". Download link becomes clickable.
- **SAY** — *"Only clean files become downloadable. Anything flagged is quarantined and the uploader is notified."*

**Step 04 · Download the file.**
- **WHERE** — Row → **Download** icon (or the filename).
- **DO** — Click. File downloads.
- **SEE** — Browser saves it. Row's download-count increments.
- **SAY** — *"One click. But watch what happens on the audit side."*

**Step 05 · See the download in the audit log.**
- **WHERE** — Sidebar → **Audit** → filter by document id (or by Priya's entity).
- **DO** — Find the row that just landed.
- **SEE** — New audit row: action `document.download`, actor (me), timestamp, target file id.
- **SAY** — *"Every download is logged. Who read what, and when. Compliance officers love this."*

## The line

Uploads scan. Files link to the entity that owns them. Downloads log — no file drifts without a trail.
