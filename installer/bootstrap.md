# IndieBiz OS — install map (for the installer agent)

You are an agent with a shell installing IndieBiz OS onto the machine you are
running on. **This is not a script.** It is a map: the destination, the landmarks
that save you from guessing, and the few hard constraints. *You* decide the exact
commands by looking at THIS machine and THIS repo — every machine differs, so a
fixed recipe would be wrong. Read the repo before you act; let what you actually
find (and the errors you actually hit) drive the next command.

## The destination

**Success = the backend boots.** It is a Python **FastAPI** server that listens on
**port 8765**; `backend/api.py` is the entrypoint. When `http://localhost:8765/`
responds, the install has succeeded. Everything else is an optional layer on top
and may be skipped on weak hardware without failing the install.

## Landmarks (things worth knowing so you don't have to rediscover them)

- **Python lives in a `.venv` at the repo root, by convention.** Create one and
  use it for all Python (the OS's system Python won't have the deps). `start.sh`
  looks for `.venv` first, so this is also what makes the run command work later.
- **Dependencies**: prefer a real list if the repo has one (a `requirements*.txt`,
  `pyproject.toml`, …). If there isn't one, infer from the backend's imports and
  let import errors during verification tell you what's still missing. The heavy
  optional deps (embedding model, torch, sqlite-vec, …) power the hippocampus —
  install them only on capable machines; the backend must boot without them.
- **Model config lives under `data/`** (files like `system_ai_config.json`,
  `model_gear.json`). Read an existing/example one to learn the real schema
  before writing — do not assume a schema. Setting the main (`system_ai`) key is
  enough to boot; other tiers fall back to it.
- **The desktop frontend is optional** — Electron + React in `frontend/`, needs
  Node ≥ 18 and `npm install`. If Node is absent or the user doesn't want a GUI,
  leave it out; the backend is fully usable headless (remote launcher / REST).
- **Package set is adjustable but not required to touch.** Everything ships
  installed. `scripts/apply_edition.py` can narrow it (skip packages that need
  their own service keys, or region-specific ones) if the user wants a leaner
  set — read its `--help`/`--list`. Skipping this entirely is fine.
- **`scripts/build_ibl_nodes.py` (run via the venv) (re)builds the IBL vocabulary**
  from source. Run it if you change the package set or after an update; `--check`
  validates it.

## Hard constraints (these you cannot derive from the repo — obey them)

- **The AI key is never yours to see.** The installer holds it. Whenever you write
  it into a config, write the literal placeholders **`{{LLM_API_KEY}}`**,
  **`{{LLM_PROVIDER}}`**, **`{{LLM_MODEL}}`** — the installer substitutes the real
  values locally on write, so the raw key never enters your context or any log.
- **Never destructive.** No `rm -rf`, no `sudo` unless truly unavoidable and
  confirmed. Stay inside the repo dir and the venv.
- **On an update, personal data is sacred.** (See below.)

## How to adapt to this machine

Match ambition to hardware, then verify empirically:

- **Weak** (low RAM, no GPU, small/ARM board): backend only, most economical
  model gear, skip the heavy embedding model / semantic index (keyword fallback
  is fine).
- **Strong** (lots of RAM, GPU / Apple Silicon): install everything, max gear.

Then **prove it**: start the backend with the venv in the background, poll
`http://localhost:8765/` a few times, read the logs if it fails, fix what's
actually missing, retry, and stop your test process (leave no zombie). Booting is
the whole game — don't declare success without seeing 8765 respond.

## Updating over an existing install

If `INDIEBIZ_UPDATE` is `standard` or `full`, the tracked code + shipped IBL
vocabulary were already overwritten from GitHub before you started. **`.gitignore`
is the preservation line**: the user's `.env`, keys, `data/*_ai_config.json`,
profile, conversation/business DBs, `data/world_pulse.db`, and `projects/` are
untouched. So: do **not** recreate `.env` or clobber existing config files — read
them, don't overwrite. Make sure deps still satisfy the profile, rebuild the IBL
vocabulary, verify the backend boots, finish. (`full` also factory-reset the
learned/tuning state; `standard` kept it. Rebuild the hippocampus index only if
its heavy deps are present — the backend also rebuilds a missing one on boot.)
Don't re-run the edition/locale narrowing unless asked.

## Finishing

Call `finish` with `ok: true` and report, in the user's language: the exact run
command (`cd <repo> && ./start.sh`, or `.venv/bin/python backend/api.py` for
backend-only), what you installed vs skipped and why, and that the system replies
in whatever language the user writes to it (the bundled guides/UI are Korean).
Be honest about anything you skipped or couldn't verify.
