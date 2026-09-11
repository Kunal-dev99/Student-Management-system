# 13 · Integration & webhooks — send an event out, receive one in, replay a failed one

## What it is

The platform talks to the outside world in both directions. Every business event (registration, funding change, viva outcome, etc.) queues into the **outbox**, gets delivered to the right partner adapter, retried with backoff on failure. Every inbound webhook (funder confirms payment, HR confirms employment, etc.) lands on our endpoint, normalises into a business event, and a workflow reacts. In this chapter we watch an outbound event queue and deliver, receive an inbound webhook that updates Priya's arrangement, then simulate a failed delivery and replay it.

## The clicks

**Step 01 · Open Integration.**
- **WHERE** — Sidebar → **Integration** (cable icon, ADMINISTRATION).
- **DO** — Show adapters and delivery report tiles at the top.
- **SEE** — Counts: ok / retrying / failed in the last 24 hours.
- **SAY** — *"Every partner is an adapter. Every message we send is in the outbox. Every message we receive is a row in the inbound log."*

**Step 02 · Watch an outbound event queue.**
- **WHERE** — On Priya's record (from earlier) → **Send registration notice to UKRI** button (or trigger by adjusting something on her funding).
- **DO** — Click. Back on Integration → **Outbox** tab.
- **SEE** — New row: event `student.registered`, target `UKRI adapter`, attempt 1, delivered at (timestamp).
- **SAY** — *"There it is. Between our click and the partner receiving it, the outbox handles delivery — retries on our side, not on the caller's."*

**Step 03 · Simulate an inbound webhook.**
- **WHERE** — Same page → **Inbound** tab → **Simulate webhook** (dev-only button).
- **DO** — Pick source `UKRI`, event `payment.confirmed`, entity Priya's arrangement, amount `1552`. Send.
- **SEE** — Row appears in inbound log. A business event fires — one of Priya's stipend rows flips from "Due" to "Paid".
- **SAY** — *"Webhook → normalise → business event → workflow reacts. All visible."*

**Step 04 · Force a failed delivery, then replay.**
- **WHERE** — **Outbox** tab → **Simulate failure** on a queued row (dev-only).
- **DO** — Confirm. Watch the row turn amber "retrying".
- **SEE** — Retry timeline: attempts with backoff (1 min, 2 min, 4 min).
- **SAY** — *"Nothing is fire-and-forget. If a partner is down for two hours, we retry with backoff and land the message when they come back."*

**Step 05 · Manual replay.**
- **WHERE** — Same row → **Replay** button.
- **DO** — Click. Confirm.
- **SEE** — Attempt counter increments, row flips to green "Delivered".
- **SAY** — *"When we know the partner's back and don't want to wait for the next scheduled retry, one click. Audit rows land for the replay too."*

## The line

Every message we send and receive is a first-class record — not a console log.
