#!/usr/bin/env bash
# IndieBiz OS — minimal self-installer (macOS / Linux)
#
# One-liner:
#   curl -fsSL https://raw.githubusercontent.com/kangkukjin/indiebizOS/main/install.sh | bash
#
# With your key inline (recommended when piping — no prompt needed):
#   curl -fsSL https://raw.githubusercontent.com/kangkukjin/indiebizOS/main/install.sh \
#     | INDIEBIZ_API_KEY=sk-ant-... bash
#
# Re-installing over an existing clone (overwrite with GitHub code):
#   INDIEBIZ_UPDATE=standard  overwrite tracked code + shipped vocabulary; KEEP
#                             your .env, personal data, AND accumulated learning.
#   INDIEBIZ_UPDATE=full      also factory-reset learned data & tuning to shipped
#                             defaults (keeps only .env + personal data + history).
#   INDIEBIZ_UPDATE=off       (default) just fast-forward pull, skip if local edits.
#   If unset and a terminal is attached, you are asked which one.
#   Either way, git-ignored files (.env / keys / profile / DBs / projects) are
#   never touched by the code overwrite — .gitignore IS the preservation boundary.
#
# This bootstrap does the *dumb* part: make sure git + python3 exist, get the
# code, and hand off to the intelligent seed (installer/seed.py), which is an
# LLM agent that adapts the install to *this* machine.
set -euo pipefail

REPO_URL="${INDIEBIZ_REPO:-https://github.com/kangkukjin/indiebizOS.git}"
INSTALL_DIR="${INDIEBIZ_DIR:-$HOME/indiebizOS}"
BRANCH="${INDIEBIZ_BRANCH:-main}"
UPDATE_MODE="${INDIEBIZ_UPDATE:-}"   # standard | full | off  (empty = ask if interactive)
YES="${INDIEBIZ_YES:-}"

c_say() { printf "\033[1;36m[indiebiz]\033[0m %s\n" "$*"; }
c_err() { printf "\033[1;31m[indiebiz:error]\033[0m %s\n" "$*" >&2; }

OS="$(uname -s)"

find_python() {
  for c in python3 python; do
    if command -v "$c" >/dev/null 2>&1; then
      # must be python 3.x
      if "$c" -c 'import sys; sys.exit(0 if sys.version_info[0]==3 else 1)' 2>/dev/null; then
        echo "$c"; return 0
      fi
    fi
  done
  return 1
}

install_prereqs() {
  local need_git=0 need_py=0
  command -v git >/dev/null 2>&1 || need_git=1
  find_python >/dev/null 2>&1 || need_py=1
  [ "$need_git" = 0 ] && [ "$need_py" = 0 ] && return 0

  c_say "installing prerequisites (git / python3)…"
  if [ "$OS" = "Darwin" ]; then
    if command -v brew >/dev/null 2>&1; then
      [ "$need_git" = 1 ] && brew install git
      [ "$need_py" = 1 ] && brew install python
    else
      c_err "git/python3 missing and Homebrew not found."
      c_err "Run:  xcode-select --install   (gives git+python3)"
      c_err "  or install Homebrew: https://brew.sh  then re-run this."
      exit 1
    fi
  elif command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update -y
    sudo apt-get install -y git python3 python3-venv python3-pip
  elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y git python3 python3-pip
  elif command -v pacman >/dev/null 2>&1; then
    sudo pacman -Sy --noconfirm git python python-pip
  elif command -v zypper >/dev/null 2>&1; then
    sudo zypper install -y git python3 python3-pip
  else
    c_err "Could not detect a package manager. Please install git + python3 manually, then re-run."
    exit 1
  fi
}

# Ask (via the real terminal — stdin is the piped script under curl|bash) which
# overwrite mode to use for an existing install. Echoes standard|full|off.
resolve_update_mode() {
  # explicit env wins
  case "$UPDATE_MODE" in
    standard|full|off) echo "$UPDATE_MODE"; return 0 ;;
  esac
  # unattended (INDIEBIZ_YES) or no terminal → safe default
  if [ -n "$YES" ] || [ ! -r /dev/tty ]; then
    echo off; return 0
  fi
  {
    printf "\033[1;36m[indiebiz]\033[0m existing install found — overwrite with GitHub code?\n"
    printf "  [1] standard  overwrite code + shipped vocabulary; KEEP your learning & settings\n"
    printf "  [2] full      factory reset: also reset learned data & tuning (keeps .env + personal data)\n"
    printf "  [3] off       just fast-forward pull (default, safest)\n"
    printf "  choose [1/2/3] (default 3): "
  } >/dev/tty
  local ans=""; read -r ans </dev/tty || ans=""
  case "$ans" in
    1) echo standard ;;
    2) echo full ;;
    *) echo off ;;
  esac
}

# Overwrite all *tracked* files with the fetched GitHub state. git reset --hard
# never touches untracked/ignored files, so .env / keys / personal data survive.
overwrite_tracked() {
  c_say "overwriting tracked code + vocabulary from origin/$BRANCH (git-ignored files kept)…"
  git -C "$INSTALL_DIR" fetch --depth 1 origin "$BRANCH"
  git -C "$INSTALL_DIR" reset --hard FETCH_HEAD
}

main() {
  c_say "IndieBiz OS installer — bootstrapping on $OS"
  install_prereqs

  local PY; PY="$(find_python)"
  c_say "using python: $PY ($("$PY" --version 2>&1))"

  if [ -d "$INSTALL_DIR/.git" ]; then
    local mode; mode="$(resolve_update_mode)"
    UPDATE_MODE="$mode"
    if [ "$mode" = "standard" ] || [ "$mode" = "full" ]; then
      overwrite_tracked
      if [ "$mode" = "full" ]; then
        c_say "full update — factory-resetting learned/tuning state (keys + personal data kept)…"
        "$PY" "$INSTALL_DIR/scripts/reset_runtime_state.py" --mode full --yes \
          || c_say "(runtime reset skipped — script missing or errored)"
      fi
    else
      c_say "found existing clone at $INSTALL_DIR — fast-forward pull only"
      git -C "$INSTALL_DIR" fetch --depth 1 origin "$BRANCH" >/dev/null 2>&1 || true
      git -C "$INSTALL_DIR" pull --ff-only >/dev/null 2>&1 || c_say "(skip pull — local changes present)"
    fi
  else
    c_say "cloning $REPO_URL -> $INSTALL_DIR"
    git clone --branch "$BRANCH" --depth 1 "$REPO_URL" "$INSTALL_DIR"
  fi

  cd "$INSTALL_DIR"
  c_say "handing off to the installer agent…"
  # let the seed know this was an update so it rebuilds vocab / won't clobber .env
  export INDIEBIZ_UPDATE="$UPDATE_MODE"
  # exec so signals (Ctrl-C) go straight to the seed
  exec "$PY" "$INSTALL_DIR/installer/seed.py"
}

main "$@"
