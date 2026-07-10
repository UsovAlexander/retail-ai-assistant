"""Streamlit desktop chat UI (spec §6.1). A thin wrapper over ``core.ask``.

Run: ``streamlit run src/ui_desktop/app.py`` → http://localhost:8501

The core produces file artifacts (PNG charts, xlsx) — this UI only *displays*
them (``st.image`` / ``st.download_button``), it never re-renders figures
(spec §12). Includes a sidebar LLM-backend toggle (local / external / auto) so
answers from the local and external models can be compared per request.
"""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

# Make ``src`` importable when launched via ``streamlit run src/ui_desktop/app.py``.
ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import configure_logging, get_settings  # noqa: E402
from src.core import AssistantResponse, HistoryTurn, ask  # noqa: E402
from src.core.llm_client import active_model_label, use_backend  # noqa: E402

configure_logging()
settings = get_settings()

st.set_page_config(page_title="Retail AI Assistant", page_icon="💎", layout="centered")

EXCEL_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
BACKENDS = ["local", "external", "auto"]
BACKEND_LABELS = {
    "local": "🖥️ Локальная (Ollama)",
    "external": "☁️ Внешняя (Groq)",
    "auto": "🔀 Авто (внешняя → локальная)",
}
EXAMPLES = [
    "Выручка по городам за 2025 год",
    "Покажи график выручки по месяцам за 2025 год",
    "Топ-5 магазинов по выручке",
    "Выгрузи топ-10 товаров по выручке в Excel",
]


def build_history(messages: list[dict]) -> list[HistoryTurn]:
    """Recent (question, sql) turns from the chat history, for follow-ups."""
    turns: list[HistoryTurn] = []
    for i in range(len(messages) - 1):
        cur, nxt = messages[i], messages[i + 1]
        if cur["role"] == "user" and nxt["role"] == "assistant":
            resp: AssistantResponse = nxt["response"]
            if resp.error is None and resp.sql:
                turns.append((resp.resolved_question or cur["content"], resp.sql))
    return turns[-3:]


def render_response(resp: AssistantResponse, idx: int) -> None:
    """Render one assistant answer: text, chart, table, Excel, SQL."""
    if resp.resolved_question:
        st.caption(f"🔎 Понял как: {resp.resolved_question}")
    if resp.text:
        st.markdown(resp.text)
    if resp.chart_path is not None and Path(resp.chart_path).exists():
        st.image(str(resp.chart_path), use_container_width=True)
    if resp.table_preview:
        with st.expander(f"Таблица · первые {len(resp.table_preview)} строк"):
            st.dataframe(resp.table_preview, use_container_width=True)
    if resp.excel_path is not None and Path(resp.excel_path).exists():
        st.download_button(
            "📥 Скачать Excel",
            data=Path(resp.excel_path).read_bytes(),
            file_name=Path(resp.excel_path).name,
            mime=EXCEL_MIME,
            key=f"dl_{idx}_{Path(resp.excel_path).name}",
        )
    if resp.sql:
        with st.expander("SQL"):
            st.code(resp.sql, language="sql")
    if resp.error:
        st.caption(f"⚠️ {resp.error}")


# --- Sidebar: backend toggle -------------------------------------------------
with st.sidebar:
    st.header("⚙️ Настройки")
    backend = st.radio(
        "Модель (LLM backend)",
        BACKENDS,
        index=BACKENDS.index(settings.llm_backend) if settings.llm_backend in BACKENDS else 0,
        format_func=lambda b: BACKEND_LABELS[b],
    )
    st.caption(f"Активно: `{active_model_label(backend)}`")
    if backend in ("external", "auto") and not settings.external_configured:
        st.warning(
            "Внешняя модель не настроена (EXTERNAL_LLM_* в .env). "
            + ("Будет использована локальная." if backend == "auto" else "")
        )
    st.divider()
    st.caption("Примеры вопросов:")
    for ex in EXAMPLES:
        st.caption(f"• {ex}")
    st.divider()
    if st.button("🗑️ Очистить чат"):
        st.session_state.messages = []
        st.rerun()


# --- Chat --------------------------------------------------------------------
st.title("💎 Retail AI Assistant")
st.caption("Аналитический ассистент по продажам ювелирной сети. Спросите на русском.")

if "messages" not in st.session_state:
    st.session_state.messages = []

for i, msg in enumerate(st.session_state.messages):
    with st.chat_message(msg["role"]):
        if msg["role"] == "user":
            st.markdown(msg["content"])
        else:
            render_response(msg["response"], i)

if prompt := st.chat_input("Спросите про выручку, магазины, план, сотрудников…"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    with st.chat_message("assistant"):
        with st.spinner(f"Анализирую ({active_model_label(backend)})…"):
            with use_backend(backend):
                response = ask(prompt, build_history(st.session_state.messages[:-1]))
        render_response(response, len(st.session_state.messages))
    st.session_state.messages.append({"role": "assistant", "response": response})
