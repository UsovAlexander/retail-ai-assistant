"""Chart building: matplotlib (Agg) → PNG artifact. See [[Artifacts]].

Two responsibilities (spec §5.3):
  * ``decide_chart_spec`` — the LLM picks the chart via structured JSON output.
  * ``build_chart``       — render that spec to a PNG file (no GUI, Agg backend).

Colors use the validated categorical palette from the data-viz guidance
(colorblind-safe, fixed order, never cycled; a 9th category folds into "Прочее").
"""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any, Literal

import matplotlib

matplotlib.use("Agg")  # headless: no GUI, safe for server/bot

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402
from pydantic import BaseModel, ValidationError  # noqa: E402

from src.config import PROMPTS_DIR, get_settings  # noqa: E402
from src.core.llm_client import chat  # noqa: E402

logger = logging.getLogger(__name__)

# Validated light-surface categorical palette (dataviz skill), FIXED order.
CATEGORICAL = [
    "#2a78d6", "#1baf7a", "#eda100", "#008300",
    "#4a3aa7", "#e34948", "#e87ba4", "#eb6834",
]
SERIES_1 = CATEGORICAL[0]
SURFACE = "#fcfcfb"
INK_PRIMARY = "#0b0b0b"
INK_SECONDARY = "#52514e"
GRID_COLOR = "#d9d8d4"

MAX_CATEGORIES = 20          # bar/barh cap; the rest folds into "Прочее"
OTHER_LABEL = "Прочее"


class ChartSpec(BaseModel):
    """How to draw the result — produced by the LLM as structured JSON."""

    chart_type: Literal["line", "bar", "barh", "pie"]
    x: str
    y: str
    title: str
    hue: str | None = None


# --- LLM: decide the chart spec ----------------------------------------------
def decide_chart_spec(question: str, columns: list[str], rows: list[dict]) -> ChartSpec | None:
    """Ask the LLM for a chart spec; return None if it can't be applied."""
    system = (PROMPTS_DIR / "chart_spec.txt").read_text(encoding="utf-8")
    sample = rows[:3]
    user = (
        f"QUESTION: {question}\n"
        f"COLUMNS: {columns}\n"
        f"SAMPLE ROWS: {json.dumps(sample, ensure_ascii=False, default=str)}\n"
        "JSON:"
    )
    raw = chat(
        [{"role": "system", "content": system}, {"role": "user", "content": user}],
        temperature=0.1,
        json_mode=True,
    )
    try:
        spec = ChartSpec.model_validate_json(raw)
    except ValidationError as exc:
        logger.warning("Chart spec invalid: %s", exc)
        return None
    if spec.x not in columns or spec.y not in columns:
        logger.warning("Chart spec references unknown columns: %s", spec)
        return None
    if spec.hue is not None and spec.hue not in columns:
        spec.hue = None
    return spec


# --- Rendering ---------------------------------------------------------------
def _money_formatter() -> FuncFormatter:
    def fmt(value: float, _pos: int = 0) -> str:
        a = abs(value)
        if a >= 1e9:
            return f"{value / 1e9:.1f} млрд"
        if a >= 1e6:
            return f"{value / 1e6:.0f} млн"
        if a >= 1e3:
            return f"{value / 1e3:.0f} тыс"
        return f"{value:.0f}"

    return FuncFormatter(fmt)


def _to_float(v: Any) -> float:
    if isinstance(v, bool):
        raise ValueError("boolean is not a measure")
    return float(v)


def _column(rows: list[dict], col: str) -> list[Any]:
    return [r.get(col) for r in rows]


def limit_categories(
    labels: list[Any], values: list[float], max_n: int = MAX_CATEGORIES
) -> tuple[list[Any], list[float]]:
    """Keep the top ``max_n - 1`` categories by value; sum the rest into 'Прочее'."""
    if len(labels) <= max_n:
        return labels, values
    pairs = sorted(zip(labels, values), key=lambda p: p[1], reverse=True)
    head = pairs[: max_n - 1]
    tail_sum = sum(v for _, v in pairs[max_n - 1:])
    labels_out = [str(l) for l, _ in head] + [OTHER_LABEL]
    values_out = [v for _, v in head] + [tail_sum]
    return labels_out, values_out


def _style_axes(ax: plt.Axes) -> None:
    ax.set_facecolor(SURFACE)
    ax.grid(True, color=GRID_COLOR, alpha=0.7, linewidth=0.6)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID_COLOR)
    ax.tick_params(colors=INK_SECONDARY, labelsize=9)


