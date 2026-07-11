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

## Telegram bot (`src/ui_telegram/bot.py`) — implemented
- aiogram 3.x; token via `TELEGRAM_BOT_TOKEN` (.env). Bot: `@retail_ai_assist_bot`.
- Chart → photo (`FSInputFile` from the core's PNG artifact); summary as the
  caption when ≤1024 chars, otherwise a separate message.
- **Excel → document** (`answer_document`, filename `report_<date>.xlsx`,
  summary as caption; `UPLOAD_DOCUMENT` chat action while sending).
  _Spec §6.2 originally said desktop-only; amended 2026-07-11 on the owner's
  request — the spec now matches this behavior._
- Multi-row results without a chart/file get pretty emoji text lines
  (`_format_rows`: 🥇🥈🥉 for rankings, ru number formatting, bold values).
- User whitelist by telegram `user_id` (`TELEGRAM_ALLOWED_USERS`); denied users
  see their own ID so an admin can whitelist them. **Empty whitelist = deny all.**
- Commands: `/start`, `/help` (capabilities + example questions).
- The sync core runs via `asyncio.to_thread` so polling stays responsive;
  `typing` chat action while thinking. HTML parse mode, everything escaped.
- Run: `python -m src.ui_telegram.bot`.
- **Verified (stage 9)**: bot connects, `getMe` OK, polling starts, whitelist
  logged. Live chat exchange requires messaging the bot from Telegram.

## Open questions / decisions

- **History stores `AssistantResponse` objects**, not re-serialized dicts — the
  simplest faithful replay; artifact files persist in `ARTIFACTS_DIR` so old
  messages keep their images/downloads within a session.
- **Backend toggle is per-request** (`use_backend` context), not process-wide —
  two consecutive questions can hit different models for comparison.
- **`sys.path` bootstrap** at the top of `app.py` because
  `streamlit run src/ui_desktop/app.py` doesn't put the repo root on the path.
- **Bot ignores `excel_path` rather than the core skipping generation** — keeping
  the core interface-agnostic beats saving one small file write. If it ever
  matters, add an `allow_excel` flag to `ask()`.
- **Empty whitelist denies everyone** (safe default for a corporate tool); the
  denial message shows the requester's ID to ease onboarding.
- **No LLM-backend toggle in the bot** — it follows `LLM_BACKEND` from config;
  per-request comparison is a desktop feature.
