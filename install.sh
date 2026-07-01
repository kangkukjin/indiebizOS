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
# This bootstrap does the *dumb* part: make sure git + python3 exist, get the
# code, and hand off to the intelligent seed (installer/seed.py), which is an
# LLM agent that adapts the install to *this* machine.
set -euo pipefail

REPO_URL="${INDIEBIZ_REPO:-https://github.com/kangkukjin/indiebizOS.git}"
INSTALL_DIR="${INDIEBIZ_DIR:-$HOME/indiebizOS}"
BRANCH="${INDIEBIZ_BRANCH:-main}"

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

main() {
  c_say "IndieBiz OS installer — bootstrapping on $OS"
  install_prereqs

  local PY; PY="$(find_python)"
  c_say "using python: $PY ($("$PY" --version 2>&1))"

  if [ -d "$INSTALL_DIR/.git" ]; then
    c_say "found existing clone at $INSTALL_DIR — updating"
    git -C "$INSTALL_DIR" fetch --depth 1 origin "$BRANCH" >/dev/null 2>&1 || true
    git -C "$INSTALL_DIR" pull --ff-only >/dev/null 2>&1 || c_say "(skip pull — local changes present)"
  else
    c_say "cloning $REPO_URL -> $INSTALL_DIR"
    git clone --branch "$BRANCH" --depth 1 "$REPO_URL" "$INSTALL_DIR"
  fi

  cd "$INSTALL_DIR"
  c_say "handing off to the installer agent…"
  # exec so signals (Ctrl-C) go straight to the seed
  exec "$PY" "$INSTALL_DIR/installer/seed.py"
}

main "$@"
