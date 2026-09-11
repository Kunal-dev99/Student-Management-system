# 21 · AI — Weekly review queue · watch the trace, then turn Wi-Fi off

## What it is

A deterministic scorer runs every active student against three signals — overdue milestones, funding gaps, expected end-date proximity — producing a scored table. The AI layer picks the top five with one sentence of reasoning per pick, from ids in the shortlist only. **Turn the model off** and the page still works: same evidence table on the right, top-five picks in score order on the left, chip flips from purple to grey. This is the flagship example of "AI as a layer, not a component" — and the demo moment the audience will remember.

## The clicks

**Step 01 · Open Weekly review.**
- **WHERE** — Sidebar (under `WORKSPACE`) → **Weekly review** (sparkle icon, just below "Tasks").
- **DO** — Click. Do not touch the mouse for the next 3 seconds.
- **SEE** — Gradient pane appears. Four icons light up in turn: 🗄️ database → 🧮 calculator → ✨ sparkles (pulses) → 🎨 layout.
- **SAY** — *"Every step is real server work — not a fake spinner. Fetch, weigh, wake the model, lay it out."*

**Step 02 · Point at the AI chip.**
- **WHERE** — Header of the left card — small pill next to "Top 5 to review this week".
- **DO** — Point at it. Purple = model-authored. Grey = fallback.
- **SEE** — Currently purple: ✨ **Drafted just now**.
- **SAY** — *"Every AI-touched element in this app carries this pill. The reader knows in one glance what came from the model."*

**Step 03 · Cross-reference to the evidence.**
- **WHERE** — Right column — the "Evidence" table.
- **DO** — Point at a row highlighted faint red-brown — one of the AI's picks. Then point at the matching name on the left.
- **SEE** — Every pick on the left has its exact score and reasons on the right, verbatim.
- **SAY** — *"Picks left, deterministic evidence right. The AI can't invent a name that isn't on that table."*

**Step 04 · The model-off drill — the moment of truth.**
- **WHERE** — System tray → Wi-Fi icon.
- **DO** — Turn Wi-Fi off. Back in the app, click **Run again** (top-right).
- **SEE** — Trace still ticks. Chip flips to grey ✨ **Generated offline**. Picks come back in pure score order with rule-based reasoning ("Flagged by: 2 milestone(s) overdue").
- **SAY** — *"Model off. The page still works. Chip is honest about it. That's the whole architectural commitment — AI is a layer, not a component."*

**Step 05 · Turn Wi-Fi back on, run again.**
- **WHERE** — System tray → Wi-Fi.
- **DO** — Turn it back on. Wait a beat. Click **Run again** in the app.
- **SEE** — Purple chip returns. Picks are now model-authored with warmer reasoning.
- **SAY** — *"And back. Reader sees the difference — same picks in this data, but the sentence quality improves."*

## The line

Turn the model off. The page still works. That's the test.
