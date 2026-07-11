# Text-to-SQL

See [[Index]]. Related: [[Qdrant_Collections]], [[Data]], [[Architecture]].
Source: `raw/project_spec_en.md` §5.2. **Status: implemented (stage 4).**
Entry point: `src.core.sql_generator.generate_sql(question) -> SQLResult`.
LLM: `src.core.llm_client.chat()` (Ollama, OpenAI-compatible, temp 0.1).

## Pipeline (`src/core/sql_generator.py`)

1. **Schema RAG** — top-3 relevant tables from `retail_schema` ([[Qdrant_Collections]]).
2. **Few-shot RAG** — top-3 nearest `question → SQL` examples from `retail_few_shot`.
3. **Prompt** — system (ClickHouse dialect rules, `src/prompts/sql_system.txt`)
   + retrieved schema + retrieved examples + user question.
4. **Ollama** (`qwen2.5-coder:14b`, temperature 0.1) → SQL.
5. **Validator** (`src/core/validator.py`) — SELECT-only, forced `LIMIT`,
   system tables forbidden, single statement.
6. **Execute** in ClickHouse; on error, retry with the error text (≤3 attempts).

`SQLResult` fields: `question, sql, columns, rows (list[dict]), row_count,
attempts, error`, plus `.ok`. Prompt: `src/prompts/sql_system.txt` (system) +
retrieved schema + examples + question (user turn). Retrieval `top_k=3` each.

## Validator rules (`src/core/validator.py`) — implemented

- Strip markdown fences; require a single statement (reject inner `;`).
- Must start with `SELECT` or `WITH`. Forbid DDL/DML keywords as whole words
  (INSERT/UPDATE/DELETE/DROP/ALTER/CREATE/TRUNCATE/SYSTEM/SET/USE/INTO/…).
- Forbid external/system sources: `system.`, `information_schema.`, and table
  functions (`url/file/remote/s3/mysql/postgresql/hdfs/...`).
- Force `LIMIT DEFAULT_LIMIT` (1000) when absent. Raises `SQLValidationError`.

## Verification (stage 4) — 8 manual questions

8/8 executed; ~7/8 semantically correct after prompt tuning. Retry-on-error
recovered real ClickHouse errors on 2 questions (attempt 2). Two prompt rules
were added after the first run: (a) only use `plans` when the question is about
plans/targets (fixed a "по форматам" query that wrongly dragged in `plans`);
(b) "сколько/how many" → return a single `count()`.

**Known limitation** (for [[Evaluation]] to track): *count-over-HAVING* questions
like "сколько магазинов не выполнили план" need a nested `count(*)` over a
per-store aggregate; the 14B model tends to emit `GROUP BY store ... HAVING`
returning one row per store instead of a single scalar. Candidate fix: add a
nested-count few-shot example, or a post-check that wraps such shapes.

## Dialect / correctness rules to encode in the prompt (stage 4)

- **Relative dates must be bounded on BOTH sides** (`sale_date BETWEEN today()-7
  AND today()`), because the dataset intentionally contains **future-dated sales**
  (through 2026-12-31, see [[Data]]). Found live via the Telegram bot: «продажи
  по дням за последнюю неделю» generated an open `>= today()-7` filter and
  returned 182 days (through Dec 2026) instead of 8. Fixed in `sql_system.txt`
  + `relative_dates` few-shot examples.
- **Time semantics convention (user-confirmed)**: «прошлая неделя / прошлый
  месяц / прошлый год» are **calendar periods** (Mon–Sun week / calendar month /
  calendar year), never rolling windows:
  - неделя: `toStartOfWeek(sale_date, 1) = toStartOfWeek(today(), 1) - 7`
  - месяц: `toYYYYMM(sale_date) = toYYYYMM(addMonths(today(), -1))`
  - год: `toYear(sale_date) = toYear(today()) - 1`
  Only an explicit «за последние N дней» is a rolling window (`BETWEEN today()-N
  AND today()`). «Этот месяц/год» = current calendar period bounded by `today()`.
  Encoded in `sql_system.txt` + 4 `relative_dates` few-shot examples (30 total).
  Found live: «топ продавцов за прошлый месяц» had produced a rolling
  May 11 – Jun 10 window instead of calendar June.

- Revenue is always `sum(quantity * price * (1 - discount_pct/100))`.
- **Avoid join fan-out when aggregating the fact table against `plans`**: never
  `JOIN plans → sales` and then `sum(plan_revenue)` (it multiplies the plan by
  the number of matching sales rows). Aggregate `plans` and `sales` in separate
  subqueries, then join on `store_id` (and month). Discovered at stage 3 — see
  [[Qdrant_Collections]]; the corrected pattern is few-shot example #18.

## Open questions / decisions

- **RAG in the user turn**: system prompt = static dialect rules
  (`sql_system.txt`); retrieved schema + examples + question go in the user turn.
- **Retry protocol**: on validator or ClickHouse error, append the failed SQL +
  the error to the conversation and ask for a corrected query (≤3 attempts total).
  Validator rejections and execution errors share the same loop.
- **Not yet using JSON mode here** — SQL is returned as raw text (fences stripped
  by the validator). JSON mode is reserved for intent routing / chart spec (§5.1/5.3).
