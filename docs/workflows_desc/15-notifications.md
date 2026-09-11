# 15 · Notifications — set preferences, watch one fire, silence a noisy kind

## What it is

Every workflow transition and every AI signal can emit a notification. Users pick their channel per kind — in-app, email, or off — and the daily digest rolls up everything low-priority so people aren't drowned. In this chapter we open Elena's notification preferences, silence a kind she doesn't want, fire a workflow transition that would have hit her, and confirm it did NOT reach her while OTHER kinds still did.

## The clicks

**Step 01 · Show the bell.**
- **WHERE** — Top-right of any page → notification bell icon.
- **DO** — Click. Show the list of recent notifications.
- **SEE** — Rows: title, source (which workflow / which AI signal), timestamp, read pill.
- **SAY** — *"Every workflow transition we've done in this demo added a row here. Same source of truth."*

**Step 02 · Open preferences.**
- **WHERE** — User menu (bottom-left avatar) → **Notification preferences**. (Or Sidebar → Settings → Notifications tab.)
- **DO** — Show the per-kind matrix.
- **SEE** — Rows per notification kind (Milestone due, Panel decision, Funding change, Application received, etc.), columns for in-app / email / off.
- **SAY** — *"Users choose their own channel per kind. Directors get everything by email; supervisors keep it in-app."*

**Step 03 · Silence a kind.**
- **WHERE** — Find "Funding integrity reconciliation" row.
- **DO** — Set all three columns to "off". Save.
- **SEE** — Preference row shows "silenced". A confirmation toast.
- **SAY** — *"I've told the system I don't care about reconciliation dings. That preference sticks."*

**Step 04 · Fire something that would have hit that kind.**
- **WHERE** — Sidebar → **Funding integrity** → find an amber row → click **Resolve**.
- **DO** — Confirm.
- **SEE** — Reconciliation resolved. Back on the bell → no new "reconciliation" row for me. But if another notification fired at the same time (e.g. a task completion) — it did show up.
- **SAY** — *"Silenced kinds don't reach me. Other kinds still do. The preference is fine-grained, not all-or-nothing."*

**Step 05 · Show the daily digest example.**
- **WHERE** — Same preferences page → **Digest** section.
- **DO** — Point at the example digest email preview.
- **SEE** — Rolled-up summary of the low-priority notifications from the last 24 hours.
- **SAY** — *"Anything not urgent goes into the digest. Inbox stays clear."*

## The line

The system tells the right person, on the right channel, at the right cadence — and only what they asked for.
