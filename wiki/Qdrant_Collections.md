# Qdrant Collections

See [[Index]]. Related: [[Text_to_SQL]], [[Data]].
Source: `raw/project_spec_en.md` §4. **Status: not yet implemented (stage 3).**

Qdrant at `localhost:6333`. **Only** touch `retail_schema` and `retail_few_shot`.
Existing collections `jewelry_items`, `terraforming` are unrelated — never touch.

## `retail_schema`
- One document per table: name + columns/types + Russian description
  + 2–3 sample values of key columns (cities, categories, positions).
- Use: schema RAG — retrieve top-3 relevant tables for a question.

## `retail_few_shot`
- One document per `question → reference SQL` pair (20–30, written manually
  against the real `retail_demo` schema). Cover: aggregations, joins with
  directories, window functions, plan-vs-actual, top-N, time series.
- Use: dynamic few-shot — retrieve top-3 nearest examples per question.

## Embeddings
- `cointegrated/LaBSE-en-ru` (768-dim, cosine). Loaded once, singleton.
- Module: `src/vectorstore/indexer.py` (build), `src/vectorstore/client.py` (client).

## Open questions / decisions

- _(to be filled at stage 3)_
