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
import html
import logging

from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ChatAction, ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import FSInputFile, Message

from src.config import configure_logging, get_settings
from src.core import AssistantResponse, ask

logger = logging.getLogger("tg_bot")

router = Router()

MAX_MESSAGE = 4096
MAX_CAPTION = 1024
TABLE_ROWS = 10
CELL_WIDTH = 22

WELCOME = (
    "💎 <b>Retail AI Assistant</b>\n\n"
    "Я аналитический ассистент по продажам ювелирной сети: выручка, магазины, "
    "план vs факт, сотрудники, товары. Могу присылать графики.\n\n"
    "Примеры вопросов:\n"
    "• Выручка по городам за 2025 год\n"
    "• Покажи график выручки по месяцам\n"
    "• Топ-5 магазинов по выручке\n"
    "• Какие магазины не выполнили план в декабре 2025?\n\n"
    "📎 Выгрузка в Excel доступна в десктопной версии."
)
HELP_TEXT = WELCOME
DENIED = (
    "⛔ Доступ ограничен: это внутренний корпоративный инструмент.\n"
    "Ваш Telegram ID: <code>{user_id}</code> — передайте его администратору, "
    "чтобы вас добавили в список доступа."
)
EXCEL_HINT = (
    "📎 Выгрузка в Excel доступна в десктопной версии ассистента "
    "(Streamlit) — здесь показываю данные текстом."
)


def _is_allowed(message: Message) -> bool:
    allowed = get_settings().allowed_user_ids
    return bool(message.from_user and message.from_user.id in allowed)


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _format_table(rows: list[dict], limit: int = TABLE_ROWS) -> str:
    """Render the first rows as a compact monospace table for Telegram."""
    if not rows:
        return ""
    cols = list(rows[0].keys())
    shown = rows[:limit]

    def cell(v: object) -> str:
        s = f"{v:,.0f}" if isinstance(v, float) else str(v)
        return _truncate(s, CELL_WIDTH)

    widths = {
        c: min(CELL_WIDTH, max(len(c), *(len(cell(r.get(c))) for r in shown)))
        for c in cols
    }
    header = " | ".join(c.ljust(widths[c]) for c in cols)
    sep = "-+-".join("-" * widths[c] for c in cols)
    body = "\n".join(
        " | ".join(cell(r.get(c)).ljust(widths[c]) for c in cols) for r in shown
    )
    more = f"\n… ещё {len(rows) - limit} строк" if len(rows) > limit else ""
    return f"<pre>{html.escape(header)}\n{sep}\n{body}</pre>{html.escape(more)}"


async def _send_response(message: Message, resp: AssistantResponse) -> None:
    """Deliver an AssistantResponse: text, optional table, chart as photo."""
    text = html.escape(resp.text or "")

    # Compact table when there's data but no chart to carry it.
    if resp.table_preview and len(resp.table_preview) > 1 and resp.chart_path is None:
        text += "\n\n" + _format_table(resp.table_preview)
    if resp.excel_path is not None:
        text += f"\n\n{html.escape(EXCEL_HINT)}"

    if resp.chart_path is not None and resp.chart_path.exists():
        photo = FSInputFile(resp.chart_path)
        if len(text) <= MAX_CAPTION:
            await message.answer_photo(photo, caption=text)
        else:
            await message.answer(_truncate(text, MAX_MESSAGE))
            await message.answer_photo(photo)
    else:
        await message.answer(_truncate(text or "Готово.", MAX_MESSAGE))


@router.message(CommandStart())
@router.message(Command("help"))
async def cmd_start(message: Message) -> None:
    if not _is_allowed(message):
        user_id = message.from_user.id if message.from_user else 0
        await message.answer(DENIED.format(user_id=user_id))
        return
    await message.answer(WELCOME)


@router.message(F.text)
async def handle_question(message: Message) -> None:
    if not _is_allowed(message):
        user_id = message.from_user.id if message.from_user else 0
        await message.answer(DENIED.format(user_id=user_id))
        return
    assert message.text is not None and message.bot is not None
    logger.info("Question from %s: %s", message.from_user.id, message.text)  # type: ignore[union-attr]

    await message.bot.send_chat_action(message.chat.id, ChatAction.TYPING)
    # The core is synchronous — run it off the event loop.
    resp = await asyncio.to_thread(ask, message.text)
    await _send_response(message, resp)


async def main_async() -> None:
    configure_logging()
    s = get_settings()
    if not s.telegram_bot_token:
        raise SystemExit("TELEGRAM_BOT_TOKEN is not set in .env")
    if not s.allowed_user_ids:
        logger.warning("TELEGRAM_ALLOWED_USERS is empty — the bot will refuse everyone.")

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
