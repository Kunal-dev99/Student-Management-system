"""The composer — question in, validated render spec out.

Two phases, deliberately separated:

**Plan.** The model is shown the data-function catalogue and asked which it needs. It may
go round up to `MAX_PLAN_ROUNDS` times, because real questions are sequential: resolving
"Marcus" to an id has to happen before his funding can be fetched. Each round sees the
results so far, so the second round is an informed one.

**Compose.** The model is shown the collected results and asked for a `Composition` —
blocks only, drawn from the catalogue. It is told, repeatedly, that every number must come
from the results it was given.

If the spec fails validation it gets exactly one repair attempt with the validation errors
attached. A second failure is reported as a failure rather than retried indefinitely; a
model that cannot produce valid JSON twice will not produce it on the fifth try, and the
user would rather have an honest error than a spinner.

Every run is recorded in `composer_run` whether it succeeded or not.
"""
from __future__ import annotations

import json
import logging
import re
import time
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.llm.governance import check_budget, check_enabled, redact
from app.core.llm.provider import LLMError, get_provider
from app.core.principal import Principal
from app.modules.composer import functions as fx
from app.modules.composer import grounding
from app.modules.composer.blocks import BLOCK_TYPES, Composition
from app.modules.composer.models import ComposerRun

logger = logging.getLogger("pgr.composer")

MAX_PLAN_ROUNDS = 3
MAX_CALLS_PER_ROUND = 5
# A cohort-wide function can return every supervisor in the institution. Feeding all of
# them to the model costs tokens twice — once going in, and again when it dutifully tries
# to echo every row into a table — which overruns the completion budget mid-JSON. Cap the
# list and tell the model it was capped, so it can say so rather than silently dropping
# rows or truncating its own output.
MAX_ITEMS_PER_RESULT = 25
COMPOSE_MAX_TOKENS = 8000


def _fallback_render(question: str, collected: dict[str, Any], max_rows: int) -> dict:
    """A deterministic, boring, always-shippable render of the data we already have.

    Called when the model fails to produce a valid, grounded spec on both attempts. Uses no
    model output at all — every value comes straight from the function results. The point
    is that the user never stares at "something went wrong": they see the data that came
    back, laid out plainly.
    """
    blocks: list[dict] = []
    # Group each function result into its own table where the shape allows; a scalar or
    # object gets a KPI row of its top-level fields instead.
    for label, value in list(collected.items())[:6]:
        source = [label.split("(")[0]]
        if not value or (isinstance(value, dict) and value.get("error")):
            continue

        # Truncated list → the items inside; anything else stays as-is.
        if isinstance(value, dict) and value.get("_truncated"):
            value = value.get("items") or []

        if isinstance(value, list) and value and isinstance(value[0], dict):
            columns = list(value[0])[:8]
            rows: list[list[Any]] = []
            for record in value[:max_rows]:
                rows.append(
                    [
                        _stringify(record.get(column)) for column in columns
                    ]
                )
            blocks.append({
                "type": "table",
                "title": source[0].replace("_", " ").capitalize(),
                "source": source,
                "columns": [c.replace("_", " ") for c in columns],
                "rows": rows,
            })
        elif isinstance(value, dict):
            items: list[dict] = []
            for key, entry in list(value.items())[:6]:
                if isinstance(entry, (dict, list)):
                    continue
                items.append(
                    {"label": key.replace("_", " ").capitalize(), "value": _stringify(entry)}
                )
            if items:
                blocks.append({
                    "type": "kpi_row",
                    "title": source[0].replace("_", " ").capitalize(),
                    "source": source,
                    "items": items[:4],
                })

    if not blocks:
        blocks.append({
            "type": "narrative",
            "body": "The functions ran but returned no rows to lay out.",
        })

    blocks.insert(0, {
        "type": "alert_banner",
        "tone": "info",
        "body": (
            "Showing the data plainly. The composer could not choose a layout for this "
            "question — the numbers below are exactly what the functions returned."
        ),
    })
    return {
        "title": question[:80],
        "subtitle": "Plain-data fallback",
        "blocks": blocks,
        "rationale": "Deterministic fallback used because the layout model did not return "
                     "a valid, grounded composition.",
    }


