# 24 · Settings & LOV — edit a reference value, tune a threshold, watch it take effect

## What it is

Reference data — funding types, milestone definitions, condition types, statuses, thresholds — lives here. Admins edit it directly through a CRUD UI; changes are versioned so historical records still point at the value they had when they were created. A separate **tunables registry** controls system behaviour (assistant tier, matching thresholds, workflow flags) without a code deploy. In this chapter we edit a reference value (add a new funding type), then change a tunable (bump the supervisor caseload cap) and confirm the workforce lens rerenders with the new threshold.

## The clicks

**Step 01 · Open Settings.**
- **WHERE** — Sidebar → **Settings** (gear icon, ADMINISTRATION).
- **DO** — Show the tab bar at the top.
- **SEE** — Tabs: General, Users, Roles, Assistant, Reference data (LOV), Tunables, Notifications.
- **SAY** — *"Everything that used to live in a config file lives here — editable by an admin, versioned by the system."*

**Step 02 · Add a new funding type.**
- **WHERE** — **Reference data** tab → pick "Funding types" → **+ Add value**.
- **DO** — Fill: code `industry_direct`, label `Industry direct`, active on, valid_from today. Save.
- **SEE** — New row in the LOV table with valid_from = today.
- **SAY** — *"Any new funding type is one form. And the system records who added it and when — no config file drift."*

**Step 03 · Verify it's available upstream.**
- **WHERE** — Sidebar → **Research** → open any award → **Type** dropdown.
- **DO** — Point at the new option in the list.
- **SEE** — `Industry direct` now selectable.
- **SAY** — *"Live. The new value is available everywhere the reference is used."*

**Step 04 · Change a tunable.**
- **WHERE** — Settings → **Tunables** tab → find `supervisor.caseload.cap.default`.
- **DO** — Change from 8 to 10. Add reason: "Bumped for methodology reviewers pilot". Save.
- **SEE** — Value updates; change history row lands under the tunable with actor + reason.
- **SAY** — *"System behaviour changes without a code deploy. Every change is audited with a reason."*

**Step 05 · Confirm it took effect.**
- **WHERE** — Sidebar → **Workforce**.
- **DO** — Point at any supervisor row's headroom column — recalculated against the new cap of 10.
- **SEE** — Headroom numbers larger than they were before; nobody in the red who wasn't before.
- **SAY** — *"The workforce lens picked up the new cap instantly. No cache to warm, no deploy to schedule."*

## The line

Reference data and system tunables live in the app, not in a config file — versioned, dated, audited.
