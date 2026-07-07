# Retail AI Assistant — Wiki Index

> **Read this page first in every session.** This wiki is the compiled
> knowledge for the project. `raw/` holds immutable source material
> (the spec); `wiki/` is the LLM-maintained compilation (Karpathy method).
> Update the affected pages after every completed stage.

## Pages

- [[Architecture]] — system diagram, "core knows nothing about interfaces"
- [[Data]] — `retail_demo` schema, synthetic data patterns, generator
- [[Text_to_SQL]] — pipeline, schema RAG, few-shot RAG, validation
- [[Qdrant_Collections]] — `retail_schema`, `retail_few_shot`, embeddings
- [[Artifacts]] — chart_builder (PNG), excel_exporter (xlsx)
- [[Interfaces]] — desktop (Streamlit), telegram (aiogram), `AssistantResponse`
- [[Evaluation]] — methodology, metrics, results
- [[Roadmap]] — the 10 stages with status checkboxes

## Fixed environment facts (do not re-ask, do not re-install)

- **ClickHouse** — already running locally, HTTP `localhost:8123`, native `9000`.
  Requires a **password** (login is not passwordless). Credentials live in `.env`
  (`CH_USER` / `CH_PASSWORD`). Only ever touch database **`retail_demo`**.
- **Qdrant** — already running, `localhost:6333`. Other collections exist
  (`jewelry_items`, `terraforming`) — **never touch them**. Only touch
  `retail_schema` and `retail_few_shot`.
- **Ollama** — already running, `localhost:11434`, `qwen2.5-coder:14b` pulled.
- macOS, Python 3.11+ (3.14 present), git repo. Local / air-gapped: no external LLM APIs.

## Safety rails

- ClickHouse: only `retail_demo`. Never query/modify/drop other databases.
- Qdrant: only `retail_schema`, `retail_few_shot`.
- Git: no force push, no `reset --hard`. One commit per stage: `stage N: ...`.

## Working protocol

1. Start every session by reading this page.
2. Follow the stage order in [[Roadmap]] strictly — do not jump ahead.
3. After finishing a stage: update the affected wiki pages, tick [[Roadmap]], commit.
4. Ambiguities: make a reasonable call, record it under "Open questions / decisions"
   on the relevant page. Never silently deviate from an explicit spec statement.
