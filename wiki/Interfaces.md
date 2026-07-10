# Interfaces

See [[Index]]. Related: [[Architecture]] (the `AssistantResponse` contract).
Source: `raw/project_spec_en.md` §6.
**Status: desktop implemented (stage 8); telegram pending (stage 9).**

Both interfaces are thin wrappers around `core.ask(question) -> AssistantResponse`.

## Desktop (`src/ui_desktop/app.py`) — implemented
- Streamlit chat: `st.chat_message` + `st.chat_input`; history in
  `st.session_state.messages` (user text + full `AssistantResponse` objects,
  re-rendered from artifact paths on rerun).
- Charts inline via `st.image(response.chart_path)` — **not** re-rendered figures.
- Excel via `st.download_button(data=Path(...).read_bytes())` (unique `key` per
  message index so history replays don't collide).
- Table preview via `st.dataframe(response.table_preview)` in an expander.
- Executed SQL in a collapsible `st.expander("SQL")` (`st.code(..., "sql")`).
- **LLM backend toggle**: sidebar `st.radio` (local / external / auto), default
  from `LLM_BACKEND`; each `ask()` runs inside `llm_client.use_backend(choice)`;
  the sidebar + spinner show `active_model_label(choice)`. Warns when
  external/auto selected but `EXTERNAL_LLM_*` unconfigured. See [[Architecture]].
- Sidebar extras: example questions, "Очистить чат" button.
- Run: `streamlit run src/ui_desktop/app.py` → localhost:8501.
- **Verified in the browser (stage 8)**: chart question on local backend →
  summary + PNG + table + SQL; toggled to Groq → Excel question → summary +
  table + download button + SQL; history preserved across the toggle.

## Telegram bot (`src/ui_telegram/bot.py`)
- aiogram 3.x; token via `TELEGRAM_BOT_TOKEN` (.env).
- Chart → photo. **Excel not supported** in the bot: on `sql_with_excel`,
  reply with data as text/chart and hint that export is in the desktop version.
- User whitelist by telegram `user_id` (config) — internal corporate tool.
- Commands: `/start` (capabilities + example questions), `/help`.
- Run: `python -m src.ui_telegram.bot`.

## Open questions / decisions

- **History stores `AssistantResponse` objects**, not re-serialized dicts — the
  simplest faithful replay; artifact files persist in `ARTIFACTS_DIR` so old
  messages keep their images/downloads within a session.
- **Backend toggle is per-request** (`use_backend` context), not process-wide —
  two consecutive questions can hit different models for comparison.
- **`sys.path` bootstrap** at the top of `app.py` because
  `streamlit run src/ui_desktop/app.py` doesn't put the repo root on the path.
- _(stage 9 decisions pending)_
