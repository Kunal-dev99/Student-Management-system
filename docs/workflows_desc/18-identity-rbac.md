# 18 · Identity & RBAC — create a user, assign a role, watch the UI change for them

## What it is

Users have roles; roles have permissions; permissions gate endpoints on the backend AND controls in the UI. When a user logs in, their JWT carries the tenant and the permission set, and the frontend uses that same set to grey out buttons the user can't act on. In this chapter we create a new user (a wellbeing officer), give them a role, log in as them, and confirm they see the sidebar, buttons and pages that role gets — and nothing else.

## The clicks

**Step 01 · Open Users.**
- **WHERE** — Sidebar → **Settings** → **Users** tab (or `/settings/users`).
- **DO** — Land on the users table.
- **SEE** — Rows with role chips and active/inactive pills.
- **SAY** — *"Users have roles. Roles have permissions. The JWT carries the whole set — one auth check on the way in."*

**Step 02 · Create a new user.**
- **WHERE** — Top-right → **+ New user**.
- **DO** — Fill: email `wellbeing@example.com`, name `Sam Cooper`, temporary password, is_active on. Save.
- **SEE** — New row appears with no role chip yet.
- **SAY** — *"Just an account. No permissions yet — they can't even open the app."*

**Step 03 · Assign a role.**
- **WHERE** — On the new user's row → **Roles** column → **+ Assign role**.
- **DO** — Pick `Wellbeing Officer`. Save.
- **SEE** — Role chip appears. Permissions summary panel updates: `student.read`, `notes.write`, `case.escalate`.
- **SAY** — *"Assigning a role assigns its permissions. No per-user permission management to drift out of sync."*

**Step 04 · Open a role to show its permissions.**
- **WHERE** — Settings → **Roles** tab → open `Wellbeing Officer`.
- **DO** — Show its permission list.
- **SEE** — Permission codes like `student.read`, `notes.write`, `case.escalate` — no `funding.change`, no `audit.read`.
- **SAY** — *"Permissions name actions, not screens. A new screen inherits the right permissions automatically."*

**Step 05 · Log in as the new user, see the different UI.**
- **WHERE** — Log out. Log back in as `wellbeing@example.com`.
- **DO** — Show the sidebar.
- **SEE** — Sidebar is smaller — no `/audit`, no `/funding`, no `/statutory`. On student pages, no funding change controls, no state-change buttons.
- **SAY** — *"The permission set drives the UI. Buttons the user can't act on aren't there. No red-flag 403s at click time."*

## The line

The permission code gates the endpoint AND the button — one system of truth for what a user can do.
