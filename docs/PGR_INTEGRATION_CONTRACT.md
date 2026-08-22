# PGR Platform — Partner Integration Contract

**Audience:** owners of the Research, HR and Finance systems.
**Purpose:** everything your system needs to exchange data with the PGR Platform. Hand this to an
integration developer and they should not need to ask us anything.

Version 1.0 · 2026-08-22 · applies to API `v1`

---

## 1. Boundary — who owns what

The PGR Platform **integrates with** your systems; it does not replace them. This is a firm
architectural boundary, not a phase-one simplification.

| Data | System of record | PGR Platform holds |
|---|---|---|
| Research awards / grants | **Research system** | a *reference*: award ref, title, funder, dates, headline value. **No budget lines, claims, expenditure or reporting periods.** |
| Employment terms, payroll, contracts | **HR system** | only that a person *has* an employee/researcher relationship, with effective dates |
| Payment execution, invoices, ledgers | **Finance system** | a stipend *schedule* and a record of what Finance told us was paid |
| PGR lifecycle, supervision, progression, thesis | **PGR Platform** | everything |

Consequences you should expect:
- An award we received from you is **read-only in our UI**. Changes must be made in your system.
- We will never write back to your system unless a specific outbound contract is agreed (§5).
- We do not attempt to reconcile your ledger. We record what you tell us.

---

## 2. Inbound: sending us data

### 2.1 Endpoint

```
POST https://<pgr-host>/api/v1/integration/webhooks/{system}
Content-Type: application/json
X-Signature: <hex hmac>
```

`{system}` is one of `research`, `hr`, `finance`.

### 2.2 Envelope

Every message uses the same envelope:

```json
{
  "sourceId": "RS-2026-000123",
  "eventType": "award.updated",
  "payload": { }
}
```

| Field | Rules |
|---|---|
| `sourceId` | **Required.** Stable, unique per message **within your system**. Used for idempotency — see §3. |
| `eventType` | **Required.** One of the types in §4. Unknown types are recorded but change nothing. |
| `payload` | **Required.** Shape depends on `eventType`. |

### 2.3 Signature

`X-Signature` is the lowercase hex **HMAC-SHA256 of the exact raw request body**, keyed with the
shared secret we will issue you.

```python
import hmac, hashlib
signature = hmac.new(SHARED_SECRET.encode(), raw_body_bytes, hashlib.sha256).hexdigest()
```

> **Sign the bytes you actually send.** Re-serialising the JSON (different key order, whitespace or
> unicode escaping) produces a different signature and will be rejected. Compute the signature over
> the final body.

An invalid or missing signature returns **401** and the message is **not** recorded.

---

## 3. Idempotency, retries and ordering

- **Idempotency is by `(system, sourceId)`.** Re-sending the same `sourceId` returns
  `{"status": "duplicate"}` and changes nothing. This is safe and expected.
- **Retry freely.** A network failure on your side can always be retried with the same `sourceId`.
- **We do not require ordering.** If two updates for the same award arrive out of order, the last
  one processed wins. If ordering matters to you, include a version/timestamp in the payload and
  tell us — we will add a guard.
- **Nothing is lost.** Even a payload we cannot apply is recorded and visible in our integration log.

---

## 4. Event types we act on

### 4.1 Research — `award.created`, `award.updated`

```json
{
  "sourceId": "RS-2026-000123",
  "eventType": "award.updated",
  "payload": {
    "awardRef": "EP/X12345/1",
    "title": "Assistive Robotics Programme Grant",
    "startDate": "2026-04-01",
    "endDate": "2031-03-31",
    "value": "2400000",
    "currency": "GBP",
    "externalRef": "RS-INTERNAL-88231"
  }
}
```

| Field | Required | Notes |
|---|---|---|
| `awardRef` | **yes** | The funder's award number. **This is the key we match on** — it must be stable for the life of the award. |
| `title` | recommended | Defaults to `awardRef` if absent |
| `startDate`, `endDate` | recommended | ISO `YYYY-MM-DD`. Used to detect funding that outlives its award. |
| `value`, `currency` | recommended | Headline value only. Used to detect over-commitment. |
| `externalRef` | optional | Your internal id, stored for traceability |

**Effect:** creates or updates the award, marks it mastered by your system, and stamps `syncedAt`.
Fields you omit on an update are **left unchanged**.

**Send us an update when:** the award is extended, the value changes, or it closes. We do not poll.

### 4.2 HR — `employee.appointed`, `employee.updated`

