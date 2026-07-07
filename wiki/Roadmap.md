# Roadmap

See [[Index]]. Source: `raw/project_spec_en.md` §8. Execute strictly in order;
one commit per stage (`stage N: ...`); update the wiki after each.

- [x] **Stage 1 — Project skeleton.** Folder structure, `config.py`,
  `requirements.txt`, `.env.example`, connections to CH/Qdrant/Ollama with
  availability checks (`python -m src.check_env`).
- [ ] **Stage 2 — Synthetic data generator.** `retail_demo`, all 6 tables;
  seasonal peaks visible via a simple query. → [[Data]]
- [ ] **Stage 3 — Qdrant collections.** `retail_schema` + `retail_few_shot`
  (20–30 manual few-shot examples). → [[Qdrant_Collections]]
- [ ] **Stage 4 — Text-to-SQL core.** `sql_generator` + `validator`; verify on
  5–10 questions. → [[Text_to_SQL]]
- [ ] **Stage 5 — Chart builder + Excel exporter** (with unit tests). → [[Artifacts]]
- [ ] **Stage 6 — Orchestrator + summarizer.** Full core, `core.ask()` end-to-end.
- [ ] **Stage 7 — Eval.** 30 questions, execution + result accuracy → `eval/results.md`.
  → [[Evaluation]]
- [ ] **Stage 8 — Desktop UI.** → [[Interfaces]]
- [ ] **Stage 9 — Telegram bot.** → [[Interfaces]]
- [ ] **Stage 10 — README + polish.** Screenshots, demo GIF, eval metrics.

## Status log

- **Stage 1** — skeleton + `check_env` verifying all three live services. _(done)_
- **Stage 2** — in progress.
