# Artifacts — charts & Excel

See [[Index]]. Related: [[Architecture]], [[Interfaces]].
Source: `raw/project_spec_en.md` §5.3–5.4. **Status: implemented (stage 5).**

The core writes artifacts to **files** (dir = `settings.artifacts_path`) so both
interfaces share one pipeline (see [[Architecture]]). 27 unit tests cover the
render/export logic (+ the SQL validator); charts eyeballed on real data.

## Chart builder (`src/core/chart_builder.py`)
- matplotlib, **Agg** backend (no GUI), PNG via `build_chart(rows, spec)`.
- `decide_chart_spec(question, columns, rows)` — LLM (JSON mode) returns a
  `ChartSpec` (pydantic): `{chart_type, x, y, title, hue}`. Returns `None`
  (→ no chart) if the spec is invalid or references unknown columns.
- Style: title bold, money axis abbreviated (тыс/млн/млрд), recessive grid,
  top/right spines off. Line=trend, bar/barh=magnitude, pie=composition.
- **Colors**: the validated colorblind-safe categorical palette from the
  data-viz guidance, fixed 8-hue order (single blue for single-series magnitude;
  categorical for pie slices / multi-series `hue`). Ran the palette validator
  (worst adjacent CVD ΔE 24.2; sub-3:1 hues carry direct labels).
- `limit_categories()` — bar/barh keep the top 19, fold the rest into **"Прочее"**
  (pie: top 7 + Прочее). Unit-tested (value is conserved).

## Excel exporter (`src/core/excel_exporter.py`)
- openpyxl, `export_to_excel(rows, columns) -> Path`.
- Formatting: bold + filled header, auto column width (cap 60), money number
  format on numeric columns, frozen header row (`freeze_panes="A2"`).
- `ROW_WARN_THRESHOLD = 100_000` — the **caller** (orchestrator/UI) warns in the
  text answer; the exporter still writes the file.

## Open questions / decisions

- **Money format**: spec wrote `# ##0`; implemented as the portable Excel code
  `#,##0` (`MONEY_FORMAT`) which renders locale thousands grouping reliably.
- **Numeric-column detection**: first non-null value is `int/float` (excluding
  `bool`) → gets money format. Good enough for aggregate result sets.
- **Axis labels** currently show the raw result column names (e.g. `revenue`,
  `month`) — kept for transparency; the Russian chart title is the main
  descriptor. Minor polish candidate: humanize/translate axis labels.
- **Charts are static PNGs** (Telegram + Streamlit share them), so the data-viz
  skill's interactive layer (hover/tooltips/filters) does not apply; its form +
  color rules do and were followed.
