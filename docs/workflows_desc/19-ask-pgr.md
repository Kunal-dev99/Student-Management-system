# 19 · Ask PGR — ask two questions, get an answer in 40 ms then a reasoned one

## What it is

A natural-language question box. Behind it: the **cohort resolver** figures out who the question is about ("first-years in Physics" → a concrete list), then either the **fast path** (deterministic SQL for common shapes — counts, filters, single values) or **typed tools** (for questions that need judgement) run. Answers arrive with evidence beside them — always auditable, always cite-able. In this chapter we ask one fast-path question and one that needs judgement, so the buyer sees both modes.

## The clicks

**Step 01 · Open the palette.**
- **WHERE** — Any page. Press <kbd>Ctrl</kbd>+<kbd>K</kbd> (or the top-right search icon).
- **DO** — Palette opens centre-screen.
- **SEE** — Empty text box with placeholder "Ask about PGR data…".
- **SAY** — *"One box, one keystroke. Anywhere in the app."*

**Step 02 · Ask a fast-path question.**
- **WHERE** — In the palette.
- **DO** — Type: `how many first-years are at risk?` Press Enter.
- **SEE** — Answer returns in under 100 ms with the number and a link to the filtered list.
- **SAY** — *"Fast path — this question has a direct SQL answer. Assistant doesn't need the model. Back in 40 ms."*

**Step 03 · Click through the evidence link.**
- **WHERE** — The "N students" link on the answer.
- **DO** — Click. Land on a filtered students table.
- **SEE** — Every student the number counted, right there.
- **SAY** — *"The answer isn't just a number — it comes with the list that produced it. Auditable."*

**Step 04 · Ask a judgement question.**
- **WHERE** — Palette again.
- **DO** — Type: `who might not submit on time?` Press Enter.
- **SEE** — Brief trace ticks (reading records, calling tools). Then a list of students with a one-line reason each, evidence links beside.
- **SAY** — *"This one needs judgement, so it calls the typed tools and the model composes. Evidence sits beside the sentence — every claim traceable."*

**Step 05 · Prove the evidence.**
- **WHERE** — Any student in the list → **evidence** link.
- **DO** — Click. Land on their milestones panel.
- **SEE** — Exactly the milestone / funding / date that the assistant cited.
- **SAY** — *"Every AI claim points back to the record it came from. If the assistant is wrong, you know instantly."*

## The line

Fast when the answer is arithmetic. Thoughtful when it isn't. Evidence always beside it.