def _new_figure() -> tuple[plt.Figure, plt.Axes]:
    fig, ax = plt.subplots(figsize=(10, 6), dpi=120)
    fig.patch.set_facecolor(SURFACE)
    _style_axes(ax)
    return fig, ax


def _series_groups(rows: list[dict], spec: ChartSpec) -> dict[Any, list[dict]]:
    """Split rows by the hue column into ordered series groups."""
    groups: dict[Any, list[dict]] = {}
    for r in rows:
        groups.setdefault(r.get(spec.hue), []).append(r)
    return groups


def _render_line(ax: plt.Axes, rows: list[dict], spec: ChartSpec) -> None:
    if spec.hue:
        for i, (name, grp) in enumerate(_series_groups(rows, spec).items()):
            xs = [r.get(spec.x) for r in grp]
            ys = [_to_float(r.get(spec.y)) for r in grp]
            ax.plot(xs, ys, marker="o", markersize=4, linewidth=2,
                    color=CATEGORICAL[i % len(CATEGORICAL)], label=str(name))
        ax.legend(frameon=False, labelcolor=INK_SECONDARY, fontsize=9)
    else:
        xs = _column(rows, spec.x)
        ys = [_to_float(v) for v in _column(rows, spec.y)]
        ax.plot(xs, ys, marker="o", markersize=4, linewidth=2, color=SERIES_1)
    ax.yaxis.set_major_formatter(_money_formatter())


def _render_bar(ax: plt.Axes, rows: list[dict], spec: ChartSpec, horizontal: bool) -> None:
    labels = [str(v) for v in _column(rows, spec.x)]
    values = [_to_float(v) for v in _column(rows, spec.y)]
    labels, values = limit_categories(labels, values)

    if horizontal:
        # Largest at the top.
        order = sorted(range(len(values)), key=lambda i: values[i])
        labels = [labels[i] for i in order]
        values = [values[i] for i in order]
        ax.barh(labels, values, color=SERIES_1, height=0.7)
        ax.xaxis.set_major_formatter(_money_formatter())
    else:
        ax.bar(labels, values, color=SERIES_1, width=0.7)
        ax.yaxis.set_major_formatter(_money_formatter())
        if len(labels) > 6:
            plt.setp(ax.get_xticklabels(), rotation=45, ha="right")


def _render_pie(ax: plt.Axes, rows: list[dict], spec: ChartSpec) -> None:
    labels = [str(v) for v in _column(rows, spec.x)]
    values = [_to_float(v) for v in _column(rows, spec.y)]
    labels, values = limit_categories(labels, values, max_n=8)
    colors = [CATEGORICAL[i % len(CATEGORICAL)] for i in range(len(labels))]
    ax.pie(
        values, labels=labels, colors=colors, autopct="%1.1f%%",
        startangle=90, textprops={"color": INK_PRIMARY, "fontsize": 9},
        wedgeprops={"edgecolor": SURFACE, "linewidth": 2},
    )
    ax.axis("equal")


def build_chart(rows: list[dict], spec: ChartSpec, out_dir: Path | None = None) -> Path:
    """Render ``spec`` over ``rows`` to a PNG file and return its path."""
    if not rows:
        raise ValueError("no rows to plot")
    out_dir = out_dir or get_settings().artifacts_path

    fig, ax = _new_figure()
    try:
        if spec.chart_type == "line":
            _render_line(ax, rows, spec)
        elif spec.chart_type == "bar":
            _render_bar(ax, rows, spec, horizontal=False)
        elif spec.chart_type == "barh":
            _render_bar(ax, rows, spec, horizontal=True)
        elif spec.chart_type == "pie":
            _render_pie(ax, rows, spec)

        ax.set_title(spec.title, color=INK_PRIMARY, fontsize=14, fontweight="bold", pad=14)
        if spec.chart_type != "pie":
            ax.set_xlabel(spec.x, color=INK_SECONDARY, fontsize=10)
            ax.set_ylabel(spec.y, color=INK_SECONDARY, fontsize=10)

        fig.tight_layout()
        path = out_dir / f"chart_{uuid.uuid4().hex[:12]}.png"
        fig.savefig(path, facecolor=SURFACE, bbox_inches="tight")
        logger.info("Chart saved: %s (%s)", path, spec.chart_type)
        return path
    finally:
        plt.close(fig)
