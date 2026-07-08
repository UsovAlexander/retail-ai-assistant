# Roadmap

See [[Index]]. Source: `raw/project_spec_en.md` §8. Execute strictly in order;
one commit per stage (`stage N: ...`); update the wiki after each.

- [x] **Stage 1 — Project skeleton.** Folder structure, `config.py`,
  `requirements.txt`, `.env.example`, connections to CH/Qdrant/Ollama with
  availability checks (`python -m src.check_env`).
- [x] **Stage 2 — Synthetic data generator.** `retail_demo`, all 6 tables
  (994,892 sales, 2024–2026); seasonal + store-tier patterns verified. → [[Data]]
- [x] **Stage 3 — Qdrant collections.** `retail_schema` (6) + `retail_few_shot`
  (26 validated examples); LaBSE 768-d/cosine; retrieval smoke-tested. Also
  fixed a plan-vs-actual data-realism issue + a few-shot fan-out bug.
  → [[Qdrant_Collections]]
- [x] **Stage 4 — Text-to-SQL core.** `llm_client` + `sql_generator` (schema RAG
  + few-shot RAG + retry) + `validator`; verified 8/8 execute on manual
  questions. → [[Text_to_SQL]]
- [ ] **Stage 5 — Chart builder + Excel exporter** (with unit tests). → [[Artifacts]]
- [ ] **Stage 6 — Orchestrator + summarizer.** Full core, `core.ask()` end-to-end.
- [ ] **Stage 7 — Eval.** 30 questions, execution + result accuracy → `eval/results.md`.
  → [[Evaluation]]
- [ ] **Stage 8 — Desktop UI.** → [[Interfaces]]
- [ ] **Stage 9 — Telegram bot.** → [[Interfaces]]
- [ ] **Stage 10 — README + polish.** Screenshots, demo GIF, eval metrics.

## Status log

- **Stage 1** — skeleton + `check_env` verifying all three live services. _(done)_
- **Stage 2** — generator built; `retail_demo` populated (995k sales); sanity
  queries confirm Dec + Feb–Mar peaks and leader/laggard store tiers. Actual
  numbers in [[Data]]. _(done; plan-vs-actual recalibrated at stage 3)_
- **Stage 3** — both Qdrant collections built (schema 6, few-shot 26), LaBSE
  embeddings, retrieval verified; other collections untouched. _(done)_
- **Stage 4** — text-to-SQL pipeline works end-to-end (RAG → Ollama → validate →
  execute, ≤3 retries). 8/8 manual questions execute; one nested count-over-HAVING
  shape noted as a known limitation. _(done)_
- **Next: Stage 5** — chart builder + Excel exporter (with unit tests).
