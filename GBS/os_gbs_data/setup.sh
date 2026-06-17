#!/usr/bin/env bash
# setup.sh — one-shot setup for the open-source GBS pipeline (in-process Qwen3-Coder).
#
# Run this from the project root after `git clone`. It will:
#   1. Verify hardware/driver/Python prerequisites
#   2. Verify bioinformatics CLI tools are on PATH (warns if missing)
#   3. Create .venv/ with torch + the agent (transformers/accelerate/huggingface_hub)
#   4. Pre-download the Qwen3-Coder-30B-A3B-Instruct model (bf16, ~60 GB)
#   5. Print next steps
#
# Idempotent: re-running skips work that's already done.
# Does NOT install bioinformatics tools (they need sudo and are OS-specific —
# see the README's Installation section 2 for those).

set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$REPO"

# ---------- helpers ----------
red()    { printf '\033[31m%s\033[0m\n' "$*" >&2; }
green()  { printf '\033[32m%s\033[0m\n' "$*"; }
yellow() { printf '\033[33m%s\033[0m\n' "$*"; }
section() { printf '\n\033[1;34m== %s ==\033[0m\n' "$*"; }

die() { red "ERROR: $*"; exit 1; }

# ---------- 1. hardware + Python ----------
section "1. Hardware + Python prerequisites"

command -v nvidia-smi >/dev/null 2>&1 || die "nvidia-smi not found — no NVIDIA driver installed?"

GPU_FREE_MB=$(nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1 | tr -d ' ')
if [ "${GPU_FREE_MB:-0}" -lt 70000 ]; then
    red "GPU has only ${GPU_FREE_MB} MB total — Qwen3-Coder-30B-A3B bf16 needs ≥75 GB."
    die "Use a different model variant or hardware."
fi
green "GPU OK: ${GPU_FREE_MB} MB total"

DRIVER=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader | head -1 | tr -d ' ')
DRIVER_MAJOR=${DRIVER%%.*}
if [ "${DRIVER_MAJOR:-0}" -lt 470 ]; then
    die "Driver $DRIVER too old (need ≥470 for cu118 wheels). Update NVIDIA driver."
fi
green "Driver OK: $DRIVER"

DISK_FREE_GB=$(df -BG "$HOME" | awk 'NR==2 {print $4}' | tr -d 'G')
if [ "${DISK_FREE_GB:-0}" -lt 65 ]; then
    yellow "WARNING: only ${DISK_FREE_GB} GB free in \$HOME — bf16 model needs ~60 GB."
fi

PYTHON=python3.11
command -v "$PYTHON" >/dev/null 2>&1 || die "$PYTHON not found. Install via apt/conda."
green "$PYTHON OK: $($PYTHON --version)"

# ---------- 2. bioinformatics CLI tools (check only) ----------
section "2. Bioinformatics tool check"

REQUIRED_TOOLS=(bwa samtools bcftools vcftools blastn makeblastdb cutadapt parallel
                process_radtags gstacks populations Rscript perl)
OPTIONAL_TOOLS=(plink2 plink)
MISSING=()
for tool in "${REQUIRED_TOOLS[@]}"; do
    if command -v "$tool" >/dev/null 2>&1; then
        green "OK   $tool"
    else
        red   "MISS $tool"
        MISSING+=("$tool")
    fi
done

# plink2 OR plink is acceptable
if command -v plink2 >/dev/null 2>&1; then
    green "OK   plink2"
elif command -v plink >/dev/null 2>&1; then
    yellow "OK   plink (plink2 preferred but plink will work)"
else
    red   "MISS plink2/plink"
    MISSING+=("plink2")
fi