def _stringify(value: Any) -> Any:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float)):
        return value
    return str(value)[:120]


def _guessed_ids(args: dict[str, Any]) -> list[str]:
    """Arguments named like ids whose value is not one — i.e. a name the model made up."""
    bad: list[str] = []
    for key, value in args.items():
        if not key.endswith("_id") or value in (None, ""):
            continue
        try:
            uuid.UUID(str(value))
        except (ValueError, AttributeError, TypeError):
            bad.append(key)
    return bad


def _trim(value: Any) -> Any:
    """Cap a list result, preserving the true total so the composition can report it."""
    if isinstance(value, list) and len(value) > MAX_ITEMS_PER_RESULT:
        return {
            "_truncated": True,
            "_total": len(value),
            "_showing": MAX_ITEMS_PER_RESULT,
            "items": value[:MAX_ITEMS_PER_RESULT],
        }
    return value


class ComposerRefused(RuntimeError):
    """A gate said no. Carries a message written for the user, not the log."""


class UngroundedComposition(ValueError):
    """The model returned values that appear nowhere in the data it was given.

    Treated as a hard failure rather than a warning. A dashboard about a real student that
    quietly contains invented supervisors and milestones is worse than no dashboard.
    """

    def __init__(self, values: list[str]) -> None:
        super().__init__(f"{len(values)} ungrounded value(s)")
        self.values = values


@dataclass
class ComposerResult:
    composition: dict
    functions_called: list[str] = field(default_factory=list)
    tokens_in: int = 0
    tokens_out: int = 0
    latency_ms: int = 0
    model: str = ""


@dataclass
class Progress:
    """A step worth showing a waiting user.

    Composition takes two or three sequential model round-trips, which is long enough that
    a blank spinner reads as broken. These events are the real work as it happens — not a
    simulated progress bar — so what the user sees is what the composer is actually doing.
    """

    kind: Literal["status", "function", "result", "composition", "error"]
    message: str
    data: dict | None = None


BLOCK_CATALOGUE = """\
kpi_row       {items:[{label, value, delta?, tone?, hint?}]}            1-6 headline figures
narrative     {body, tone?}                                            prose; only facts present in the data
alert_banner  {body, tone}                                             one thing needing attention
action_card   {body?, actions:[{label, tool, args, tone?}]}            offers next steps
line_chart    {x:[label], series:[{name, values, style?}], yFormat?,
               markers?:[{at, label, tone}], bands?:[{fromX, toX, tone, label?}]}
                                                                       change over time; bands shade a range
bar_chart     {x:[label], series:[{name, values, style?}], orientation?, yFormat?}
                                                                       compare magnitudes; style "reference" = target line
stacked_bar   {x:[label], series:[{name, values}], orientation?}       part-to-whole across categories
donut         {slices:[{label, value}], centreLabel?}                  one part-to-whole split with a headline value
pie           {slices:[{label, value}]}                                one part-to-whole split, filled
gauge         {value, minimum?, maximum, target?, unit?, label?,
               thresholds?:[breakpoints]}                              one measure against a target — completion vs REF target, load vs cap
table         {columns:[str], rows:[[cell]], rowTones?:[tone],
               rowAction?:{label, tool, argsFrom}, emptyMessage?}       detail; keep to what is needed
timeline      {events:[{at, label, kind, detail?, tone?}]}             dated history
sparkline_grid{items:[{label, values, baseline?, caption?, tone?}]}    many small trends side by side
comparison    {attributes:[str], columns:[{label, values{}, highlight?, note?}]}
                                                                       candidates judged on the same attributes
tree          {nodes:[{id, label, group?, detail?, tone?}],
               edges:[{source, target, label?, tone?}],
               layout?: hierarchical|network, direction?: down|right}   provenance chains, supervision trees, taxonomies
roadmap       {steps:[{label, status: done|current|upcoming|at_risk|missed, at?, detail?}]}
                                                                       ordered stages — student journey, thesis lifecycle, funnel
heatmap       {rows:[str], columns:[str], cells:[{row, column, value, label?}], unit?}
                                                                       density across two axes — supervisor × month, cohort × milestone

Every block also accepts: title (string), source (list of the data function names that
produced it — always set this).

Tones: neutral | info | success | warning | danger."""


