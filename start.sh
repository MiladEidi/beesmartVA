#!/usr/bin/env bash
# ============================================================
# BeeSmartVA Bot — start script
# Usage:  bash start.sh
# Place this file next to your .env in the project root.
# ============================================================
set -euo pipefail

# ── Resolve project root (folder that contains this script) ──
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ── Load .env ────────────────────────────────────────────────
if [ -f ".env" ]; then
    set -a
    source .env
    set +a
    echo "[start] .env loaded"
else
    echo "[start] WARNING: .env not found in $SCRIPT_DIR — bot may fail without required vars"
fi

# ── Virtual environment ──────────────────────────────────────
VENV_DIR="$SCRIPT_DIR/.venv"

if [ ! -d "$VENV_DIR" ]; then
    echo "[start] Creating virtual environment at .venv ..."
    python3 -m venv "$VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
echo "[start] Python: $(which python) ($(python --version))"

# ── Install / upgrade dependencies ──────────────────────────
echo "[start] Installing dependencies from requirements.txt ..."
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt
echo "[start] Dependencies ready"

# ── Launch bot ───────────────────────────────────────────────
echo "[start] Starting BeeSmartVA bot ..."
exec python -m app.main
