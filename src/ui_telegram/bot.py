"""Telegram bot (aiogram 3.x) — a thin wrapper over ``core.ask`` (spec §6.2).

Run: ``python -m src.ui_telegram.bot``

Behavior:
- **Whitelist** by Telegram user id (``TELEGRAM_ALLOWED_USERS`` in .env) — this
  is an internal corporate tool. Empty whitelist = nobody is allowed (safe default).
- Chart → sent as a photo (the core's PNG artifact).
- **Excel is NOT supported here**: on the ``sql_with_excel`` intent the core still
  returns ``excel_path``; the bot ignores the file, answers with text + a small
  monospace table and hints that Excel export lives in the desktop version.
- Commands: /start (capabilities + example questions), /help.

See [[Interfaces]].
"""

from __future__ import annotations

import asyncio
import datetime as dt
import html
import logging
import uuid

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatAction, ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import FSInputFile, KeyboardButton, Message, ReplyKeyboardMarkup

from src.config import configure_logging, get_settings
from src.core import AssistantResponse, ask, chat_store

logger = logging.getLogger("tg_bot")

router = Router()

# Session id per Telegram chat: a new one on /new — the explicit dialogue
# boundary. Follow-up context comes from chat_store (the shared ClickHouse
# history), so a session continued from the desktop UI stays coherent here too.
_session: dict[int, str] = {}


def _session_id(chat_id: int) -> str:
    if chat_id not in _session:
        _session[chat_id] = f"tg-{chat_id}-{uuid.uuid4().hex[:6]}"
    return _session[chat_id]

NEW_CHAT_TEXT = "🆕 Новый запрос"
MAIN_KEYBOARD = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=NEW_CHAT_TEXT)]],
    resize_keyboard=True,
    is_persistent=True,
)

MAX_MESSAGE = 4096
MAX_CAPTION = 1024
TABLE_ROWS = 10

WELCOME = (
    "💎 <b>Retail AI Assistant</b>\n\n"
    "Я аналитический ассистент по продажам ювелирной сети: выручка, магазины, "
    "план vs факт, сотрудники, товары. Могу присылать графики и отчёты в Excel.\n\n"
    "Примеры вопросов:\n"
    "• Выручка по городам за 2025 год\n"
    "• Покажи график выручки по месяцам\n"
    "• Топ-5 магазинов по выручке\n"
    "• Какие магазины не выполнили план в прошлом месяце?\n"
    "• Полный отчет за прошлый месяц\n"
    "• Выгрузи продажи по категориям в Excel\n\n"
    "🔗 Вопросы связываются между собой — можно уточнять: «а по месяцам», "
    "«добавь %». Кнопка «🆕 Новый запрос» (или /new) сбрасывает контекст."
)
HELP_TEXT = WELCOME
DENIED = (
    "⛔ Доступ ограничен: это внутренний корпоративный инструмент.\n"
    "Ваш Telegram ID: <code>{user_id}</code> — передайте его администратору, "
    "чтобы вас добавили в список доступа."
)


def _is_allowed(message: Message) -> bool:
    allowed = get_settings().allowed_user_ids
    return bool(message.from_user and message.from_user.id in allowed)


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


RANK_EMOJI = ["🥇", "🥈", "🥉"]
PCT_HINTS = ("pct", "percent", "share", "процент", "доля")