_SYSTEM = """\
You compose dashboards for a postgraduate research management platform.

You do not answer in prose and you do not calculate. You choose which data functions to \
call, then you choose how to draw what comes back.

Absolute rules:
1. Every number you place in a block must appear in the function results you were given. \
Never estimate, extrapolate or fill a gap. If something was not returned, leave it out.
2. Only use block types from the catalogue. Only use the fields listed.
3. Prefer showing over telling. A trend is a line_chart, not a sentence. A comparison is a \
table or bar_chart, not a paragraph. Use narrative only to say what the reader might \
otherwise miss — never to restate a number that is already on screen.
4. Lead with the answer. First block should resolve the question asked.
5. Set `source` on every block to the data functions it came from.
6. Respond with JSON only. No markdown fence, no commentary."""


def _describe(value: Any) -> str:
    """A shape, not the data.

    The planner only needs to know what it already holds in order to decide what to fetch
    next — it never reads the values. Sending full results back on every round tripled the
    token cost of planning for no benefit, and on a metered account that is the difference
    between answering and being rate-limited. Ids are the exception: they get passed as
    arguments to the next call, so they have to survive.
    """
    if isinstance(value, dict) and value.get("_truncated"):
        return f"{value['_showing']} of {value['_total']} rows"
    if isinstance(value, list):
        if not value:
            return "empty"
        first = value[0]
        if isinstance(first, dict):
            ids = [
                f"{k}={v}" for k, v in first.items()
                if k.endswith("_id") and isinstance(v, str)
            ]
            hint = f" (first: {', '.join(ids)})" if ids else ""
            return f"{len(value)} rows with fields {', '.join(list(first)[:8])}{hint}"
        return f"{len(value)} values"
    if isinstance(value, dict):
        ids = [f"{k}={v}" for k, v in value.items() if k.endswith("_id") and isinstance(v, str)]
        hint = f" ({', '.join(ids)})" if ids else ""
        return f"object with fields {', '.join(list(value)[:10])}{hint}"
    return str(value)[:120]


def _plan_prompt(question: str, catalogue: str, collected: dict[str, Any], round_no: int) -> str:
    known = (
        "\n".join(f"- {label} -> {_describe(v)}" for label, v in collected.items())
        if collected
        else "Nothing yet — this is the first round."
    )
    return f"""\
Question from the user:
{question}

Data functions available to you:
{catalogue}

Results collected so far:
{known}

This is planning round {round_no} of {MAX_PLAN_ROUNDS}.

Decide what you still need. Arguments must be literal values — where a function needs an \
id, use one that appears in the results above, never a name.

Open-ended asks ("full dashboard", "everything about X", "how is Y doing") need multiple \
functions in ONE round — pull overview, milestones, supervision, funding, thesis, journey \
together rather than one at a time. Narrow asks call just what they name.

Watch for these VISUAL SHAPE requests and use the matching function:
- "as a tree", "lineage", "chain", "hierarchy" → funding_lineage_graph
- "as a roadmap", "journey", "progression", "timeline of stages" → student_journey
- "as a donut" / "as a pie" of funding types → funding_type_breakdown
- "heatmap" of overdue milestones → overdue_milestones_heatmap
- "gauge" for completion vs target → completion_gauge_data
When the user names a specific person AND a shape, first call search_student to get the \
id, then in the NEXT round call the shape-specific function with that id. Do not stop \
after search_student when the ask is for a shape you have not yet fetched data for.

Respond with JSON:
{{"calls": [{{"name": "...", "args": {{...}}}}], "done": false}}

Every entry in `calls` must be an object like {{"name": "x", "args": {{}}}} — never a \
bare string. Set "done": true as soon as these are the LAST functions you need — you may \
set it in the same response as those calls, and doing so saves a round. Only use \
"done": false when you genuinely need to see these results before deciding what to fetch \
next.

Ask for at most {MAX_CALLS_PER_ROUND} functions in one round."""


