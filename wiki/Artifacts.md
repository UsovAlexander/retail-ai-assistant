# Artifacts — charts & Excel

See [[Index]]. Related: [[Architecture]], [[Interfaces]].
Source: `raw/project_spec_en.md` §5.3–5.4. **Status: not yet implemented (stage 5).**

The core writes artifacts to **files** in a temp folder so both interfaces
share one pipeline (see [[Architecture]]).

## Chart builder (`src/core/chart_builder.py`)
- matplotlib, **Agg** backend (no GUI), save PNG to temp folder.
- LLM chooses the chart via structured output:
  `{"chart_type": "line|bar|barh|pie", "x": "col", "y": "col", "title": "...", "hue": "col|null"}`
- Russian axis labels/title; unified style (grid, readable fonts, no 3D/clutter).
- Max 20 categories on a bar chart; the rest → "Other" (Прочее).

## Excel exporter (`src/core/excel_exporter.py`)
- openpyxl, save to temp folder.
- Formatting: bold header, auto column width, money number format (`# ##0`),
  frozen first row.
- If rows > 100,000 — warn in the text answer.

## Open questions / decisions

- _(to be filled at stage 5)_
