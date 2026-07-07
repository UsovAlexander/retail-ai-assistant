# Retail AI Assistant

A **fully local, air-gapped** AI analyst assistant for a retail company.
Employees ask questions in natural language ("show revenue by region for March",
"which sales reps beat their targets", "export March sales to Excel") and get a
short analytical summary, a chart (PNG), and/or an Excel export. Everything runs
on-premise: a local LLM via **Ollama** (`qwen2.5-coder:14b`), data in
**ClickHouse**, vector search in **Qdrant** — no external APIs.

> **Status:** work in progress. Built stage by stage (see `wiki/Roadmap.md`).
> Currently complete: **Stage 1** (skeleton) and **Stage 2** (synthetic data).

## Architecture

An interface-agnostic **core** exposes `core.ask(question) -> AssistantResponse`.
Two thin interfaces sit on top: a **Streamlit** desktop chat and a **Telegram**
bot. The core produces **file artifacts** (PNG charts, xlsx) so both interfaces
share one pipeline. Text-to-SQL is grounded by **two RAG layers** (schema +
few-shot) retrieved from Qdrant. See `wiki/Architecture.md`.

```
Desktop UI (Streamlit) ─┐        ┌─ Text-to-SQL (schema RAG) → ClickHouse
                        ├─ Core ─┼─ Chart builder → matplotlib → PNG
Telegram bot (aiogram) ─┘        ├─ Excel export → openpyxl → xlsx
                                 └─ Summarizer
                     Qdrant (schema + few-shot) · Ollama (qwen2.5-coder:14b)
```

## Metrics

_Populated at stage 7 from `eval/results.md` (execution accuracy, result accuracy)._

## Quick start

```bash
# 1. Services. On a fresh machine:
docker-compose up -d            # ClickHouse + Qdrant
ollama pull qwen2.5-coder:14b   # LLM (Ollama runs on the host)

# 2. Python env
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 3. Configure
cp .env.example .env            # set CH_PASSWORD, TELEGRAM_BOT_TOKEN, ...

# 4. Verify connectivity to all three services
python -m src.check_env

# 5. Generate synthetic data → retail_demo
python -m src.data_gen.generate

# --- later stages ---
# python -m src.vectorstore.indexer      # build Qdrant collections
# streamlit run src/ui_desktop/app.py    # desktop chat
# python -m src.ui_telegram.bot          # telegram bot
```

## Stack & rationale

- **Ollama (local LLM)** — air-gapped corporate environment; data never leaves the host.
- **ClickHouse** — fast analytical queries over ~1M sales rows.
- **Qdrant + two RAG layers** — schema RAG grounds SQL in the real tables;
  few-shot RAG supplies dialect-correct, dynamic examples per question.
- **File artifacts, not live figures** — one artifact pipeline serves both the
  Streamlit UI and the Telegram bot.
- **No LangChain/LlamaIndex** — the pipeline is written explicitly to demonstrate
  the mechanics (this is a portfolio project).

## Project knowledge (LLM Wiki)

This repo uses the [LLM Wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f):
`raw/` is immutable source material, `wiki/` is the compiled knowledge. Start at
`wiki/Index.md`. Contributor rules live in `CLAUDE.md`.
