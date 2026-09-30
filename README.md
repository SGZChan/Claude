# Laya — System One AI

Laya is a local, agentic, self-learning assistant. It runs a small (~0.5B) model on your machine, uses tools to get things done, and gets faster the more you use it: repeated successful behaviour is promoted into **skills** that run instantly without the model ("System One"), while novel goals go through a slower constrained reasoning loop.

```
laya/        Python package (agent, tools, memory, learning, FastAPI) + tests
dashboard/   React + TypeScript dashboard (Vite)
```

## Quick start (Windows)
Double-click **`setup.bat`** (needs Python 3.10+ and Node 18+). It creates a venv, installs Laya, downloads the 0.5B model, builds the dashboard and starts everything. Use `setup.bat /nomodel` to skip the model, `/norun` to skip launching. Afterwards start with **`run.bat`**.

## Quick start (manual)

```bash
cd laya
pip install -e ".[dev]"
pytest                                   # uses the scripted mock model
laya run "What is 17*23 and save it to notes"
laya practice -n 9                       # self-practice: watch skills get learned
```

### Use the real 0.5B model
```bash
pip install -e ".[llm]"
python scripts/download_model.py         # Qwen2.5-0.5B-Instruct Q4_K_M (~400 MB) -> ./models
laya run "What is 17*23?"                # backend auto-detects the GGUF file
```
Without the model file Laya falls back to a deterministic mock so everything (tests, dashboard) still works. Configure via env vars (see `laya/.env.example`).

### Dashboard
```bash
cd dashboard && npm install && npm run build   # then: cd ../laya && laya serve  -> http://127.0.0.1:8000
# or, for development: `laya serve` (port 8000) + `npm run dev` in dashboard/
```
Pages: Overview (KPIs, Today panel, learning curve), Features, Run console (live steps, approvals, stop), Runs, Skills, Memory, Learning, Tools & permissions, Schedules, System (+ kill switch).

## Features you can switch on and off
The dashboard's **Features** page lets you pick what Laya can do (25 features: assistant, files & knowledge base, data wrangling, web digest, developer helper, message triage, utilities, plugins, learning toggles, background jobs) or apply a preset. See [docs/FEATURES.md](docs/FEATURES.md) for the full list and a roadmap of more ideas.

## How it learns (no weight updates)
1. Every run is stored; a one-line **reflection** lesson is added to vector memory and retrieved into later prompts.
2. Goals are reduced to a *shape* (numbers/quoted strings become slots). When the same shape yields the same tool sequence **3 times**, it becomes a **skill**.
3. The **System One router** matches new goals to skills and runs them with zero model calls; failures fall back to the model.
4. 👍/👎 and corrections adjust skill scores (two rejections disable a skill) and memory.
5. **Self-practice** runs verifiable tasks; **export** produces JSONL for an optional offline fine-tune.

## Safety
Tools have tiers (`safe` / `confirm` / `blocked`); `confirm` tools (file writes, web fetch, sandboxed Python, read-only shell) need approval each run, even inside skills. Files are confined to a workspace directory, web fetch is allow-listed, runs have step and time budgets, and a kill switch stops everything.

## Use cases
Personal assistant · private file helper · web digests · data wrangling · dev helper · scheduled automation · email triage (planned) · personal knowledge base · offline/edge deployment · plugin platform (`@registry.register` tools).
