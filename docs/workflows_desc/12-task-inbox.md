# 12 · Task inbox — pick up a task fired by a workflow

## What it is

Every state change we've done so far has fired tasks: "review application", "clear conditions", "form the panel", "record assessment", "invite examiners". They all land in the task inbox routed by role — anyone with that role can pick them up, so cover doesn't need a handover. In this chapter we filter down to the tasks we (and our workflow instance) generated, pick one up, complete it, and watch the workflow advance behind it.

## The clicks

**Step 01 · Open Tasks.**
- **WHERE** — Sidebar → **Tasks** (checkbox icon, under `WORKSPACE`).
- **DO** — Land on the inbox filtered by "assigned to my roles".
- **SEE** — Rows: title, entity link, due date, state pill (Open / In progress / Done).
- **SAY** — *"Every task the workflow engine emitted for me is here. Nothing arrives by memory."*

**Step 02 · Filter to a specific entity.**
- **WHERE** — Filter bar at the top.
- **DO** — Filter by entity = Priya Nair.
- **SEE** — Tasks we generated along the demo: examiner nominations, corrections review, etc.
- **SAY** — *"Every task from every workflow instance, filterable by the entity it's about."*

**Step 03 · Pick one up.**
- **WHERE** — Any open task row → **Take**.
- **DO** — Click. State pill flips to "In progress" and assignee flips to me by name.
- **SEE** — Task moves out of the shared queue into my personal one.
- **SAY** — *"Tasks route to a role first, a person second. Anyone in the role can pick one up — cover doesn't require a handover."*

**Step 04 · Complete it.**
- **WHERE** — Same task → **Mark done**.
- **DO** — Add a completion note if the task asks for one. Confirm.
- **SEE** — State pill flips to green "Done". The workflow instance behind it advances to its next state. If that new state fires more actions, new tasks appear.
- **SAY** — *"Completing a task is a state transition. The workflow moves. New tasks appear if the next transition needs one — chained work without email chains."*

**Step 05 · Show the audit link.**
- **WHERE** — Task's **History** tab.
- **DO** — Point at rows: created (by workflow), taken (by me), done (by me).
- **SEE** — Full audit of the task lifecycle.
- **SAY** — *"Even task lifecycle is audit-trailed. Who took it, who did it, when."*

## The line

If it isn't in the task inbox, no one is on the hook for it — and if the workflow emits it, it's there.
