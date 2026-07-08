# Architecture

See [[Index]]. Related: [[Interfaces]], [[Text_to_SQL]], [[Artifacts]].

## Principle: the core knows nothing about the interfaces

The **core** takes a natural-language question and returns a structured
`AssistantResponse`. Desktop (Streamlit) and Telegram (aiogram) are thin
wrappers around `core.ask(question) -> AssistantResponse`.

Critically, the core produces **file artifacts** (PNG charts, xlsx exports),
not live figures. The Telegram bot needs files; Streamlit merely displays them
(`st.image`, `st.download_button`). This keeps a single shared artifact pipeline.

## `AssistantResponse` contract

```python
@dataclass
class AssistantResponse:
    text: str                      # analytical summary
    sql: str | None                # executed SQL (for transparency)
    table_preview: list[dict]      # first N rows of the result
    chart_path: Path | None        # PNG chart, if built
    excel_path: Path | None        # Excel file, if generated
    error: str | None
```

## Diagram

```
 Desktop UI (Streamlit chat) ─┐        ┌─ Text-to-SQL (schema RAG) ─→ ClickHouse
                              ├─ Core ─┼─ Chart builder ─→ matplotlib → PNG
 Telegram bot (aiogram) ──────┘  (agent │─ Excel export ─→ openpyxl → xlsx
                                orchestr)└─ Summarizer
                                   ▲   Qdrant (schema + few-shot) ─┘
                                   └─ Ollama (qwen2.5-coder:14b)
```

## Data flow (per question) — **implemented (stage 6)**

Entry point: `core.ask(question) -> AssistantResponse` (`src/core/orchestrator.py`,
re-exported from `src/core/__init__.py`).

1. **Orchestrator** classifies intent (structured JSON, temp 0.1): `sql_query`,
   `sql_with_chart`, `sql_with_excel`, `chitchat` (`src/prompts/intent_router.txt`).
2. **chitchat** → short capability reply (from the router, static fallback).
3. **Text-to-SQL** (data intents): schema RAG + few-shot RAG → prompt → Ollama →
   SQL → validate → execute (retry on error). See [[Text_to_SQL]].
4. **Summarizer**: 2–4 sentence Russian analytical summary from the first 50
   rows (`src/core/summarizer.py`, temp 0.3). See [[Interfaces]].
5. **Artifacts**: `sql_with_chart` → PNG (best-effort); `sql_with_excel` → xlsx
   (+ row-count warning past 100k). See [[Artifacts]].
6. Return `AssistantResponse` (text, sql, table_preview[:50], chart_path, excel_path, error).
   `ask()` never raises — failures surface in `error`/`text`.

## LLM backend (local / external / auto)

`src/core/llm_client.py` supports three backends via `LLM_BACKEND`:

- **`local`** (default) — Ollama `qwen2.5-coder:14b`. Keeps the system fully local.
- **`external`** — any OpenAI-compatible endpoint (`EXTERNAL_LLM_*`), e.g. **Groq**
  `llama-3.3-70b-versatile`, to benchmark against a stronger model.
- **`auto`** — try external first, **fall back to local** on any error / rate
  limit / quota exhaustion (prod resilience).

Precedence for each `chat()` call: explicit `backend=` arg > `use_backend(...)`
context override (for a per-request UI toggle) > `LLM_BACKEND` config. Both
backends use the OpenAI SDK — no extra dependency. `active_model_label()` reports
what actually ran; the eval report and (stage 8) the desktop UI surface it.

> **Deliberate deviation from spec §12** ("local Ollama only"): added on request
> to (a) compare metrics against a stronger external model and (b) auto-fail-over
> in prod. Mitigated: **off by default** — the "fully local" default is preserved;
> external needs an explicit key in `.env`.

## Stack choices (rationale)

- **Ollama / local** — air-gapped corporate environment by default; external
  backend is opt-in (see above).
- **Two RAG layers** — schema RAG grounds the model in the real tables;
  few-shot RAG gives dialect-correct, dynamic examples per question.
- **File artifacts, not live figures** — one pipeline serves both interfaces.
- **No LangChain/LlamaIndex** — explicit pipeline; this is a portfolio project
  demonstrating the mechanics.

## Open questions / decisions

- **`ask()` is total** (never raises): validator/SQL failure → `SQL_FAILURE_TEXT`
  + `error`; any exception → `ERROR_TEXT` + `error`. Interfaces can render blindly.
- **Chart is best-effort**: if `decide_chart_spec` returns None or `build_chart`
  throws, the text answer + preview still return (chart just omitted).
- **Intent fallback**: if the router JSON won't parse, default to `sql_query`
  (most useful safe behavior) rather than erroring.
- **`core.ask` re-export** lives in `src/core/__init__.py` via a lazy import of
  the orchestrator, to avoid a circular import (orchestrator needs
  `AssistantResponse` from the package).
- **Verified end-to-end (stage 6)** on all four intents: chitchat replies with
  capabilities; `sql_query`/`_with_chart`/`_with_excel` return summary + SQL +
  preview, with a PNG / xlsx attached as routed.
