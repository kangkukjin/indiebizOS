# IndieBiz OS — install guide (for the installer agent)

You are installing IndieBiz OS onto the machine you are running on. This file is
the **install vocabulary**: a set of known landmarks and a strategy. It may be
slightly stale — **always confirm against the real repo** (read files) before
acting. Compose these steps; do not invent shell commands from nothing.

## What you are installing

- **Backend**: Python **FastAPI** server, listens on **port 8765**
  (`backend/api.py` is the entrypoint). This is the core — it must run.
- **Frontend**: **Electron + React (TypeScript)** in `frontend/`. This is the
  desktop UI. It is **optional** — the backend is fully usable headless (remote
  launcher / REST) without it. Only install it if Node ≥ 18 is present and the
  user wants the desktop app.
- **Data**: runtime state under `data/` (configs, SQLite DBs, guides, the
  fine-tuned embedding model, packages).
- **Start script**: `start.sh` (macOS/Linux) launches backend + frontend.

## The one hard rule about the AI key

The user's LLM key is held by the installer, not by you. Whenever you write it
into a config, use the literal placeholder **`{{LLM_API_KEY}}`** (also
`{{LLM_PROVIDER}}`, `{{LLM_MODEL}}`). The installer substitutes the real values
locally on write/run, so the raw key never enters your context or any log.

## Steps

### 1. Understand this machine
You already have a hardware snapshot in the system prompt. Refine only if needed
(`python3 --version`, `node --version`, RAM, CPU, GPU). Decide a **profile**:

- **lean** — low RAM (≲ 4 GB), no GPU, or a small/ARM SBC / server: backend
  only, lightweight model gear, **skip** the heavy embedding model / hippocampus
  semantic index (keyword fallback is fine).
- **standard** — a normal laptop/desktop: backend + frontend, balanced gear.
- **full** — lots of RAM + GPU/Apple Silicon: everything, including the
  embedding model, max gear.

### 2. Backend dependencies
- Create an isolated venv at the repo root: `python3 -m venv .venv`
  (on Windows the interpreter is `.venv\Scripts\python.exe`; on unix
  `.venv/bin/python`). Use the venv's pip for everything below.
- **Find the dependency list**: look for `requirements.txt`, `pyproject.toml`,
  `Pipfile`, or a `requirements*.txt` under `backend/`. If one exists, install
  from it: `.venv/bin/python -m pip install -r <file>`.
- **If no requirements file exists**, infer core deps by reading the top imports
  of `backend/api.py` and the `backend/api_*.py` / core modules. At minimum the
  backend needs: `fastapi`, `uvicorn[standard]`, `httpx`/`requests`,
  `python-dotenv`, `pyyaml`, `websockets`, and the AI SDK for the chosen
  provider (`anthropic`, `openai`, or `google-genai`). Install what the imports
  actually require; add more as import errors reveal them during verification.
- Heavy/optional deps (`sentence-transformers`, `torch`, `sqlite-vec`, etc.)
  power the hippocampus. Install them **only** for the `standard`/`full`
  profile. If they fail to build on this machine, fall back to `lean` and
  continue — the backend must still boot without them.

### 3. Wire the AI key + provider
- Read `.env.example` at the repo root. Create `.env` from it (copy), and set
  any owner/identity fields the user provides. Leave external service keys as
  their placeholders — the user adds those later as they use features.
- Find how the backend selects its model. Look under `data/` for existing or
  example config files such as `system_ai_config.json`,
  `lightweight_ai_config.json`, `midtier_ai_config.json`, and
  `model_gear.json`. **Read an existing one to learn the exact schema**, then
  write the chosen provider/model/key into it using the placeholders. If only
  some tiers have keys, the lightweight/midtier tiers fall back to the main key
  — setting the main (`system_ai`) config is enough to boot.
- Do **not** hardcode a schema you haven't confirmed by reading the repo.

### 4. Model gear (hardware profile → tiers)
If `data/model_gear.json` exists, read it and set a gear matching the profile
(lean → most economical, full → max). If it doesn't exist, skip — the system
has a default.

### 5. Frontend (optional)
Only if installing the desktop UI: ensure Node ≥ 18 (`node --version`); then
`cd frontend && npm install`. This can be large and slow — tell the user it's
optional and continue on failure (backend still works).

### 6. Verify the backend boots
- Start it in the background using the venv:
  `.venv/bin/python backend/api.py` (Windows: `.venv\Scripts\python.exe backend\api.py`).
- Poll `http://localhost:8765/` (or an obvious health/docs route like `/docs`)
  a few times with a short delay. A 200/response means success.
- Read the startup logs if it fails; fix missing deps (install them) or config
  errors and retry. Then **stop** the test process (don't leave a zombie).

### 7. Finish
Report the profile chosen, what was installed vs skipped, and the **exact**
command to run it:
- macOS/Linux: `cd <repo> && ./start.sh` (backend + frontend), or
  `.venv/bin/python backend/api.py` for backend-only.
- Windows: `.venv\Scripts\python.exe backend\api.py` for the backend; the
  frontend via `cd frontend; npm run electron:dev` if installed.

Then call the `finish` tool with `ok: true`.

## Principles
- **Read before you write.** The repo is the source of truth; this guide is a map.
- **The backend booting is success.** Frontend, hippocampus, and extras are
  layered on top and may be skipped on weak hardware without failing the install.
- **Never destructive.** No `rm -rf`, no `sudo` unless truly required and
  confirmed. Work inside the repo dir and the venv.
- **Be honest in the summary** about what you skipped and why.
