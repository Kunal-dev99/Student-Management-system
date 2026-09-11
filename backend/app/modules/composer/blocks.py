"""The block catalog — the contract between the composer (LLM) and the renderer (React).

The LLM never emits prose-as-answer and never emits numbers it invented. It emits a
`Composition`: an ordered list of blocks drawn from this fixed catalog, where every value
came out of a deterministic data function (see `functions.py`).

Two consequences fall out of that:

* **It renders or it doesn't.** A block that fails validation here never reaches the
  frontend, so the renderer can assume well-formed input and there is no such thing as a
  hallucinated component.
* **Every number is traceable.** Blocks carry `source` — the data function(s) that produced
  them — so the UI can offer "show me the underlying rows" on anything.

Adding a block type is a three-step change: a model here, a renderer in
`frontend/src/features/composer/blocks/`, and a line in the catalogue the prompt shows the
model. Nothing else needs to know.
"""
from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

Tone = Literal["neutral", "info", "success", "warning", "danger"]


def _camel(s: str) -> str:
    head, *rest = s.split("_")
    return head + "".join(w.title() for w in rest)


class _Block(BaseModel):
    """Common shape. Serialises camelCase to match the frontend's convention."""

    model_config = ConfigDict(alias_generator=_camel, populate_by_name=True, extra="forbid")

    title: str | None = None
    # Data functions that produced this block, e.g. ["funding_burndown"]. Drives the
    # "show underlying rows" affordance and the audit trail.
    source: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- structural


class KpiItem(BaseModel):
    model_config = ConfigDict(alias_generator=_camel, populate_by_name=True, extra="forbid")

    label: str
    value: str | float | int
    # Optional change vs the comparison period, already formatted (e.g. "+3", "-12%").
    delta: str | None = None
    tone: Tone = "neutral"
    hint: str | None = None


class KpiRow(_Block):
    type: Literal["kpi_row"] = "kpi_row"
    items: list[KpiItem] = Field(min_length=1, max_length=6)


class Narrative(_Block):
    """The one block whose body is model-written. Everything in it must be supported by
    values present in other blocks of the same composition."""

    type: Literal["narrative"] = "narrative"
    body: str = Field(max_length=2000)
    tone: Tone = "neutral"


class AlertBanner(_Block):
    type: Literal["alert_banner"] = "alert_banner"
    body: str = Field(max_length=600)
    tone: Tone = "warning"


class Action(BaseModel):
    """A button. `tool` names a staged write in the action registry — pressing it opens a
    confirmation, it never executes inline."""

    model_config = ConfigDict(alias_generator=_camel, populate_by_name=True, extra="forbid")

    label: str
    tool: str
    args: dict = Field(default_factory=dict)
    tone: Tone = "neutral"


class ActionCard(_Block):
    type: Literal["action_card"] = "action_card"
    body: str | None = Field(default=None, max_length=600)
    actions: list[Action] = Field(min_length=1, max_length=4)


# ------------------------------------------------------------------------------- charts


class Marker(BaseModel):
    """A labelled vertical rule on a time axis — "projected submission", "viva booked"."""

    model_config = ConfigDict(alias_generator=_camel, populate_by_name=True, extra="forbid")

    at: str
    label: str
    tone: Tone = "neutral"


class Band(BaseModel):
    """A shaded x-range — the four months where funding has run out but the thesis hasn't
    been submitted, say."""

    model_config = ConfigDict(alias_generator=_camel, populate_by_name=True, extra="forbid")

    from_x: str = Field(alias="fromX")
    to_x: str = Field(alias="toX")
    label: str | None = None
    tone: Tone = "danger"


class Series(BaseModel):
    model_config = ConfigDict(alias_generator=_camel, populate_by_name=True, extra="forbid")

    name: str
    # `None` breaks the line — used for "no data beyond here", not for zero.
    values: list[float | None]
    # "reference" renders dashed and recessive: targets, caps, cohort medians.
    style: Literal["solid", "dashed", "reference"] = "solid"


class LineChart(_Block):
    type: Literal["line_chart"] = "line_chart"
    x: list[str] = Field(min_length=2)
    series: list[Series] = Field(min_length=1, max_length=4)
    x_label: str | None = None
    y_label: str | None = None
    y_format: Literal["number", "currency", "percent", "months"] = "number"
    markers: list[Marker] = Field(default_factory=list)
    bands: list[Band] = Field(default_factory=list)


