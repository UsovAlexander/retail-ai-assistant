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

## Data flow (per question)

1. **Orchestrator** classifies intent (structured JSON): `sql_query`,
   `sql_with_chart`, `sql_with_excel`, `chitchat`.
2. **Text-to-SQL** (if not chitchat): schema RAG + few-shot RAG → prompt →
   Ollama → SQL → validate → execute (retry on error). See [[Text_to_SQL]].
3. **Artifacts**: chart and/or Excel as requested. See [[Artifacts]].
4. **Summarizer**: 2–4 sentence Russian analytical summary from the result.
5. Return `AssistantResponse`.

## Stack choices (rationale)

- **Ollama / local** — air-gapped corporate environment; no external LLM APIs.
- **Two RAG layers** — schema RAG grounds the model in the real tables;
  few-shot RAG gives dialect-correct, dynamic examples per question.
- **File artifacts, not live figures** — one pipeline serves both interfaces.
- **No LangChain/LlamaIndex** — explicit pipeline; this is a portfolio project
  demonstrating the mechanics.

## Open questions / decisions

- _(none yet)_
