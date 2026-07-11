"""Streamlit desktop chat UI (spec §6.1). A thin wrapper over ``core.ask``.

Run: ``streamlit run src/ui_desktop/app.py`` → http://localhost:8501

GPT-style multi-chat: a «Новый чат» button plus the chat list in the sidebar.
History is stored in ClickHouse (`retail_demo.chat_history`, see
src/core/chat_store.py) and is shared with the Telegram bot — Telegram
dialogues appear in the sidebar too (read-only). Follow-up questions chain
(condense) ONLY within the current chat; «Новый чат» is the explicit boundary.

The core produces file artifacts (PNG charts, xlsx) — this UI only *displays*
them (spec §12). Includes a sidebar LLM-backend toggle (local / external / auto).
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import streamlit as st

# Make ``src`` importable when launched via ``streamlit run src/ui_desktop/app.py``.
ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import configure_logging, get_settings  # noqa: E402
from src.core import AssistantResponse, ask, chat_store  # noqa: E402
from src.core.llm_client import active_model_label, use_backend  # noqa: E402

configure_logging()
settings = get_settings()

st.set_page_config(page_title="Retail AI Assistant", page_icon="💎", layout="centered")

EXCEL_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
MAX_TITLE = 40
SOURCE_ICONS = {"desktop": "🖥️", "telegram": "📱"}
BACKENDS = ["local", "external", "auto"]
BACKEND_LABELS = {
    "local": "🖥️ Локальная (Ollama)",
    "external": "☁️ Внешняя (Groq)",
    "auto": "🔀 Авто (внешняя → локальная)",
}
EXAMPLES = [
    "Выручка по городам за 2025 год",
    "Покажи график выручки по месяцам",
    "Топ-5 магазинов по выручке",
    "Полный отчет за прошлый месяц",
    "Выгрузи топ-10 товаров по выручке в Excel",
]


@st.cache_resource
def _init_store() -> bool:
    chat_store.ensure_table()
    return True


_init_store()

# --- Session state -------------------------------------------------------------
if "current_source" not in st.session_state:
    st.session_state.current_source = "desktop"
if "current_chat" not in st.session_state:
    st.session_state.current_chat = f"ds-{uuid.uuid4().hex[:8]}"


def _switch(source: str, chat_id: str) -> None:
    st.session_state.current_source = source
    st.session_state.current_chat = chat_id


def render_response(resp: AssistantResponse, idx: int) -> None:
    """Render one assistant answer: text, chart, table, Excel, SQL."""
    if resp.resolved_question:
        st.caption(f"🔎 Понял как: {resp.resolved_question}")
    if resp.text:
        st.markdown(resp.text)
    if resp.chart_path is not None and Path(resp.chart_path).exists():
        st.image(str(resp.chart_path), width="stretch")
    if resp.table_preview:
        with st.expander(f"Таблица · первые {len(resp.table_preview)} строк"):
            st.dataframe(resp.table_preview, width="stretch")
    if resp.excel_path is not None and Path(resp.excel_path).exists():
        st.download_button(
            "📥 Скачать Excel",
            data=Path(resp.excel_path).read_bytes(),
            file_name=Path(resp.excel_path).name,
            mime=EXCEL_MIME,
            key=f"dl_{st.session_state.current_chat}_{idx}",
        )
    if resp.sql:
        with st.expander("SQL"):
            st.code(resp.sql, language="sql")
    if resp.error:
        st.caption(f"⚠️ {resp.error}")


# --- Sidebar: chats + backend toggle -------------------------------------------
chats = chat_store.list_chats()

with st.sidebar:
    if st.button("➕ Новый чат", width="stretch", type="primary"):
        _switch("desktop", f"ds-{uuid.uuid4().hex[:8]}")
        st.rerun()

    if chats:
        st.caption("Чаты (🖥️ desktop · 📱 telegram)")
    for c in chats:
        is_current = (
            c["chat_id"] == st.session_state.current_chat
            and c["source"] == st.session_state.current_source
        )
        icon = SOURCE_ICONS.get(c["source"], "💬")
        title = (c["title"] or "…")[:MAX_TITLE]
        if st.button(
            f"{icon} {title}",
            key=f"chat_{c['source']}_{c['chat_id']}",
            width="stretch",
            disabled=is_current,
        ):
            _switch(c["source"], c["chat_id"])
            st.rerun()

    known_ids = {(c["source"], c["chat_id"]) for c in chats}
    if (st.session_state.current_source, st.session_state.current_chat) in known_ids:
        if st.button("🗑️ Удалить текущий чат", width="stretch"):
            chat_store.delete_chat(st.session_state.current_source, st.session_state.current_chat)
            _switch("desktop", f"ds-{uuid.uuid4().hex[:8]}")
            st.rerun()

    st.divider()
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
    st.caption(
        "🔗 Вопросы внутри чата связываются (можно уточнять: «а по месяцам», "
        "«добавь %»). «➕ Новый чат» начинает с чистого листа."
    )


# --- Chat ------------------------------------------------------------------------
st.title("💎 Retail AI Assistant")
st.caption("Аналитический ассистент по продажам ювелирной сети. Спросите на русском.")

source = st.session_state.current_source
chat_id = st.session_state.current_chat
turns = chat_store.load_turns(source, chat_id)

for i, turn in enumerate(turns):
    with st.chat_message("user"):
        st.markdown(turn["question"])
    with st.chat_message("assistant"):
        render_response(chat_store.turn_to_response(turn), i)

if source == "telegram":
    st.info("📱 Это переписка из Telegram — просмотр. Продолжить можно в боте, "
            "или начните новый чат здесь.")
else:
    if prompt := st.chat_input("Спросите про выручку, магазины, план, сотрудников…"):
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner(f"Анализирую ({active_model_label(backend)})…"):
                with use_backend(backend):
                    response = ask(prompt, chat_store.build_history(source, chat_id))
            render_response(response, len(turns))
        chat_store.log_turn(source, chat_id, prompt, response)
        st.rerun()
