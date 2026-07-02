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

## Updating / reinstalling over an existing install

If the environment variable `INDIEBIZ_UPDATE` is `standard` or `full`, this is a
re-install over an existing clone, **not** a fresh install. The dumb bootstrap
has already done the overwrite before handing off to you:

- It ran `git fetch` + `git reset --hard`, so **every tracked file** (all backend
  / frontend / scripts code, and the shipped "standard" IBL vocabulary under
  `data/ibl_nodes_src/` + `data/ibl_nodes.yaml` + guides + system docs) is now
  exactly the GitHub state.
- **`.gitignore` is the preservation boundary.** `git reset --hard` never touches
  untracked/ignored files, so the user's `.env`, API keys, `data/*_ai_config.json`,
  `data/my_profile.txt`, conversation/business/calendar DBs, `data/world_pulse.db`
  (episodic history), and everything under `projects/` are all intact.
- For `INDIEBIZ_UPDATE=full` only, the bootstrap additionally ran
  `scripts/reset_runtime_state.py`, which factory-reset the *learned/tuning*
  artifacts (hippocampus `data/ibl_usage.db`, forager memory, distilled recipes,
  `data/model_gear.json`, `data/package_meta.json`) back to shipped defaults.
  `standard` keeps all of that learning.

**On an update your job is narrower — do NOT run the full fresh-install flow:**
1. Do **not** recreate `.env` or overwrite any existing `data/*_ai_config.json` —
   they hold the user's keys and were deliberately preserved. Read them if you
   need to; never clobber them.
2. Make sure the venv + dependencies still satisfy the profile (a `pip install`
   is idempotent; add anything the fresh code now imports).
3. Rebuild the IBL vocabulary: `.venv/bin/python scripts/build_ibl_nodes.py`
   (this also regenerates `data/package_meta.json`). Confirm `--check` passes.
4. For a `full` update, the hippocampus index was wiped — rebuild it from the
   **shipped** training corpus if the heavy deps are installed (look for
   `backend/rebuild_usage_db.py` or the rebuild routine). The backend also
   rebuilds a missing hippocampus on boot, so treat this as best-effort.
5. Skip the edition/locale step (§3) unless the user explicitly asks to change it.
6. Verify the backend boots (§7) and finish (§8).

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

### 3. Choose package edition + locale
IndieBiz ships with every tool package *installed*. Each package is a
self-contained capability (code + its IBL vocabulary), so the install set can be
narrowed by a single deterministic filter — you don't hand-pick packages.

Ask the user two short questions (default in brackets; in unattended mode use the
defaults or `INDIEBIZ_EDITION` / `INDIEBIZ_LOCALE`):
- **Edition** [standard]: `standard` = only packages that need **no external API
  key** and are **lightweight** (they just work out of the box); `full` =
  everything, including packages that need their own service keys or heavy deps
  (playwright, torch, moviepy, …). Standard is the right default; the user can
  add any package later.
- **Locale** [universal]: `universal` = region-neutral packages only; `kr` =
  also include Korea-specific packages (real-estate, legal, KOSIS statistics,
  culture, …). Pick `kr` only if the user is in / works with Korea.

Then apply it with the venv (needs pyyaml, installed in step 2):
```
.venv/bin/python scripts/apply_edition.py --edition <standard|full> --locale <universal|kr|all>
```
Run `--list` first to show the membership, or `--dry-run` to preview moves.
Non-selected packages are moved to `not_installed/` (they stay in the catalog as
*available* for on-demand install — nothing is deleted). This also rebuilds the
IBL vocabulary. Re-running with a wider edition restores the packages it parked.
This is safe to skip entirely (everything stays installed) if the user wants all
packages.

### 4. Wire the AI key + provider
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

### 5. Model gear (hardware profile → tiers)
If `data/model_gear.json` exists, read it and set a gear matching the profile
(lean → most economical, full → max). If it doesn't exist, skip — the system
has a default.

### 6. Frontend (optional)
Only if installing the desktop UI: ensure Node ≥ 18 (`node --version`); then
`cd frontend && npm install`. This can be large and slow — tell the user it's
optional and continue on failure (backend still works).

### 7. Verify the backend boots
- Start it in the background using the venv:
  `.venv/bin/python backend/api.py` (Windows: `.venv\Scripts\python.exe backend\api.py`).
- Poll `http://localhost:8765/` (or an obvious health/docs route like `/docs`)
  a few times with a short delay. A 200/response means success.
- Read the startup logs if it fails; fix missing deps (install them) or config
  errors and retry. Then **stop** the test process (don't leave a zombie).

### 8. Finish
Report the profile chosen, what was installed vs skipped, and the **exact**
command to run it:
- macOS/Linux: `cd <repo> && ./start.sh` (backend + frontend), or
  `.venv/bin/python backend/api.py` for backend-only.
- Windows: `.venv\Scripts\python.exe backend\api.py` for the backend; the
  frontend via `cd frontend; npm run electron:dev` if installed.

Mention that the system replies in whatever language the user writes to it (no
language setting needed), while the bundled guides and UI labels are currently
Korean. Say this in the user's own language.

Then call the `finish` tool with `ok: true`.

## Principles
- **Read before you write.** The repo is the source of truth; this guide is a map.
- **The backend booting is success.** Frontend, hippocampus, and extras are
  layered on top and may be skipped on weak hardware without failing the install.
- **Never destructive.** No `rm -rf`, no `sudo` unless truly required and
  confirmed. Work inside the repo dir and the venv.
- **Be honest in the summary** about what you skipped and why.