class BarChart(_Block):
    type: Literal["bar_chart"] = "bar_chart"
    x: list[str] = Field(min_length=1)
    series: list[Series] = Field(min_length=1, max_length=3)
    orientation: Literal["vertical", "horizontal"] = "vertical"
    x_label: str | None = None
    y_label: str | None = None
    y_format: Literal["number", "currency", "percent", "months"] = "number"


class StackedBar(_Block):
    type: Literal["stacked_bar"] = "stacked_bar"
    x: list[str] = Field(min_length=1)
    series: list[Series] = Field(min_length=2, max_length=6)
    orientation: Literal["vertical", "horizontal"] = "vertical"


class Slice(BaseModel):
    model_config = ConfigDict(alias_generator=_camel, populate_by_name=True, extra="forbid")

    label: str
    value: float


class Donut(_Block):
    type: Literal["donut"] = "donut"
    slices: list[Slice] = Field(min_length=2, max_length=8)
    centre_label: str | None = None


class Pie(_Block):
    """A filled pie, no centre. Same schema as donut — kept separate so the model can
    reach for it explicitly when there is no headline number to sit in the middle."""

    type: Literal["pie"] = "pie"
    slices: list[Slice] = Field(min_length=2, max_length=8)


class Gauge(_Block):
    """A value against a target — completion rate vs REF target, funding drawdown vs plan.
    Renders as a curved dial with the target marked; thresholds tint the arc."""

    type: Literal["gauge"] = "gauge"
    value: float
    minimum: float = 0
    maximum: float
    target: float | None = None
    unit: Literal["number", "currency", "percent", "months", "days"] = "number"
    label: str | None = None
    # Segment breakpoints in ascending order — [30, 70] on a 0-100 gauge divides the arc
    # into red / amber / green bands so the reader sees the zone at a glance.
    thresholds: list[float] = Field(default_factory=list, max_length=4)


# ------------------------------------------------------------------------ data displays


class RowAction(BaseModel):
    """Turns every table row into a control. `args_from` maps column names onto the tool's
    arguments, so one declaration wires the whole column."""

    model_config = ConfigDict(alias_generator=_camel, populate_by_name=True, extra="forbid")

    label: str
    tool: str
    args_from: dict[str, str] = Field(default_factory=dict)


class Table(_Block):
    type: Literal["table"] = "table"
    columns: list[str] = Field(min_length=1, max_length=10)
    rows: list[list[str | float | int | None]] = Field(max_length=200)
    # Per-row tone, same length as `rows` when present — highlights the ones needing action.
    row_tones: list[Tone] | None = None
    row_action: RowAction | None = None
    empty_message: str | None = None


class TimelineEvent(BaseModel):
    model_config = ConfigDict(alias_generator=_camel, populate_by_name=True, extra="forbid")

    at: str
    label: str
    # Free-text grouping — "milestone", "meeting", "funding", "thesis", "exception".
    kind: str
    detail: str | None = None
    tone: Tone = "neutral"


class Timeline(_Block):
    type: Literal["timeline"] = "timeline"
    events: list[TimelineEvent] = Field(min_length=1, max_length=120)


class SparklineItem(BaseModel):
    model_config = ConfigDict(alias_generator=_camel, populate_by_name=True, extra="forbid")

    label: str
    values: list[float]
    # Drawn as a reference line through the sparkline — cohort median, target, cap.
    baseline: float | None = None
    caption: str | None = None
    tone: Tone = "neutral"


class SparklineGrid(_Block):
    type: Literal["sparkline_grid"] = "sparkline_grid"
    items: list[SparklineItem] = Field(min_length=1, max_length=12)


class ComparisonColumn(BaseModel):
    model_config = ConfigDict(alias_generator=_camel, populate_by_name=True, extra="forbid")

    label: str
    # Attribute name -> value. Keys must match `attributes` on the parent block.
    values: dict[str, str]
    highlight: bool = False
    note: str | None = None


class Comparison(_Block):
    """Candidates side by side — examiner shortlists, supervisor matches, cohort A vs B."""

    type: Literal["comparison"] = "comparison"
    attributes: list[str] = Field(min_length=1, max_length=10)
    columns: list[ComparisonColumn] = Field(min_length=2, max_length=5)
    actions: list[Action] = Field(default_factory=list)


