# 11 · Workflow engine — define a new cycle live

## What it is

Every cycle you've watched — admissions, milestones, suspension, thesis, corrections, completion — is a definition on the same generic engine. Not code. Data. In this chapter we create a new workflow definition end-to-end (e.g. "Ethics approval") — states, transitions, actions on transition — save it, activate it, then start an instance and drive it through. Adding a new cycle to the platform doesn't need a deploy.

## The clicks

**Step 01 · Open Workflows.**
- **WHERE** — Sidebar → **Workflows** (under ADMINISTRATION).
- **DO** — Show the list. Point at existing definitions (Onboarding, Milestone, Thesis, Correction).
- **SEE** — Rows: key, name, active toggle, version, instances count.
- **SAY** — *"Every cycle we've watched is one row here. The engine doesn't know what a milestone is — it moves state."*

**Step 02 · Create a new definition.**
- **WHERE** — Top-right → **+ New workflow**.
- **DO** — Fill: key `ethics_approval`, name `Ethics approval`, initial_state `submitted`, version `1`.
- **SEE** — Form drawer with sections for states, transitions, and actions.
- **SAY** — *"I'm going to add a whole new cycle in three minutes. No deploy."*

**Step 03 · Define the states.**
- **WHERE** — **States** section.
- **DO** — Add rows: `submitted`, `under_review`, `approved`, `rejected`, `needs_amendment`.
- **SEE** — Five state pills.
- **SAY** — *"Five states. Nothing fancy. The vocabulary is the ethics committee's own."*

**Step 04 · Define the transitions.**
- **WHERE** — **Transitions** section → **+ Add transition**.
- **DO** — Add rows:
  - from `submitted` → on `assign` → to `under_review` → action `createTask` (assignee_role: Ethics Reviewer)
  - from `under_review` → on `approve` → to `approved` → action `notify` (person: applicant)
  - from `under_review` → on `reject` → to `rejected` → action `notify`
  - from `under_review` → on `request_amendment` → to `needs_amendment` → action `createTask` (assignee: applicant)
  - from `needs_amendment` → on `resubmit` → to `submitted`
- **SEE** — Transitions listed with from/on/to/action cells.
- **SAY** — *"Every transition can fire actions. Tasks land in inboxes, notifications reach the right people. All out of the box."*

**Step 05 · Save and activate.**
- **WHERE** — Bottom → **Save**, then toggle **Active**.
- **DO** — Click both.
- **SEE** — Definition appears in the list with a green "Active" pill and version 1.
- **SAY** — *"Live. Any part of the system can now start an ethics_approval instance."*

**Step 06 · Start an instance and drive it.**
- **WHERE** — Same definition → **Instances** tab → **+ Start instance**.
- **DO** — Pick a business entity (e.g. Priya Nair's thesis). Start. Then fire transition `assign`.
- **SEE** — Instance created in state `submitted`, then moves to `under_review`. A new task lands in the Ethics Reviewer inbox.
- **SAY** — *"Data-driven state machine, right here. No developer wrote a line of ethics-specific code."*

## The line

Adding a new cycle isn't a code change — it's a definition, data-driven, versioned.
