#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
IndieBiz OS - minimal self-installer seed.

An LLM agent that installs IndieBiz OS onto *this* machine. It detects the
hardware, reads the repo, installs the right dependencies, wires up your AI
key, picks a hardware-appropriate profile, and verifies the backend boots.

- Standard library only (no pip needed to *run the installer itself*).
- Bring your own AI API key: Anthropic (sk-ant-...), OpenAI (sk-...),
  or Google Gemini (AIza...). Provider is inferred from the key, or set
  INDIEBIZ_PROVIDER = anthropic | openai | google.

The intelligence lives in installer/bootstrap.md (author-time install
vocabulary) + this loop. The agent *composes* that vocabulary against the
real repo state; it does not freestyle from nothing.

Env knobs:
  INDIEBIZ_API_KEY   your LLM key (else you're prompted)
  INDIEBIZ_PROVIDER  anthropic | openai | google  (else inferred from key)
  INDIEBIZ_MODEL     override the model id
  INDIEBIZ_YES=1     unattended: auto-approve every command (use with care)
  INDIEBIZ_EDITION   standard | full   (package edition; see installer/bootstrap.md step 3)
  INDIEBIZ_LOCALE    universal | kr | all   (which regional packages to install)
  INDIEBIZ_UPDATE    standard | full | off  (set by the bootstrap when re-installing over
                     an existing clone; the code + vocabulary were already overwritten from
                     GitHub, and for 'full' the learned/tuning state was factory-reset —
                     see the "Updating an existing install" section of installer/bootstrap.md)
"""

import os
import sys
import json
import time
import platform
import subprocess
import urllib.request
import urllib.error

# --------------------------------------------------------------------------
# Paths
# --------------------------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)                      # repo root (installer/ lives inside it)
REPO_URL = "https://github.com/kangkukjin/indiebizOS"

# Frozen (PyInstaller single-binary) mode: the binary is downloaded on its own,
# outside any clone. __file__ then lives in a throwaway extraction dir, so the
# "parent of installer/" rule would point ROOT at a temp path that vanishes on
# exit (and the write gate would confine the agent there). Instead: bundled
# data (bootstrap.md) is read from the extraction dir, and ROOT becomes the
# *install destination* — INDIEBIZ_DIR or ~/indiebizOS — which the agent
# populates by cloning/downloading the repo as its first step (see
# build_system's "repo not present" note).
if getattr(sys, "frozen", False):
    HERE = getattr(sys, "_MEIPASS", HERE)
    ROOT = os.path.abspath(
        os.environ.get("INDIEBIZ_DIR")
        or os.path.join(os.path.expanduser("~"), "indiebizOS"))

# --------------------------------------------------------------------------
# Terminal I/O  (must work even when the bootstrap was piped via curl|bash,
# where sys.stdin is the script itself, not the keyboard)
# --------------------------------------------------------------------------
def _color(code, s):
    if os.environ.get("NO_COLOR"):
        return s
    return "\033[%sm%s\033[0m" % (code, s)

def say(s):  print(_color("1;36", "[indiebiz] ") + s, flush=True)
def warn(s): print(_color("1;33", "[indiebiz] ") + s, flush=True)
def err(s):  print(_color("1;31", "[indiebiz:error] ") + s, file=sys.stderr, flush=True)
def dim(s):  print(_color("2", s), flush=True)

_TTY = None
def _tty():
    """A read/write handle to the real terminal, or None if unavailable."""
    global _TTY
    if _TTY is not None:
        return _TTY
    if os.name == "posix":
        try:
            _TTY = open("/dev/tty", "r+")
            return _TTY
        except Exception:
            pass
    # Windows / normal invocation: stdin is the console
    _TTY = None
    return None

def ask_line(question, secret=False):
    t = _tty()
    if t is not None:
        t.write(question)
        t.flush()
        line = t.readline()
        return line.rstrip("\n")
    # fall back to stdin/getpass
    if secret:
        try:
            import getpass
            return getpass.getpass(question)
        except Exception:
            pass
    try:
        return input(question)
    except EOFError:
        return ""

# --------------------------------------------------------------------------
# LLM key + provider resolution
# --------------------------------------------------------------------------
def infer_provider(key):
    if key.startswith("sk-ant-"):
        return "anthropic"
    if key.startswith("AIza"):
        return "google"
    if key.startswith("sk-") or key.startswith("sess-"):
        return "openai"
    return ""

# 설치는 절차적 작업이라 각 프로바이더의 저렴한 현행 모델이 기본값.
# 모델 세대는 계속 바뀌므로 이 목록은 참고 기본값일 뿐 — 실행 시 프롬프트나
# INDIEBIZ_MODEL 로 아무 모델 ID나 지정할 수 있다.
DEFAULT_MODEL = {
    "anthropic": "claude-haiku-4-5",
    "openai":    "gpt-5-mini",
    "google":    "gemini-3.1-flash-lite",
}

def resolve_credentials():
    key = os.environ.get("INDIEBIZ_API_KEY", "").strip()
    if not key:
        say("Paste your AI API key (Anthropic sk-ant-… / OpenAI sk-… / Google AIza…).")
        say("It is used only to run this installer and is written into your local config.")
        key = ask_line("API key: ", secret=True).strip()
    if not key:
        err("No API key provided. Aborting.")
        sys.exit(1)

    provider = os.environ.get("INDIEBIZ_PROVIDER", "").strip().lower() or infer_provider(key)
    if provider not in DEFAULT_MODEL:
        say("Could not infer provider from the key.")
        provider = ask_line("Provider [anthropic/openai/google]: ").strip().lower()
    if provider not in DEFAULT_MODEL:
        err("Unknown provider %r. Aborting." % provider)
        sys.exit(1)

    # 모델 이름도 사용자가 결정한다 — env(INDIEBIZ_MODEL) > 프롬프트 > 기본값.
    # 모델 세대가 빨리 바뀌어 하드코딩 기본값은 금방 낡으므로(예: gemini-2.0 시절 기본값),
    # 대화형이면 항상 물어보고 Enter=기본값. 무인 모드(INDIEBIZ_YES=1)는 프롬프트 스킵.
    model = os.environ.get("INDIEBIZ_MODEL", "").strip()
    if not model:
        if os.environ.get("INDIEBIZ_YES") == "1":
            model = DEFAULT_MODEL[provider]
        else:
            entered = ask_line(
                "Model id [Enter = %s]: " % DEFAULT_MODEL[provider]).strip()
            model = entered or DEFAULT_MODEL[provider]
    return key, provider, model

# --------------------------------------------------------------------------
# HTTP
# --------------------------------------------------------------------------
def http_post_json(url, headers, payload, timeout=180):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    last = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8")
            except Exception:
                pass
            if e.code in (429, 500, 502, 503, 529) and attempt < 3:
                wait = 2 ** attempt
                warn("LLM API %s — retrying in %ss" % (e.code, wait))
                time.sleep(wait)
                last = "%s: %s" % (e.code, body)
                continue
            raise RuntimeError("LLM API error %s: %s" % (e.code, body))
        except urllib.error.URLError as e:
            if attempt < 3:
                time.sleep(2 ** attempt)
                last = str(e)
                continue
            raise RuntimeError("Network error calling LLM: %s" % e)
    raise RuntimeError("LLM API failed: %s" % last)

# --------------------------------------------------------------------------
# Tool definitions (provider-neutral)
# --------------------------------------------------------------------------
TOOLS = [
    {
        "name": "run",
        "description": (
            "Run a shell command in the repo directory and get stdout/stderr/exit code. "
            "Use for probing hardware, installing dependencies, and verifying the backend. "
            "You may use the placeholders {{LLM_API_KEY}}, {{LLM_PROVIDER}}, {{LLM_MODEL}} "
            "and they will be substituted locally (the raw key never appears in your context)."
        ),
        "schema": {
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "The shell command to run."},
                "explain": {"type": "string", "description": "One short line: why you run this."},
            },
            "required": ["command", "explain"],
        },
    },
    {
        "name": "write_file",
        "description": (
            "Write a file (creating parent dirs). Prefer this over shell heredocs for config. "
            "Placeholders {{LLM_API_KEY}}, {{LLM_PROVIDER}}, {{LLM_MODEL}} are substituted "
            "locally on write, so put {{LLM_API_KEY}} where the key belongs."
        ),
        "schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path (absolute, or relative to repo root)."},
                "content": {"type": "string"},
                "explain": {"type": "string"},
            },
            "required": ["path", "content", "explain"],
        },
    },
    {
        "name": "read_file",
        "description": "Read a text file to understand the repo (config schemas, imports, examples).",
        "schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "max_bytes": {"type": "integer", "description": "Default 20000."},
            },
            "required": ["path"],
        },
    },
    {
        "name": "ask",
        "description": "Ask the user a question (e.g. an optional external API key, or a yes/no choice). Returns their answer.",
        "schema": {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
                "secret": {"type": "boolean", "description": "True to hide the input (for secrets)."},
            },
            "required": ["question"],
        },
    },
    {
        "name": "finish",
        "description": "Call when installation is complete (or cannot proceed). Ends the installer.",
        "schema": {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "description": "What was installed and the chosen profile."},
                "how_to_run": {"type": "string", "description": "Exact command(s) the user runs to start it."},
                "ok": {"type": "boolean", "description": "True if install succeeded."},
            },
            "required": ["summary", "how_to_run"],
        },
    },
]

# --------------------------------------------------------------------------
# Tool execution  (with a light safety gate)
# --------------------------------------------------------------------------
_ALLOW_ALL = os.environ.get("INDIEBIZ_YES", "").lower() in ("1", "true", "yes")

# commands we auto-run without asking (read-only probes + standard, scoped installs)
_SAFE_PREFIXES = (
    "uname", "sw_vers", "sysctl", "nproc", "free", "df", "cat ", "ls", "head ",
    "tail ", "grep ", "find ", "echo ", "printf ", "pwd", "which ", "command -v",
    "test ", "mkdir -p", "printenv", "env", "node -v", "node --version",
    "npm -v", "npm --version", "python3 --version", "python --version",
    "python3 -m venv", "python -m venv", "python3 -m pip", "python -m pip",
    "pip install", "pip3 install", "npm install", "npm ci", "systeminfo",
    "wmic ", "ver", "git status", "git rev-parse", "git branch", "git log",
    "vm_stat", "lscpu", "getconf",
)
# tokens that always require confirmation, even if a safe prefix matched
_DANGER = (
    " rm ", "rm -", "sudo", "mkfs", " dd ", "shutdown", "reboot", "kill ",
    "pkill", "chmod 777", "chown ", "> /etc", ">/etc", "| sh", "| bash",
    "curl ", "wget ", "format ", "del /", "rmdir /", ":(){", "eval ",
)

# scoped install/build invocations are safe wherever they appear in the command
# (covers venv interpreters like `.venv/bin/python -m pip install ...`)
_SAFE_CONTAINS = (
    "-m pip install", "-m pip download", "-m pip --version", "-m venv ",
    "-m pip list", " pip install ", "npm install", "npm ci",
)

def _looks_safe(cmd):
    low = " " + cmd.strip() + " "
    for d in _DANGER:
        if d in low:
            return False
    c = cmd.strip()
    if any(c.startswith(p) for p in _SAFE_PREFIXES):
        return True
    return any(s in low for s in _SAFE_CONTAINS)

def _confirm(kind, detail):
    global _ALLOW_ALL
    if _ALLOW_ALL:
        return True
    print(_color("1;35", "\n  ⟶ %s:" % kind))
    print("    " + detail.replace("\n", "\n    "))
    ans = ask_line(_color("1;35", "  approve? [Y/n/a=all/q=quit] ")).strip().lower()
    if ans in ("q", "quit"):
        err("Aborted by user.")
        sys.exit(1)
    if ans == "a":
        _ALLOW_ALL = True
        return True
    return ans in ("", "y", "yes")

def _subst(text, key, provider, model):
    if text is None:
        return text
    return (text.replace("{{LLM_API_KEY}}", key)
                .replace("{{LLM_PROVIDER}}", provider)
                .replace("{{LLM_MODEL}}", model))

def _resolve_path(p):
    p = os.path.expanduser(p)
    if not os.path.isabs(p):
        p = os.path.join(ROOT, p)
    return os.path.normpath(p)

def exec_tool(name, args, creds):
    key, provider, model = creds
    try:
        if name == "run":
            cmd = args.get("command", "")
            explain = args.get("explain", "")
            shown = cmd  # never reveal the substituted key in prompts/logs
            if not _looks_safe(cmd):
                if not _confirm("run command (%s)" % explain, shown):
                    return "SKIPPED by user."
            else:
                dim("  $ " + shown)
            real = _subst(cmd, key, provider, model)
            proc = subprocess.run(
                real, shell=True, cwd=ROOT, capture_output=True, text=True, timeout=1800
            )
            out = (proc.stdout or "")[-8000:]
            errout = (proc.stderr or "")[-4000:]
            return "exit=%d\n--- stdout ---\n%s\n--- stderr ---\n%s" % (proc.returncode, out, errout)

        if name == "write_file":
            path = _resolve_path(args["path"])
            explain = args.get("explain", "")
            if not path.startswith(os.path.normpath(ROOT) + os.sep) and path != os.path.normpath(ROOT):
                if not _confirm("write OUTSIDE repo: %s (%s)" % (path, explain), "(outside repo dir)"):
                    return "SKIPPED by user."
            else:
                dim("  ✎ write " + os.path.relpath(path, ROOT))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(_subst(args["content"], key, provider, model))
            return "wrote %d bytes to %s" % (os.path.getsize(path), path)

        if name == "read_file":
            path = _resolve_path(args["path"])
            mb = int(args.get("max_bytes") or 20000)
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                data = f.read(mb)
            return data if data else "(empty file)"

        if name == "ask":
            q = args.get("question", "")
            ans = ask_line(_color("1;32", "  ? " + q + " "), secret=bool(args.get("secret")))
            return ans

        return "unknown tool: %s" % name
    except subprocess.TimeoutExpired:
        return "ERROR: command timed out (30 min)."
    except FileNotFoundError as e:
        return "ERROR: %s" % e
    except Exception as e:
        return "ERROR: %s" % e

# --------------------------------------------------------------------------
# Provider clients — each keeps its own native message history.
# step() -> {"text": str, "tool_calls": [{"id","name","input"}], "done": bool}
# submit(results) where results = [{"id","name","output"}]
# --------------------------------------------------------------------------
class Anthropic:
    def __init__(self, key, model, system):
        self.key, self.model, self.system = key, model, system
        self.messages = []
        self.tools = [
            {"name": t["name"], "description": t["description"], "input_schema": t["schema"]}
            for t in TOOLS
        ]
    def user(self, text):
        self.messages.append({"role": "user", "content": text})
    def step(self):
        payload = {
            "model": self.model, "max_tokens": 4096, "system": self.system,
            "tools": self.tools, "messages": self.messages,
        }
        headers = {
            "x-api-key": self.key, "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        resp = http_post_json("https://api.anthropic.com/v1/messages", headers, payload)
        content = resp.get("content", [])
        self.messages.append({"role": "assistant", "content": content})
        text, calls = "", []
        for b in content:
            if b.get("type") == "text":
                text += b.get("text", "")
            elif b.get("type") == "tool_use":
                calls.append({"id": b["id"], "name": b["name"], "input": b.get("input", {})})
        return {"text": text, "tool_calls": calls}
    def submit(self, results):
        self.messages.append({"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": r["id"], "content": r["output"]}
            for r in results
        ]})

class OpenAI:
    def __init__(self, key, model, system):
        self.key, self.model = key, model
        self.messages = [{"role": "system", "content": system}]
        self.tools = [
            {"type": "function", "function": {
                "name": t["name"], "description": t["description"], "parameters": t["schema"]}}
            for t in TOOLS
        ]
    def user(self, text):
        self.messages.append({"role": "user", "content": text})
    def step(self):
        payload = {"model": self.model, "messages": self.messages,
                   "tools": self.tools, "tool_choice": "auto"}
        headers = {"Authorization": "Bearer " + self.key, "content-type": "application/json"}
        resp = http_post_json("https://api.openai.com/v1/chat/completions", headers, payload)
        msg = resp["choices"][0]["message"]
        self.messages.append(msg)
        text = msg.get("content") or ""
        calls = []
        for tc in (msg.get("tool_calls") or []):
            try:
                args = json.loads(tc["function"].get("arguments") or "{}")
            except Exception:
                args = {}
            calls.append({"id": tc["id"], "name": tc["function"]["name"], "input": args})
        return {"text": text, "tool_calls": calls}
    def submit(self, results):
        for r in results:
            self.messages.append({"role": "tool", "tool_call_id": r["id"], "content": r["output"]})

class Google:
    def __init__(self, key, model, system):
        self.key, self.model, self.system = key, model, system
        self.contents = []
        self.decls = [{"function_declarations": [
            {"name": t["name"], "description": t["description"], "parameters": t["schema"]}
            for t in TOOLS
        ]}]
    def user(self, text):
        self.contents.append({"role": "user", "parts": [{"text": text}]})
    def step(self):
        url = ("https://generativelanguage.googleapis.com/v1beta/models/%s:generateContent?key=%s"
               % (self.model, self.key))
        payload = {
            "system_instruction": {"parts": [{"text": self.system}]},
            "contents": self.contents,
            "tools": self.decls,
        }
        resp = http_post_json(url, {"content-type": "application/json"}, payload)
        cand = (resp.get("candidates") or [{}])[0]
        parts = (cand.get("content") or {}).get("parts", []) or []
        self.contents.append({"role": "model", "parts": parts})
        text, calls = "", []
        for i, p in enumerate(parts):
            if "text" in p:
                text += p["text"]
            elif "functionCall" in p:
                fc = p["functionCall"]
                calls.append({"id": "%s_%d" % (fc.get("name", "fn"), i),
                              "name": fc.get("name"), "input": fc.get("args", {})})
        return {"text": text, "tool_calls": calls}
    def submit(self, results):
        self.contents.append({"role": "user", "parts": [
            {"functionResponse": {"name": r["name"], "response": {"result": r["output"]}}}
            for r in results
        ]})

def make_client(provider, key, model, system):
    return {"anthropic": Anthropic, "openai": OpenAI, "google": Google}[provider](key, model, system)

# --------------------------------------------------------------------------
# Hardware snapshot (so the agent starts informed)
# --------------------------------------------------------------------------
def _try(cmd):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15).stdout.strip()
    except Exception:
        return ""

def hardware_facts():
    f = {
        "os": platform.system(),
        "os_release": platform.release(),
        "arch": platform.machine(),
        "python": platform.python_version(),
        "cpu_count": os.cpu_count(),
    }
    # RAM
    try:
        if hasattr(os, "sysconf") and "SC_PHYS_PAGES" in os.sysconf_names:
            f["ram_gb"] = round(os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE") / 1e9, 1)
    except Exception:
        pass
    if f["os"] == "Darwin":
        mem = _try("sysctl -n hw.memsize")
        if mem.isdigit():
            f["ram_gb"] = round(int(mem) / 1e9, 1)
        f["model"] = _try("sysctl -n hw.model")
        f["chip"] = _try("sysctl -n machdep.cpu.brand_string")
    # node
    f["node"] = _try("node --version") or "not found"
    f["npm"] = _try("npm --version") or "not found"
    # gpu hint (best effort, never fails the install)
    f["gpu"] = _try("nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null") or \
               ("Apple Silicon GPU" if f["arch"] in ("arm64",) and f["os"] == "Darwin" else "unknown")
    return f

# --------------------------------------------------------------------------
# System prompt
# --------------------------------------------------------------------------
FALLBACK_BOOTSTRAP = """\
You are installing IndieBiz OS: a Python FastAPI backend (port 8765) plus an
Electron+React frontend, living in this repo.

Do this, verifying each step against the ACTUAL repo (read files; do not assume):
1. Probe the machine (you already have a snapshot; refine if needed).
2. Backend deps: create a venv at the repo root (.venv). Look for a
   requirements.txt / pyproject.toml; if none, infer core deps from backend
   imports (fastapi, uvicorn, etc.) and install them. Prefer the venv's pip.
3. Wire the AI key: find how the backend reads its model config (look in
   data/ for *_ai_config.json examples/existing files and .env.example).
   Write the provider/model/key using the placeholders {{LLM_PROVIDER}},
   {{LLM_MODEL}}, {{LLM_API_KEY}} so the raw key stays out of your context.
   Also create .env from .env.example if present.
4. Pick a hardware profile (model gear): weak machine -> lean profile, and
   skip the heavy fine-tuned embedding model / hippocampus index if it would
   be too heavy; strong machine -> full. Set data/model_gear.json if present.
5. Frontend is OPTIONAL: only run `npm install` in frontend/ if Node >= 18 is
   available and the user wants the desktop UI; otherwise leave backend-only.
6. Verify: start the backend briefly (python backend/api.py via the venv),
   poll http://localhost:8765/ , then stop it. Report the result.
7. Finish with the exact run command (./start.sh on mac/linux).

Be economical. Read before writing. Confirm nothing destructive.
"""

def load_bootstrap():
    p = os.path.join(HERE, "bootstrap.md")
    try:
        with open(p, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return FALLBACK_BOOTSTRAP

def _update_note(update_mode):
    if update_mode not in ("standard", "full"):
        return ""
    common = (
        "\n\n=== THIS IS AN UPDATE (INDIEBIZ_UPDATE=%s) ===\n"
        "The bootstrap already overwrote all tracked GitHub code + the shipped IBL "
        "vocabulary via `git reset --hard`. Every git-IGNORED file (.env, keys, "
        "data/*_ai_config.json, profile, conversation DBs, projects/, world_pulse.db) "
        "was left intact. So on this run you must NOT recreate or overwrite .env or the "
        "existing AI config files — read them, don't clobber them. Focus on: (a) make "
        "sure deps are still satisfied for the profile, (b) rebuild the IBL vocabulary "
        "(`python scripts/build_ibl_nodes.py`), (c) verify the backend still boots, "
        "(d) finish. Do NOT re-run the edition/locale step unless the user asks."
        % update_mode
    )
    if update_mode == "full":
        common += (
            "\nBecause this is a FULL update, the learned/tuning state (hippocampus "
            "index data/ibl_usage.db, forager memory, distilled recipes, model_gear.json, "
            "package_meta.json) was also factory-reset to shipped defaults by "
            "scripts/reset_runtime_state.py. After rebuilding the vocabulary, rebuild the "
            "hippocampus index from the SHIPPED training corpus if the heavy deps are "
            "present (look for backend/rebuild_usage_db.py or a rebuild routine); the "
            "backend also rebuilds a missing hippocampus on boot, so this is best-effort."
        )
    return common


def _repo_present():
    return os.path.isdir(os.path.join(ROOT, "backend")) and \
           os.path.isdir(os.path.join(ROOT, "installer"))


def _clone_note():
    """Standalone binary ran outside a clone: the repo must be fetched first."""
    if _repo_present():
        return ""
    return (
        "\n\n=== THE REPO IS NOT ON THIS MACHINE YET ===\n"
        "Repo root %s is empty (or not a clone). Your FIRST task is to fetch the "
        "repo into it, then continue with the normal install guide:\n"
        "- If git is available: git clone %s \"%s\"  (the directory already exists "
        "and is empty, so clone into it; if clone refuses, git init + remote add + "
        "fetch + checkout works too.)\n"
        "- If git is missing: either install git first, or download "
        "%s/archive/refs/heads/main.zip (curl -L on mac/linux, Invoke-WebRequest "
        "on Windows PowerShell) and extract its contents so that backend/ sits "
        "directly under the repo root above.\n"
        % (ROOT, REPO_URL, ROOT, REPO_URL)
    )


def build_system(provider, model, facts, update_mode=""):
    return (
        "You are the IndieBiz OS installer agent. Your job: install IndieBiz OS "
        "onto THIS machine, adapting to its hardware, then verify it boots.\n\n"
        "Repo root: %s\nRepo URL: %s\n"
        "LLM you are running on: provider=%s model=%s (the user's own key is already "
        "held by the installer; reference it only via the {{LLM_API_KEY}} placeholder).\n\n"
        "Machine snapshot:\n%s\n\n"
        "Work by calling tools. Read the repo to confirm real paths/schemas before "
        "writing. Do not run destructive commands. When done (or blocked), call finish.%s%s\n\n"
        "=== INSTALL GUIDE (compose against the real repo; it may be slightly stale) ===\n%s"
        % (ROOT, REPO_URL, provider, model, json.dumps(facts, indent=2, ensure_ascii=False),
           _clone_note(), _update_note(update_mode), load_bootstrap())
    )

# --------------------------------------------------------------------------
# Main loop
# --------------------------------------------------------------------------
MAX_TURNS = 100

def main():
    say("IndieBiz OS installer agent")
    say("repo: %s" % ROOT)
    # 단일 바이너리 모드: 목적지 폴더가 없으면 만들어 둔다 (run 도구의 cwd이자 쓰기 가드 경계)
    if getattr(sys, "frozen", False):
        try:
            os.makedirs(ROOT, exist_ok=True)
        except Exception as e:
            err("cannot create install dir %s: %s" % (ROOT, e))
            sys.exit(1)
        if not _repo_present():
            say("repo not present yet — the agent will fetch it first")
    key, provider, model = resolve_credentials()
    say("LLM: %s / %s" % (provider, model))

    facts = hardware_facts()
    say("machine: %s %s, %s cores, %s GB RAM, node %s"
        % (facts.get("os"), facts.get("arch"), facts.get("cpu_count"),
           facts.get("ram_gb", "?"), facts.get("node")))

    update_mode = os.environ.get("INDIEBIZ_UPDATE", "").strip().lower()
    if update_mode in ("standard", "full"):
        say("update mode: %s (code + vocabulary already overwritten from GitHub)" % update_mode)

    system = build_system(provider, model, facts, update_mode)
    client = make_client(provider, key, model, system)
    creds = (key, provider, model)

    if update_mode in ("standard", "full"):
        client.user(
            "This is an UPDATE over an existing install (mode=%s). The tracked code and "
            "IBL vocabulary were already overwritten from GitHub; .env and personal data "
            "were preserved. Do NOT recreate .env or clobber existing AI config files. "
            "Read the repo, make sure deps match the profile, rebuild the IBL vocabulary, "
            "verify the backend boots, then finish." % update_mode
        )
    else:
        client.user(
            "Begin installing IndieBiz OS on this machine. Start by reading the repo "
            "root layout and looking for dependency and config files. Then proceed "
            "through the install guide, adapting to the machine snapshot."
        )

    for turn in range(MAX_TURNS):
        try:
            out = client.step()
        except Exception as e:
            err(str(e))
            if "401" in str(e) or "403" in str(e) or "authentication" in str(e).lower():
                err("Your API key was rejected. Re-run with a valid INDIEBIZ_API_KEY.")
            sys.exit(1)

        if out["text"].strip():
            print(_color("0", out["text"].strip()), flush=True)

        calls = out["tool_calls"]
        if not calls:
            # no tool call and not finished -> nudge once, then stop
            client.user("If installation is complete or blocked, call the finish tool. "
                        "Otherwise continue with the next tool call.")
            continue

        results = []
        for c in calls:
            if c["name"] == "finish":
                inp = c["input"]
                ok = inp.get("ok", True)
                print()
                (say if ok else warn)("Installation %s" % ("complete." if ok else "did not complete."))
                print(_color("1;37", "\nSummary:\n") + str(inp.get("summary", "")))
                print(_color("1;37", "\nTo run:\n") + str(inp.get("how_to_run", "")))
                return
            say("· %s" % (c["input"].get("explain") or c["name"]))
            output = exec_tool(c["name"], c["input"], creds)
            results.append({"id": c["id"], "name": c["name"], "output": output})
        client.submit(results)

    warn("Reached the step limit without finishing. You can re-run; progress is on disk.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print()
        err("Interrupted.")
        sys.exit(130)
