# Interfaces

See [[Index]]. Related: [[Architecture]] (the `AssistantResponse` contract).
Source: `raw/project_spec_en.md` §6. **Status: not yet implemented (stages 8–9).**

Both interfaces are thin wrappers around `core.ask(question) -> AssistantResponse`.

## Desktop (`src/ui_desktop/app.py`)
- Streamlit chat: `st.chat_message` + `st.chat_input`; history in `st.session_state`.
- Charts inline via `st.image(response.chart_path)` — **do not** re-render figures.
- Excel via `st.download_button(data=open(response.excel_path, 'rb'))`.
- Table preview via `st.dataframe(response.table_preview)`.
- Executed SQL in a collapsible `st.expander("SQL")`.
- Run: `streamlit run src/ui_desktop/app.py` → localhost:8501.

## Telegram bot (`src/ui_telegram/bot.py`)
- aiogram 3.x; token via `TELEGRAM_BOT_TOKEN` (.env).
- Chart → photo. **Excel not supported** in the bot: on `sql_with_excel`,
  reply with data as text/chart and hint that export is in the desktop version.
- User whitelist by telegram `user_id` (config) — internal corporate tool.
- Commands: `/start` (capabilities + example questions), `/help`.
- Run: `python -m src.ui_telegram.bot`.

## Open questions / decisions

- _(to be filled at stages 8–9)_
