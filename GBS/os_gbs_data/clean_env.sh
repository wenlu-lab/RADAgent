#!/usr/bin/env bash
# clean_env.sh — wipe the Python virtualenv + all Python cache/build artifacts
# from this repo, for a clean-slate reinstall.
#
# Removes:   .venv/, __pycache__/, *.pyc, *.pyo, *.egg-info/,
#            .pytest_cache/, .mypy_cache/, .ruff_cache/
# Leaves:    your data (02-raw/, 08-genome/, ...), pipeline outputs,
#            .gbs/ run transcripts, and the Hugging Face model cache (~/.cache).
#            (Use clean_pipeline.sh to clean pipeline outputs.)
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "Cleaning Python env + caches under: $REPO"

# 1. virtualenv
if [ -d "$REPO/.venv" ]; then
    rm -rf "$REPO/.venv"
    echo "  removed .venv/"
fi

# 2. cache/build directories (skip .git; -prune so find won't descend into them)
find "$REPO" -path "$REPO/.git" -prune -o \
    -type d \( -name '__pycache__' -o -name '.pytest_cache' -o -name '.mypy_cache' \
               -o -name '.ruff_cache' -o -name '*.egg-info' \) \
    -prune -print -exec rm -rf {} + 2>/dev/null || true

# 3. loose bytecode
find "$REPO" -path "$REPO/.git" -prune -o \
    -type f \( -name '*.pyc' -o -name '*.pyo' \) -print -delete 2>/dev/null || true

echo "Done. Run 'bash setup.sh' to rebuild the venv."