def _fmt_value(v: object, col: str) -> str:
    """Human number formatting: space thousands, comma decimals, % for shares."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, float) and not float(v).is_integer():
        s = f"{v:,.1f}".replace(",", " ").replace(".", ",")
    else:
        s = f"{int(v):,}".replace(",", " ")
    if any(h in col.lower() for h in PCT_HINTS):
        s += "%"
    return s


def _format_rows(rows: list[dict], limit: int = TABLE_ROWS) -> str:
    """Render rows as pretty text lines (no tables): emoji bullet + values."""
    if not rows:
        return ""
    cols = list(rows[0].keys())
    str_cols = [c for c in cols if isinstance(rows[0].get(c), str)]
    label_col = str_cols[0] if str_cols else cols[0]
    value_cols = [c for c in cols if c != label_col]

    # Medals only when the list reads as a ranking (first metric non-increasing).
    ranked = False
    if value_cols and len(rows) > 1:
        nums = [r.get(value_cols[-1]) for r in rows[:limit]]
        if all(isinstance(n, (int, float)) for n in nums):
            ranked = all(nums[i] >= nums[i + 1] for i in range(len(nums) - 1))

    lines: list[str] = []
    for i, r in enumerate(rows[:limit]):
        bullet = RANK_EMOJI[i] if ranked and i < len(RANK_EMOJI) else "▫️"
        label = html.escape(_truncate(str(r.get(label_col)), 60))
        if not value_cols:
            lines.append(f"{bullet} {label}")
            continue
        parts = [
            f"{html.escape(c)}: <b>{html.escape(_fmt_value(r.get(c), c))}</b>"
            for c in value_cols
        ]
        if len(value_cols) == 1:
            lines.append(f"{bullet} {label} — <b>{html.escape(_fmt_value(r.get(value_cols[0]), value_cols[0]))}</b>")
        else:
            lines.append(f"{bullet} <b>{label}</b>\n      {' · '.join(parts)}")
    if len(rows) > limit:
        lines.append(f"… ещё {len(rows) - limit} строк")
    return "\n".join(lines)


async def _send_response(message: Message, resp: AssistantResponse) -> None:
    """Deliver an AssistantResponse: text, chart as photo, Excel as document."""
    text = html.escape(resp.text or "")

    # Transparency: show how a follow-up was understood.
    if resp.resolved_question:
        text = f"<i>🔎 Понял как: {html.escape(resp.resolved_question)}</i>\n\n{text}"

    has_excel = resp.excel_path is not None and resp.excel_path.exists()

    # Pretty text lines when there's data and no chart/file to carry it.
    if (
        resp.table_preview and len(resp.table_preview) > 1
        and resp.chart_path is None and not has_excel
    ):
        text += "\n\n" + _format_rows(resp.table_preview)

    if resp.chart_path is not None and resp.chart_path.exists():
        photo = FSInputFile(resp.chart_path)
        if len(text) <= MAX_CAPTION:
            await message.answer_photo(photo, caption=text, reply_markup=MAIN_KEYBOARD)
        else:
            await message.answer(_truncate(text, MAX_MESSAGE))
            await message.answer_photo(photo, reply_markup=MAIN_KEYBOARD)
    elif has_excel:
        assert resp.excel_path is not None
        document = FSInputFile(
            resp.excel_path, filename=f"report_{dt.date.today().isoformat()}.xlsx"
        )
        if message.bot is not None:
            await message.bot.send_chat_action(message.chat.id, ChatAction.UPLOAD_DOCUMENT)
        if len(text) <= MAX_CAPTION:
            await message.answer_document(document, caption=text, reply_markup=MAIN_KEYBOARD)
        else:
            await message.answer(_truncate(text, MAX_MESSAGE))
            await message.answer_document(
                document, caption="📊 Отчёт в Excel", reply_markup=MAIN_KEYBOARD
            )
    else:
        await message.answer(_truncate(text or "Готово.", MAX_MESSAGE), reply_markup=MAIN_KEYBOARD)


@router.message(CommandStart())
@router.message(Command("help"))
async def cmd_start(message: Message) -> None:
    if not _is_allowed(message):
        user_id = message.from_user.id if message.from_user else 0
        await message.answer(DENIED.format(user_id=user_id))
        return
    await message.answer(WELCOME, reply_markup=MAIN_KEYBOARD)


@router.message(Command("new"))
@router.message(F.text == NEW_CHAT_TEXT)
async def cmd_new(message: Message) -> None:
    """Explicit dialogue boundary: stop chaining questions to previous ones."""
    if not _is_allowed(message):
        user_id = message.from_user.id if message.from_user else 0
        await message.answer(DENIED.format(user_id=user_id))
        return
    _session.pop(message.chat.id, None)  # next question starts a new stored chat
    await message.answer(
        "🧹 Контекст сброшен — следующий вопрос будет обработан с чистого листа.",
        reply_markup=MAIN_KEYBOARD,
    )


@router.message(F.text)
async def handle_question(message: Message) -> None:
    if not _is_allowed(message):
        user_id = message.from_user.id if message.from_user else 0
        await message.answer(DENIED.format(user_id=user_id))
        return
    assert message.text is not None and message.bot is not None
    logger.info("Question from %s: %s", message.from_user.id, message.text)  # type: ignore[union-attr]

    await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    session = _session_id(message.chat.id)
    # The core is synchronous — run it off the event loop. Follow-up context
    # comes from the shared store, so desktop-added turns count here too.
    history = await asyncio.to_thread(chat_store.build_history, "telegram", session)
    resp = await asyncio.to_thread(ask, message.text, history)
    await _send_response(message, resp)

    # Shared conversation log (also rendered by the desktop UI). Best-effort.
    await asyncio.to_thread(chat_store.log_turn, "telegram", session, message.text, resp)


async def main_async() -> None:
    configure_logging()
    s = get_settings()
    if not s.telegram_bot_token:
        raise SystemExit("TELEGRAM_BOT_TOKEN is not set in .env")
    if not s.allowed_user_ids:
        logger.warning("TELEGRAM_ALLOWED_USERS is empty — the bot will refuse everyone.")

    chat_store.ensure_table()

    bot = Bot(
        token=s.telegram_bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher()
    dp.include_router(router)

    me = await bot.get_me()
    logger.info("Bot @%s started; whitelist: %s", me.username, sorted(s.allowed_user_ids))
    await dp.start_polling(bot)


def main() -> None:
    asyncio.run(main_async())


if __name__ == "__main__":
    main()
