# Qdrant Collections

See [[Index]]. Related: [[Text_to_SQL]], [[Data]].
Source: `raw/project_spec_en.md` §4. **Status: not yet implemented (stage 3).**

Qdrant at `localhost:6333`. **Only** touch `retail_schema` and `retail_few_shot`.
Existing collections `jewelry_items`, `terraforming` are unrelated — never touch.
`src/vectorstore/client.py` enforces this with `_assert_allowed()` on every
mutating call (recreate/upsert). Build: `python -m src.vectorstore.indexer`.

**Status: implemented (stage 3).** `retail_schema` = 6 points, `retail_few_shot`
= 26 points, both dim 768 / cosine. `jewelry_items` (23,672) and `terraforming`
(6) verified untouched.

## `retail_schema`
- One document per table: name + columns/types + Russian description
  + 2–3 sample values of key columns (cities, categories, positions).
- Use: schema RAG — retrieve top-3 relevant tables for a question.

## `retail_few_shot`
- One document per `question → reference SQL` pair (**26** written manually
  against the real `retail_demo` schema). Payload: `{question, sql, tags}`.
- Coverage tags: `aggregation`, `join`/`directory`, `top_n`, `time_series`,
  `window`, `plan_vs_actual`. All 26 SQL statements execute cleanly against
  `retail_demo` (validated before indexing — reference SQL must run).
- Use: dynamic few-shot — retrieve top-3 nearest examples per question.

## Embeddings
- `cointegrated/LaBSE-en-ru` (768-dim, cosine). Loaded once, singleton
  (`get_embedder()`), `normalize_embeddings=True`. Runs on MPS on this Mac.
- Module: `src/vectorstore/indexer.py` (build), `src/vectorstore/client.py`
  (client + embedder singletons, `embed()`, `recreate_collection()`, `search()`).

## Open questions / decisions

- **torch on Python 3.14**: `torch 2.12.1` has cp314 wheels and installs fine;
  `sentence-transformers 3.4` + LaBSE load and embed OK. Pinned `torch>=2.2,<3`.
- **qdrant-client API**: v1.18 removed `.search()`; use `.query_points(query=…)`
  and read `.points`. `recreate_collection` is done as `delete_collection` (if
  exists) + `create_collection`.
- **Few-shot SQL is validated, not just written**: a scratch harness runs each
  statement against `retail_demo`. This caught a **join fan-out bug** in the
  annual plan-vs-actual example (joining `plans`→`sales` before `sum()` multiplied
  `plan_revenue` by the sales row count). Fixed by aggregating `plans` and `sales`
  in separate subqueries, then joining. Lesson carried into [[Text_to_SQL]] rules.
- **Retrieval quality note**: LaBSE has a lexical lean — e.g. "сколько заработал
  продавец" (revenue) ranks the headcount example above the revenue one because
  of the shared word "продавец". Acceptable: top-3 still supplies relevant SQL;
  worth revisiting if eval (stage 7) shows misses. Schema-doc cosine scores are
  low in absolute terms (~0.3) but rank correctly (long doc vs short query).
