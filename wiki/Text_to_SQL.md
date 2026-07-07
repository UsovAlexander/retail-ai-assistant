# Text-to-SQL

See [[Index]]. Related: [[Qdrant_Collections]], [[Data]], [[Architecture]].
Source: `raw/project_spec_en.md` §5.2. **Status: not yet implemented (stage 4).**

## Pipeline (`src/core/sql_generator.py`)

1. **Schema RAG** — top-3 relevant tables from `retail_schema` ([[Qdrant_Collections]]).
2. **Few-shot RAG** — top-3 nearest `question → SQL` examples from `retail_few_shot`.
3. **Prompt** — system (ClickHouse dialect rules, `src/prompts/sql_system.txt`)
   + retrieved schema + retrieved examples + user question.
4. **Ollama** (`qwen2.5-coder:14b`, temperature 0.1) → SQL.
5. **Validator** (`src/core/validator.py`) — SELECT-only, forced `LIMIT`,
   system tables forbidden, single statement.
6. **Execute** in ClickHouse; on error, retry with the error text (≤3 attempts).

## Validator rules (stage 4/5)

- Reject anything that is not a single `SELECT`.
- Forbid DDL/DML keywords (INSERT/ALTER/DROP/CREATE/…), `system.*`, multi-statement.
- Force a `LIMIT` if absent.
- Restrict to `retail_demo` tables.

## Dialect / correctness rules to encode in the prompt (stage 4)

- Revenue is always `sum(quantity * price * (1 - discount_pct/100))`.
- **Avoid join fan-out when aggregating the fact table against `plans`**: never
  `JOIN plans → sales` and then `sum(plan_revenue)` (it multiplies the plan by
  the number of matching sales rows). Aggregate `plans` and `sales` in separate
  subqueries, then join on `store_id` (and month). Discovered at stage 3 — see
  [[Qdrant_Collections]]; the corrected pattern is few-shot example #18.

## Open questions / decisions

- _(to be filled at stage 4)_