if [ ${#MISSING[@]} -gt 0 ]; then
    yellow ""
    yellow "Missing tools: ${MISSING[*]}"
    yellow "Install them per the README's Installation section 2 before running the pipeline."
    yellow "Continuing anyway — the agent install does NOT need these tools."
fi

# ---------- 3. Python venv + pinned deps ----------
section "3. Python venv + pinned deps"

if [ ! -d .venv ]; then
    "$PYTHON" -m venv .venv
    green "Created .venv/"
else
    yellow "Reusing existing .venv/"
fi

.venv/bin/pip install --upgrade pip --quiet

# torch (cu118 — works with any driver ≥ 470, no need for newer CUDA)
if ! .venv/bin/python -c "import torch; assert torch.__version__.startswith('2.7.1') and 'cu118' in torch.__version__" 2>/dev/null; then
    yellow "Installing torch 2.7.1+cu118 (~900 MB download)..."
    .venv/bin/pip install --quiet \
        torch==2.7.1 torchvision==0.22.1 torchaudio==2.7.1 \
        --index-url https://download.pytorch.org/whl/cu118
    green "torch installed"
else
    green "torch already installed"
fi

# Confirm GPU is reachable from the venv
.venv/bin/python -c "
import torch
assert torch.cuda.is_available(), 'torch.cuda.is_available() == False — driver/torch mismatch'
print(f'  torch {torch.__version__}, CUDA available, device={torch.cuda.get_device_name(0)}')
"

# Pin transformers to the validated 4.55.4 BEFORE the agent install, so the agent's
# `transformers>=4.55` is already satisfied and pip won't pull an untested 5.x.
.venv/bin/pip install --quiet "transformers==4.55.4"
green "transformers pinned to 4.55.4"

# Agent itself — pulls accelerate, huggingface_hub, textual, rich, etc. per pyproject
.venv/bin/pip install --quiet -e ./agent
green "agent installed (editable)"

# Test deps (so the parity tests can run later)
.venv/bin/pip install --quiet "pytest>=8.0" "pytest-mock>=3.12" "pytest-timeout>=2.3"

# Quick import check
.venv/bin/python -c "import torch, transformers, accelerate, gbs.config; print('  imports OK')"
green "All Python packages OK"

# .gbs/ holds the agent's transcripts + runtime.log (see agent/gbs/config.py);
# the next-steps below also redirect orchestrator logs into it.
if [ ! -d .gbs ]; then
    mkdir -p .gbs
    green "Created .gbs/ (runtime transcripts + logs)"
else
    yellow "Reusing existing .gbs/"
fi

# ---------- 4. model download ----------
section "4. Pre-download Qwen3-Coder-30B-A3B-Instruct (bf16, ~60 GB)"

# bf16 checkpoint: loads on Ampere (A100). The -FP8 variant needs compute >= 8.9.
MODEL_DIR="$HOME/.cache/huggingface/hub/models--Qwen--Qwen3-Coder-30B-A3B-Instruct"
if [ -d "$MODEL_DIR" ] && [ "$(du -sh "$MODEL_DIR" 2>/dev/null | cut -f1)" != "0" ]; then
    SIZE=$(du -sh "$MODEL_DIR" | cut -f1)
    yellow "Model cache exists at $MODEL_DIR ($SIZE)"
    yellow "Skipping download. Delete the directory if you want to re-download."
else
    yellow "Downloading model — this takes ~30-60 min depending on bandwidth..."
    .venv/bin/huggingface-cli download Qwen/Qwen3-Coder-30B-A3B-Instruct
    green "Model downloaded"
fi

# ---------- 5. summary + next steps ----------
section "5. Setup complete"

cat <<EOF

Setup is done. Next steps:

1. Add YOUR data (see the README's Installation section 4):
   - Paired FASTQs:    cp /path/*.fastq.gz 02-raw/
   - Reference genome: cp /path/genome.fasta 08-genome/genome.fasta
                       bwa index 08-genome/genome.fasta
                       makeblastdb -dbtype nucl -in 08-genome/genome.fasta -input_type fasta -title genome.fasta
   - Sample CSV:       edit 01-info_files/sample_information.csv

2. Sanity check (no server to start — the model loads in-process on first run):
   ./gbs status

3. Run the pipeline (the ~60 GB model loads into VRAM on the first call, ~minutes):
   nohup ./gbs orchestrator > .gbs/orchestrator-\$(date +%Y%m%d-%H%M%S).log 2>&1 &
   tail -F .gbs/orchestrator-*.log

4. When done:
   ls -la final_snp_panel.vcf
   grep -cv '^#' final_snp_panel.vcf

For troubleshooting see the README's "Troubleshooting" section.

EOF

green "All done."
