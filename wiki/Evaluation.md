# Evaluation

See [[Index]]. Related: [[Text_to_SQL]].
Source: `raw/project_spec_en.md` §7 (`eval/`), §8 stage 7. **Status: done (stage 7).**

- `eval/test_questions.json` — 30 questions with reference SQL (canonical, all 30
  validated to run). Phrasings deliberately differ from the few-shot set so we
  measure generalization, not memorization.
- `eval/run_eval.py` — runs the full pipeline per question and compares.
  Run: `python eval/run_eval.py` → writes `eval/results.md`.

## Metrics (definitions)
- **Execution accuracy** — generated SQL runs without error.
- **Result accuracy** — generated result matches the reference **by denotation**:
  rows compared as a set (row-order invariant), cells sorted within each row
  (column-order invariant), numbers rounded to 2 dp. Strict on shape: an extra
  column or a different grouping counts as a mismatch.

## Results (model `qwen2.5-coder:14b`, 30 questions)

| Metric | Value |
|---|---|
| Execution accuracy | **97%** (29/30) |
| Result accuracy | **70%** (21/30) |
| Avg attempts / question | 1.10 |

By category: `top_n` 100%, `aggregation` 80%, `join` 60%, `time_series` 50%,
`plan_vs_actual` 50%, `window` 50% exec / 50% result. Full report: `eval/results.md`.

## Model comparison — local vs external (Groq)

Same 30 questions, same pipeline; only the LLM backend differs (see [[Architecture]]
LLM backend). Full Groq report: `eval/results_groq.md`.

| Backend | Model | Execution | Result | Avg attempts |
|---|---|---|---|---|
| local (default) | `qwen2.5-coder:14b` (Ollama) | 97% (29/30) | 70% (21/30) | 1.10 |
| external | `llama-3.3-70b-versatile` (Groq) | **100%** (30/30) | **77%** (23/30) | **1.00** |

Category deltas (result accuracy): the external model lifts `join` 60→100% and
`window` result 50→ (exec 75→100%, it fixed the year-over-year window local
couldn't run), needing **zero retries** (avg 1.00 vs 1.10). It fixed local's
genuine errors — fan-out on "by format" (Q10), silver-share-of-total (Q12),
weekend = Sat/Sun (Q14), the YoY window (Q24). Its remaining 7 misses are mostly
**near-correct**: rounding/precision on percentage queries (Q5, Q19, Q28), the
extra-column case (Q22), and the two defensible interpretations (Q15 "продавцы"
scope, Q29 top-hour) — so effective quality is materially higher than the strict
77% suggests. Takeaway: the stronger external model is a clear upgrade for
benchmarking, while `auto` keeps local as a zero-cost, always-available fallback.

## Failure analysis (the 9 non-matches)

Categorized honestly rather than tuned away:

- **Genuine model errors (6)** — Q5 grouped by month not quarter; Q10 dragged in
  `plans` for a plain "by format" question (despite the prompt rule) → fan-out;
  Q12 computed silver share over silver-only (=100%) instead of over the total;
  Q14 used `toDayOfWeek IN (7,1)` (Sun+Mon) instead of `(6,7)` (Sat+Sun);
  Q19 computed per-store % instead of overall total/total; Q24 (the only
  execution failure) couldn't produce a working year-over-year window (3 retries).
- **Defensible interpretation, differs from reference (2)** — Q15 read "продавцы"
  as only `продавец-консультант` (reference: all `%продавец%`); Q29 returned the
  single top hour (reference: all hours ranked). Both reasonable readings.
- **Metric strictness (1)** — Q22's ranking is correct but it added a `city`
  column, so the denotation differs. The answer is essentially right.

So "effective" correctness is ~22–24/30 depending on how the 3 borderline cases
are scored; the headline **70%** uses the strict metric (no cherry-picking).

## Improvement candidates (future tuning pass, not done here)
- Prompt: define weekend as Sat(6)/Sun(7); clarify "по кварталам" → `toQuarter`;
  reinforce "aggregate at the level the question asks" (overall vs per-store).
- Few-shot: add a working year-over-year window example (helps Q24) and a
  count-over-HAVING example (the stage-4 known limitation).
- Metric: optionally relax to ignore extra descriptive columns (would pass Q22).

## Open questions / decisions
- Denotation comparison chosen over exact string/columns match — robust to
  harmless row/column reordering, still strict on values and shape.
- Eval is **non-deterministic** (temp 0.1): numbers move a few points run-to-run.
  Treat as an indicative snapshot, not an exact score.