```json
{
  "sourceId": "HR-EMP-99881",
  "eventType": "employee.appointed",
  "payload": {
    "email": "n.khan@uni.ac.uk",
    "givenName": "Nadia",
    "familyName": "Khan",
    "startDate": "2026-09-01"
  }
}
```

**Matching is deterministic and conservative** — email first, then exact full name:

| Outcome | What happens |
|---|---|
| Exactly one match | An `employee` relationship is opened for that person, effective `startDate`. Their existing student identity is **kept** — one person, two concurrent identities. |
| No match | A task is raised for a PGR administrator. **No person is created.** |
| More than one match | A task is raised. **No merge is attempted.** |

> **Why we refuse to guess:** a wrong merge silently joins two people's records and is extremely
> hard to unpick. We would rather queue a human decision.
>
> **Action for you:** confirm your feed sends a reliable institutional `email`. If it does not, tell
> us which identifier we should match on (staff number, payroll id, national insurance number) and
> we will add it — matching on names alone is not safe at scale.

### 4.3 Finance

**No handler is implemented yet.** Finance messages are recorded and returned as `logged_only`.

If you want us to act on payment confirmations, we need to agree: the event type, whether it
references our `stipend_payment` id or your own reference, and what should happen on a partial or
reversed payment. Until then, stipend payments are marked paid by an administrator in our UI.

---

## 5. Outbound: data we send you

We use a **transactional outbox**: a domain event is written in the same database transaction as the
change that caused it, then delivered asynchronously. This gives **at-least-once** delivery —
design your endpoint to be idempotent.

| Event | Sent to | Meaning |
|---|---|---|
| `funding.changed` | Finance | A funding arrangement was created, changed, or a stipend instalment was marked paid |
| `student.graduated` | HR, Finance | A student completed; funding has been closed |

To receive these, give us an HTTPS endpoint and we will set `INTEGRATION_<SYSTEM>_URL`. We POST the
translated message and expect **2xx**. On failure we retry with exponential backoff (2s, 4s, 8s …
capped at 5 minutes) and **dead-letter** after 5 attempts. Dead-lettered events are visible to our
administrators and can be replayed once your endpoint recovers.

Until a URL is configured, these events are translated and logged but not transmitted.

---

## 6. Responses you will receive

| `status` | HTTP | Meaning |
|---|---|---|
| `processed` | 200 | Recognised and applied. `applied` describes what changed. |
| `duplicate` | 200 | This `sourceId` was already handled. No action taken. |
| `logged_only` | 200 | Recorded, but we have no handler for this `system`/`eventType`. |
| `logged_with_error` | 200 | Recorded, but the payload could not be applied. `error` explains why; visible in our integration log for triage. |
| — | 401 | Invalid or missing signature. **Not recorded.** |
| — | 400 | Malformed envelope (e.g. missing `sourceId`). |

Note that `logged_only` and `logged_with_error` return **200**: the message was safely received. Do
not retry on these — retrying will simply return `duplicate`. Investigate instead.

---

## 7. Test plan before go-live

Run these against our test environment and confirm each result:

| # | Test | Expected |
|---|---|---|
| 1 | Send a valid award | `processed`; the award appears in our UI marked read-only |
| 2 | Re-send the identical message | `duplicate`; nothing changes |
| 3 | Send an update with a changed value | `processed`; value updates, omitted fields unchanged |
| 4 | Send with a corrupted signature | `401`; nothing recorded |
| 5 | Send an award with no `awardRef` | `logged_with_error`, visible in our log |
| 6 | Send an HR record matching a known PGR | `processed`; person shows student **and** employee |
| 7 | Send an HR record matching nobody | `queued_for_review`; a task appears for our administrators |
| 8 | Send an HR record matching two people | `queued_for_review`; **no merge** |

We will confirm items 1–8 from our side and share the integration log.

---

## 8. What we need from you

1. **An endpoint** (only if you want outbound events) — HTTPS, idempotent, returns 2xx.
2. **Confirmation of the HR matching identifier** (§4.2) — this is the one genuine open question.
3. **A decision on Finance** (§4.3) — do you want us to act on payment confirmations, or is
   administrator entry sufficient?
4. **A shared secret exchange** for the HMAC signature, through your usual secrets process.
5. **Sandbox contacts** for the test plan in §7.

---

## 9. Current status (be aware)

The mappings described here are **built, tested and verified with signed payloads**, but **no partner
system is connected yet**. Nothing is sending. This document is the contract we are ready to
integrate against, not a description of a running interface.