def _compose_prompt(question: str, collected: dict[str, Any], max_rows: int) -> str:
    return f"""\
Question from the user:
{question}

Data you may use — this is the only source of truth available to you:
{json.dumps(collected, default=str)[:20000]}

Block catalogue:
{BLOCK_CATALOGUE}

Compose the answer. Between two and five blocks. Tables: at most {max_rows} rows.

Where a result carries "_truncated": true it was capped — use "_total" for any count you \
report, show the rows from "items", and say in a narrative or the block title that only \
the top "_showing" are listed. Never claim the capped list is complete.

Keep the response compact. Long tables are worse than short ones with a stated total.

Choosing a block — reach for the shape that fits the question, not always a table:
- Ordered stages (application funnel, thesis lifecycle, student journey) → roadmap
- Chains or hierarchies (funding provenance, supervision structure) → tree
- Density across two axes (supervisor × month, cohort × stage) → heatmap
- One measure against a target/cap (completion vs REF target, load vs cap) → gauge
- Change over time → line_chart
- Compare magnitudes across categories → bar_chart
- Part-to-whole → donut (with a headline centre) or pie (without)
- The user asked for a specific visualisation? Use it.

Respond with JSON:
{{"title": "...", "subtitle": "...", "blocks": [...], "rationale": "one sentence on why \
you chose this shape"}}"""


_RETRY_AFTER = re.compile(r"try again in ([\d.]+)s")


def _user_message_for(exc: Exception) -> str:
    """Turn a provider failure into something worth showing a person.

    Rate limiting is the one a user can act on — it is not a fault, it is a queue, and the
    provider tells us how long to wait. Everything else gets the generic message; the real
    detail is in the audit row.
    """
    text = str(exc)
    if "rate_limit_exceeded" in text or "Error code: 429" in text:
        wait = _RETRY_AFTER.search(text)
        when = f" Try again in about {round(float(wait.group(1))) + 1} seconds." if wait else ""
        return (
            "The language model is rate-limited right now, so this composition could not "
            f"be generated.{when}"
        )
    if "model_not_found" in text or "does not exist" in text:
        return (
            "The configured language model is not available on this account. An "
            "administrator needs to check the model name in the deployment configuration."
        )
    if "ungrounded" in text:
        return (
            "I could not produce an answer I can stand behind — the model kept "
            "introducing values that are not in your data, so I have discarded it "
            "rather than show you something invented. Try a narrower question."
        )
    return "I gathered the data but could not lay it out. Try rephrasing the question."


def _normalise_block_shape(spec: dict) -> dict:
    """Accept either the documented `{"type": "kind", ...fields}` shape or the mistake
    `{"kind": {...fields}}` and normalise to the former."""
    if not isinstance(spec, dict) or not isinstance(spec.get("blocks"), list):
        return spec
    from app.modules.composer.blocks import BLOCK_TYPES

    known = set(BLOCK_TYPES)
    fixed: list[dict] = []
    for block in spec["blocks"]:
        if not isinstance(block, dict):
            fixed.append(block)
            continue
        if "type" in block:
            fixed.append(block)
            continue
        # Look for a single top-level key that matches a known block name.
        wrappers = [k for k in block if k in known]
        if len(wrappers) == 1 and isinstance(block[wrappers[0]], dict):
            inner = block[wrappers[0]]
            unwrapped = {"type": wrappers[0], **inner}
            # Preserve any extra sibling keys — usually harmless, occasionally source.
            for key, value in block.items():
                if key != wrappers[0] and key not in unwrapped:
                    unwrapped[key] = value
            fixed.append(unwrapped)
        else:
            fixed.append(block)
    return {**spec, "blocks": fixed}


