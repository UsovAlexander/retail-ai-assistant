# CLAUDE.md — working rules for this project

**Retail AI Assistant** — a local AI analyst assistant for a (jewelry) retail
company: Ollama LLM + ClickHouse + Qdrant, with a Streamlit chat UI and a
Telegram bot, producing chart-PNG and Excel artifacts.

## The LLM Wiki (Karpathy method) — read this first

This project uses the LLM Wiki pattern
(https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f):

- **`raw/`** is the source material (the spec) — **immutable**. Read it, never edit it.
- **`wiki/`** is the **compiled knowledge** — LLM-maintained, interlinked
  `[[wiki-links]]`, one page = one concept.
- **Before starting ANY task**, your first action is to read **`wiki/Index.md`**
  and the pages relevant to the task. The wiki is the primary source of context.
- **After each completed stage** (see `wiki/Roadmap.md`), update the affected
  pages and create pages for new concepts, then commit.

## Stage discipline

- Follow the stage order in `wiki/Roadmap.md` / spec §8 **strictly**. Do not jump
  ahead (no Qdrant/LLM/UI code before its stage).
- **One commit per completed stage**, message format `stage N: short description`.

## Environment (already running locally — verify, do not install)

- **ClickHouse** — `localhost:8123` (HTTP) / `9000` (native). **Requires a password**;
  credentials in `.env` (`CH_USER`/`CH_PASSWORD`). Only ever touch DB **`retail_demo`**.
- **Qdrant** — `localhost:6333`. Only touch collections **`retail_schema`** and
  **`retail_few_shot`**. Never touch other collections (`jewelry_items`, `terraforming`).
- **Ollama** — `localhost:11434`, model `qwen2.5-coder:14b`. Local only — no external LLM APIs.
- macOS, Python 3.11+.

## Safety rails

- ClickHouse: never query/modify/drop any database other than `retail_demo`.
- Qdrant: never touch collections other than `retail_schema` / `retail_few_shot`.
- Git: no force push, no `reset --hard`.

## Code standards (spec §11)

- Python 3.11+, type hints everywhere; `dataclass`/`pydantic` for data structures.
- `logging`, never `print` (level configurable via config).
- All prompts in `src/prompts/*.txt`, not inline in code.
- Secrets only via `.env` (git-ignored). `requirements.txt` pins major versions.
- LLM calls via Ollama's OpenAI-compatible API (`base_url=http://localhost:11434/v1`);
  structured outputs via JSON mode + pydantic validation; `temperature=0.1` for
  SQL and classification.

## Ambiguity

Make a reasonable decision, record it under an **"Open questions / decisions"**
heading on the relevant wiki page, and move on. Never silently deviate from an
explicit spec statement; if the spec seems wrong, stop and ask.
