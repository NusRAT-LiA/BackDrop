#!/usr/bin/env bash
# One-time setup. Builds .venv, installs AppWorld and this benchmark, fetches AppWorld's data, and unpacks
# the tasks. Safe to re-run: every step is idempotent.
#
#   ./setup.sh            uses uv, installing it if it is missing
#   NO_UV=1 ./setup.sh    uses python -m venv and pip instead
set -euo pipefail
cd "$(dirname "$0")"

step() { printf '\n\033[1m==> %s\033[0m\n' "$*"; }

# ---- 1. the AppWorld checkout ------------------------------------------------------------------
APPWORLD_REPO=https://github.com/StonyBrookNLP/appworld.git
APPWORLD_COMMIT=a072b7a86e7c1d5b1d7175659d750ebb9b79f10a   # the commit the tasks were built against

if [ ! -f appworld/pyproject.toml ] && [ -d .git ]; then
  step "fetching the AppWorld submodule"
  git submodule update --init --recursive || true
fi
# Still not there? Then this is a downloaded archive (no .git at all) or a repository where the submodule was
# never registered, and the line above was a no-op either way. Clone the pinned commit directly.
if [ ! -f appworld/pyproject.toml ]; then
  if [ -d appworld ] && [ -n "$(ls -A appworld 2>/dev/null)" ]; then
    echo "appworld/ exists but has no pyproject.toml. Remove it and re-run."; exit 1
  fi
  step "cloning AppWorld at the pinned commit"
  rmdir appworld 2>/dev/null || true
  git clone --quiet "$APPWORLD_REPO" appworld
  git -C appworld checkout --quiet "$APPWORLD_COMMIT"
fi

# AppWorld keeps its encrypted code in Git LFS. A clone made before `git lfs install` has ever run gets 130-byte
# pointer files instead, and `appworld install` then fails on a file that looks nothing like a bundle. Detect
# that by size and fetch the real objects.
BUNDLE=appworld/src/appworld/.source/apps.bundle
if [ -f "$BUNDLE" ] && [ "$(wc -c <"$BUNDLE")" -lt 1000 ]; then
  command -v git-lfs >/dev/null 2>&1 || {
    echo "AppWorld's code is stored in Git LFS and $BUNDLE is only a pointer."
    echo "Install git-lfs (apt install git-lfs / brew install git-lfs), then re-run this script."; exit 1; }
  step "fetching AppWorld's Git LFS objects"
  git -C appworld lfs install --local >/dev/null
  git -C appworld lfs pull
fi

# ---- 2. the environment ------------------------------------------------------------------------
if [ -z "${NO_UV:-}" ]; then
  if ! command -v uv >/dev/null 2>&1; then
    step "installing uv"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # the installer puts uv in one of these; pick up whichever exists without needing a new shell
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
  fi
  command -v uv >/dev/null 2>&1 || { echo "uv is still not on PATH; open a new shell, or run NO_UV=1 ./setup.sh"; exit 1; }
  step "building .venv with uv"
  uv sync --extra dev
else
  PY=${PYTHON:-}
  if [ -z "$PY" ]; then
    for c in python3.13 python3.12 python3.11 python3; do
      if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then
        PY=$c; break
      fi
    done
  fi
  [ -n "$PY" ] || { echo "need Python 3.11 or newer on PATH (or set PYTHON=/path/to/python)"; exit 1; }
  step "building .venv with venv and pip ($($PY -V))"
  [ -d .venv ] || "$PY" -m venv .venv
  .venv/bin/python -m pip install --quiet --upgrade pip
  # the two paths first, then this package without deps, so pip never looks for `appworld` on PyPI
  .venv/bin/python -m pip install --quiet -e ./appworld -e ./appworld/experiments
  .venv/bin/python -m pip install --quiet --no-deps -e '.[dev]'
  .venv/bin/python -m pip install --quiet pytest
fi

# Both paths end up with a .venv here, so address it directly and stop caring which built it.
PYBIN=.venv/bin/python
APPWORLD=.venv/bin/appworld

# ---- 3. AppWorld's own code and data -----------------------------------------------------------
if [ ! -d appworld/src/appworld/apps/gmail ]; then
  step "unpacking AppWorld's app code"
  (cd appworld && "../$APPWORLD" install --repo)
fi
if [ ! -d appworld/data/base_dbs ]; then
  step "downloading AppWorld's data (about 200 MB)"
  "$APPWORLD" download data --root appworld
fi

# ---- 4. this benchmark's tasks ------------------------------------------------------------------
step "unpacking the tasks and their generators"
"$PYBIN" -m benchmark_ext.bundle unpack

# ---- 5. check it ---------------------------------------------------------------------------------
step "checking the install"
"$PYBIN" - <<'PY'
from benchmark_ext import store
for kind in ("compounds", "twins", "ablations"):
    print(f"  {len(store.select_tasks(kind)):5d} {kind}")
PY
printf '\n\033[1mready.\033[0m  next:\n'
printf '  1. cp .env.example .env   and put ONE provider key in it\n'
printf '  2. uv run python -m benchmark_ext.run --sample 2 --model gemini/gemini-flash-latest\n'
printf '     (without uv: source .venv/bin/activate, then the same command without "uv run")\n'