# ------------------------------------------------------------------- structural graphs


class TreeNode(BaseModel):
    """A node in a rendered graph. `id` is what edges refer to; `label` is what a human
    reads. `group` colours nodes by kind (funder / award / arrangement / student)."""

    model_config = ConfigDict(alias_generator=_camel, populate_by_name=True, extra="forbid")

    id: str
    label: str
    group: str | None = None
    detail: str | None = None
    tone: Tone = "neutral"


class TreeEdge(BaseModel):
    model_config = ConfigDict(alias_generator=_camel, populate_by_name=True, extra="forbid")

    source: str
    target: str
    label: str | None = None
    tone: Tone = "neutral"


class Tree(_Block):
    """A hierarchical or network graph.

    Fits the domain's provenance chains (Student → Arrangement → Source → Award → Funder),
    supervision structures (supervisor → co-supervisor → student), and taxonomy views
    (department → area → topic). Layout is `hierarchical` when there is a clear root,
    `network` for peer relationships.
    """

    type: Literal["tree"] = "tree"
    nodes: list[TreeNode] = Field(min_length=1, max_length=40)
    edges: list[TreeEdge] = Field(default_factory=list, max_length=60)
    layout: Literal["hierarchical", "network"] = "hierarchical"
    # Direction only meaningful for hierarchical — "down" for org charts, "right" for
    # provenance/lineage where the source sits at the left.
    direction: Literal["down", "right"] = "down"


# ------------------------------------------------------------------------------ roadmap


class RoadmapStep(BaseModel):
    model_config = ConfigDict(alias_generator=_camel, populate_by_name=True, extra="forbid")

    label: str
    status: Literal["done", "current", "upcoming", "at_risk", "missed"] = "upcoming"
    at: str | None = None
    detail: str | None = None


class Roadmap(_Block):
    """An ordered progression rendered as connected milestones — a student's PhD journey,
    a thesis lifecycle, a recruitment funnel, a completion pipeline. Reads left-to-right;
    the current step is emphasised, upcoming steps recede, missed steps warn."""

    type: Literal["roadmap"] = "roadmap"
    steps: list[RoadmapStep] = Field(min_length=2, max_length=10)


# ------------------------------------------------------------------------------ heatmap


class HeatmapCell(BaseModel):
    model_config = ConfigDict(alias_generator=_camel, populate_by_name=True, extra="forbid")

    row: str
    column: str
    value: float
    label: str | None = None


class Heatmap(_Block):
    """A grid of values, colour-intensity encoded. Reveals patterns a table hides: which
    supervisors take on students in which months, which milestone types cluster overdue,
    which departments concentrate risk. Rows and columns come as ordered lists so the
    grid can be laid out even when some cells are empty."""

    type: Literal["heatmap"] = "heatmap"
    rows: list[str] = Field(min_length=1, max_length=30)
    columns: list[str] = Field(min_length=1, max_length=24)
    cells: list[HeatmapCell] = Field(min_length=1, max_length=400)
    unit: Literal["number", "percent", "days", "months"] = "number"


# --------------------------------------------------------------------------------- union

Block = Annotated[
    Union[
        KpiRow,
        Narrative,
        AlertBanner,
        ActionCard,
        LineChart,
        BarChart,
        StackedBar,
        Donut,
        Pie,
        Gauge,
        Table,
        Timeline,
        SparklineGrid,
        Comparison,
        Tree,
        Roadmap,
        Heatmap,
    ],
    Field(discriminator="type"),
]


class Composition(BaseModel):
    """What the composer returns and the frontend renders."""

    model_config = ConfigDict(alias_generator=_camel, populate_by_name=True, extra="forbid")

    title: str
    subtitle: str | None = None
    blocks: list[Block] = Field(min_length=1, max_length=14)
    # Why the model chose this shape. Shown behind a disclosure, not in the flow.
    rationale: str | None = Field(default=None, max_length=600)


BLOCK_TYPES: tuple[str, ...] = (
    "kpi_row", "narrative", "alert_banner", "action_card",
    "line_chart", "bar_chart", "stacked_bar", "donut", "pie", "gauge",
    "table", "timeline", "sparkline_grid", "comparison",
    "tree", "roadmap", "heatmap",
)