def _parse_json(text: str) -> dict:
    """Models fence JSON even when told not to. Strip it rather than failing the run."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("```")[1] if "```" in cleaned[3:] else cleaned[3:]
        if cleaned.lstrip().startswith("json"):
            cleaned = cleaned.lstrip()[4:]
    cleaned = cleaned.strip().strip("`").strip()
    return json.loads(cleaned)


class ComposerService:
    def __init__(self, session: AsyncSession, principal: Principal) -> None:
        self.session = session
        self.principal = principal
        self.provider = get_provider()
        self.planner = get_provider(planner=True)
        # Set by compose_stream just before the terminal event, so the non-streaming
        # wrapper can return a typed result without re-parsing the event payload.
        self._last_result: ComposerResult | None = None

    async def compose(self, question: str, *, composition_key: str | None = None) -> ComposerResult:
        """Non-streaming entry point — drains the stream and returns the final result."""
        result: ComposerResult | None = None
        async for event in self.compose_stream(question, composition_key=composition_key):
            if event.kind == "composition":
                result = self._last_result
        if result is None:
            raise ComposerRefused("The composer produced no result.")
        return result

    async def compose_stream(
        self, question: str, *, composition_key: str | None = None
    ) -> AsyncIterator[Progress]:
        gate = await check_enabled(self.session)
        if not gate.allowed:
            raise ComposerRefused(gate.reason or "The composer is unavailable.")

        budget = await check_budget(
            self.session, user_id=self.principal.user_id, requested=8000
        )
        if not budget.allowed:
            raise ComposerRefused(budget.reason or "Budget exhausted.")

        started = time.perf_counter()
        tokens_in = tokens_out = 0
        called: list[str] = []
        collected: dict[str, Any] = {}
        # Exposed on `self` so the router's crash handler can render the fallback from
        # whatever the planner did manage to gather before it fell over.
        self._partial_collected = collected
        catalogue = fx.catalogue_for_prompt(self.principal)

        try:
            for round_no in range(1, MAX_PLAN_ROUNDS + 1):
                yield Progress(
                    "status",
                    "Working out what data is needed"
                    if round_no == 1
                    else "Following up on what came back",
                )
                # Planning runs two or three times per question and is the easier job, so
                # it uses the smaller model. That model occasionally returns nothing at all
                # on the final round — where the only thing left to say is "done" — so a
                # planning failure ends planning rather than the request. Composition is
                # what the user asked for; if we already have data, go and use it.
                try:
                    response = await self.planner.complete(
                        system=_SYSTEM,
                        user=_plan_prompt(question, catalogue, collected, round_no),
                        json_mode=True,
                        max_tokens=1200,
                    )
                except LLMError:
                    if collected:
                        logger.info("planning round %s failed; composing with what we have",
                                    round_no)
                        break
                    raise

                tokens_in += response.tokens_in
                tokens_out += response.tokens_out

                try:
                    plan = _parse_json(response.text)
                except json.JSONDecodeError:
                    break

                calls = plan.get("calls") or []
                done = bool(plan.get("done"))
                if not calls:
                    break

                for spec in calls[:MAX_CALLS_PER_ROUND]:
                    # Planners occasionally emit `calls: ["name", …]` (bare strings)
                    # instead of `calls: [{"name": "…", "args": {}}, …]`. Treat either
                    # shape as a zero-argument call rather than crashing the whole run.
                    if isinstance(spec, str):
                        name, args = spec, {}
                    elif isinstance(spec, dict):
                        name = spec.get("name", "")
                        args = spec.get("args") or {}
                    else:
                        continue
                    if not name or not isinstance(name, str) or not name.strip():
                        # Silently skip. Emitting a step-event with an empty function name
                        # would put a naked comma in the user-visible progress trail.
                        continue
                    label = f"{name}({json.dumps(args, default=str, sort_keys=True)})"
                    if label in collected:
                        continue
                    # Models reliably try to pass a person's name straight into an id
                    # parameter on the first round. Catching it here rather than at the
                    # database saves a pointless call and keeps the progress trail honest
                    # about what actually ran.
                    guessed = _guessed_ids(args)
                    if guessed:
                        collected[label] = {
                            "error": (
                                f"{', '.join(guessed)} must come from a previous result. "
                                f"Call a search function first, then use the id it returns."
                            )
                        }
                        continue

                    yield Progress("function", name, {"args": args})
                    try:
                        value = _trim(
                            await fx.call(
                                name, session=self.session, principal=self.principal, **args
                            )
                        )
                        collected[label] = value
                        called.append(name)
                        yield Progress("result", _describe(value), {"function": name})
                    except fx.FunctionError as exc:
                        # Hand the error back — the next round can correct itself.
                        collected[label] = {"error": str(exc)}
                        yield Progress("result", str(exc), {"function": name, "failed": True})

                # The model can end planning in the same response as its final calls,
                # which saves a whole round-trip on the common case.
                if done:
                    break

            if not collected:
                raise ComposerRefused(
                    "I could not work out which data this question needs. Try naming a "
                    "student, a cohort or a specific measure."
                )

            yield Progress("status", "Choosing how to lay this out")
            max_rows = await self._max_rows()
            try:
                composition, c_in, c_out = await self._compose_spec(
                    question, collected, max_rows
                )
            except (LLMError, ValueError, ValidationError, UngroundedComposition) as exc:
                # A total failure of the compose phase leaves the user staring at nothing.
                # Better to fall back to a boring, honest render of what came back —
                # tables and KPIs generated deterministically from the data, no model in
                # the loop. The audit row keeps the model's failure for later diagnosis.
                logger.warning("compose failed (%s); falling back to raw render", exc)
                composition = _fallback_render(question, collected, max_rows)
                c_in = c_out = 0
            tokens_in += c_in
            tokens_out += c_out

            latency_ms = int((time.perf_counter() - started) * 1000)
            await self._record(
                question=question, composition_key=composition_key, called=called,
                composition=composition, tokens_in=tokens_in, tokens_out=tokens_out,
                latency_ms=latency_ms, ok=True, error=None,
            )
            self._last_result = ComposerResult(
                composition=composition, functions_called=called,
                tokens_in=tokens_in, tokens_out=tokens_out,
                latency_ms=latency_ms, model=self.provider.name,
            )
            yield Progress(
                "composition",
                "Done",
                {
                    "composition": composition,
                    "meta": {
                        "functionsCalled": called,
                        "tokensIn": tokens_in,
                        "tokensOut": tokens_out,
                        "latencyMs": latency_ms,
                        "provider": self.provider.name,
                    },
                },
            )

        except (LLMError, ValueError, ValidationError) as exc:
            # The compose phase now falls back to a deterministic render, so this only
            # fires when planning itself blew up — genuinely no data to lay out. That is
            # a legitimate refusal to expose to the user.
            latency_ms = int((time.perf_counter() - started) * 1000)
            await self._record(
                question=question, composition_key=composition_key, called=called,
                composition=None, tokens_in=tokens_in, tokens_out=tokens_out,
                latency_ms=latency_ms, ok=False, error=str(exc)[:500],
            )
            logger.warning("composition failed before any data was collected: %s", exc)
            raise ComposerRefused(_user_message_for(exc)) from exc

    async def _compose_spec(
        self, question: str, collected: dict[str, Any], max_rows: int
    ) -> tuple[dict, int, int]:
        """Ask for a spec; on invalid output, one repair round with the errors attached."""
        prompt = _compose_prompt(question, collected, max_rows)
        tokens_in = tokens_out = 0

        for attempt in (1, 2):
            response = await self.provider.complete(
                system=_SYSTEM, user=prompt, json_mode=True, max_tokens=COMPOSE_MAX_TOKENS
            )
            tokens_in += response.tokens_in
            tokens_out += response.tokens_out

            try:
                raw = _parse_json(response.text)
                # Models sometimes emit blocks as {"heatmap": {...}} instead of
                # {"type": "heatmap", ...}. Normalise both shapes before validation, so a
                # cosmetic mistake does not cost a whole repair round.
                raw = _normalise_block_shape(raw)
                spec = Composition.model_validate(raw).model_dump(
                    by_alias=True, exclude_none=True
                )

                # Shape is not provenance. A well-formed composition can still be pure
                # invention, so every data-bearing value is checked against what the model
                # was actually given before it is allowed anywhere near a screen.
                ungrounded = grounding.violations(spec, collected)
                if ungrounded:
                    logger.warning(
                        "composition rejected — %s ungrounded value(s): %s",
                        len(ungrounded), "; ".join(ungrounded[:5]),
                    )
                    raise UngroundedComposition(ungrounded)

                return spec, tokens_in, tokens_out

            except UngroundedComposition as exc:
                if attempt == 2:
                    raise
                prompt = (
                    f"{_compose_prompt(question, collected, max_rows)}\n\n"
                    f"Your previous response was REJECTED because it contained values that "
                    f"do not exist in the data you were given:\n"
                    + "\n".join(f"  - {v}" for v in exc.values[:10])
                    + "\n\nYou invented those. Do not do that again. Use ONLY values that "
                    f"appear verbatim in the data above. If the data does not answer part "
                    f"of the question, omit that block and say so in a narrative. "
                    f"Respond with JSON only."
                )
            except (json.JSONDecodeError, ValidationError, LLMError) as exc:
                if attempt == 2:
                    raise
                # LLMError lands here when the provider rejects the completion — most often
                # because the model ran out of tokens part-way through a large table and
                # returned unparseable JSON. The repair round asks for something smaller.
                prompt = (
                    f"{_compose_prompt(question, collected, min(max_rows, 15))}\n\n"
                    f"Your previous response was rejected:\n{str(exc)[:1200]}\n\n"
                    f"Valid block types are exactly: {', '.join(BLOCK_TYPES)}. "
                    f"Return FEWER blocks and FEWER table rows than before — a compact, "
                    f"valid answer beats a complete one. Respond with JSON only."
                )

        raise ValueError("unreachable")

    async def _max_rows(self) -> int:
        from app.modules.settings.service import setting_value

        try:
            return int(await setting_value(self.session, "composer.max_rows_per_block"))
        except (KeyError, TypeError, ValueError):
            return 50

    async def _record(self, **kw: Any) -> None:
        """Audit the attempt. Never let logging failure mask the real outcome."""
        try:
            names = [
                str(v) for v in _names_in(kw.get("composition"))
            ] if kw.get("composition") else []
            self.session.add(
                ComposerRun(
                    tenant_id=self.principal.tenant_id,
                    user_id=self.principal.user_id,
                    question=redact(kw["question"], names=names)[:2000],
                    composition_key=kw.get("composition_key"),
                    functions_called=kw.get("called"),
                    composition=kw.get("composition"),
                    provider=self.provider.name,
                    model=getattr(self.provider, "_model", self.provider.name),
                    tokens_in=kw.get("tokens_in", 0),
                    tokens_out=kw.get("tokens_out", 0),
                    latency_ms=kw.get("latency_ms", 0),
                    ok=kw.get("ok", False),
                    error=kw.get("error"),
                )
            )
            await self.session.commit()
        except Exception:  # pragma: no cover - audit must not break the response
            logger.exception("could not record composer run")
            await self.session.rollback()


def _names_in(composition: dict | None) -> list[str]:
    """Person names appearing in a composition, so the stored question can mask them."""
    if not composition:
        return []
    found: list[str] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                if key in {"name", "label"} and isinstance(value, str) and " " in value:
                    found.append(value)
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(composition)
    return found
