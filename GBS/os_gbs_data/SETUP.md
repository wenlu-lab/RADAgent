# Open-Source Pipeline Setup Guide

Run the full GBS bioinformatics pipeline on a self-hosted Qwen3-Coder + vLLM stack — no commercial API needed. This guide covers a fresh server with nothing installed.

**Total setup time:** ~45-60 min (model download dominates).
**Total run time per pipeline:** ~2-5 hours wall-clock for ~500 paired-end samples.

---

## 1. Hardware check (1 min)

```bash
nvidia-smi                      # need ≥75 GB VRAM total (A100 80GB or H100 80GB)
df -h ~                         # need ≥50 GB free disk for model cache
free -h                         # need ≥32 GB RAM
nvidia-smi | grep "Driver Ver"  # need driver supporting CUDA 11.8+ (driver ≥ 470)
```

If your card has less than 75 GB VRAM, the Qwen3-Coder-30B-A3B-Instruct-FP8 model will not fit. Use a smaller model variant or a multi-GPU setup (not covered here).

---

## 2. System packages (5-10 min)

The bioinformatics scripts call these tools — install them via your package manager. On Ubuntu/Debian:

```bash
sudo apt update
sudo apt install -y \
    python3.11 python3.11-venv python3-pip \
    bwa samtools bcftools vcftools \
    ncbi-blast+ \
    cutadapt \
    parallel \
    perl \
    r-base \
    git curl
```

**Stacks (process_radtags, gstacks, populations)** — apt usually ships v1; you need v2.x:

```bash
# Conda is the easiest way:
conda install -c bioconda stacks=2.66
```

**plink2:**

```bash
# Download from https://www.cog-genomics.org/plink/2.0/
# or: conda install -c bioconda plink2
```

**R package `bigsnpr` (used by step 10 LD clumping):**

```bash
sudo R -e 'install.packages("bigsnpr", repos="https://cloud.r-project.org")'
```

**Verify everything is installed:**

```bash
for tool in bwa samtools bcftools vcftools blastn makeblastdb cutadapt parallel \
            process_radtags gstacks populations plink2 Rscript perl python3.11; do
  command -v "$tool" > /dev/null && echo "OK   $tool" || echo "MISS $tool"
done
```

Any `MISS` lines must be resolved before proceeding.

---

## 3. Clone the repo + Python install (15 min)

```bash
git clone <your-repo-url> os_gbs_data
cd os_gbs_data
bash install_os.sh                  # automated venv + Python deps + model download
```

`install_os.sh` does steps 4-6 below automatically. If you prefer to run them manually, skip ahead to "Manual Python install".

---

## 4. Add YOUR data

The pipeline needs three things you provide:

### 4a. Raw paired-end FASTQ files

Put them in `02-raw/` with the `_1.fastq.gz` / `_2.fastq.gz` naming convention:

```
02-raw/
├── SAMPLE001_1.fastq.gz
├── SAMPLE001_2.fastq.gz
├── SAMPLE002_1.fastq.gz
├── SAMPLE002_2.fastq.gz
└── ...
```

### 4b. Reference genome

```bash
cp /path/to/your_reference.fasta 08-genome/genome.fasta
# Build BWA index (one-time, ~5 min for a typical eukaryote genome):
bwa index 08-genome/genome.fasta
# Build BLAST database (one-time, ~2 min):
makeblastdb -dbtype nucl -in 08-genome/genome.fasta -input_type fasta -title genome.fasta
```

### 4c. Sample information CSV

`01-info_files/sample_information.csv` — one row per sample with population assignments. See the existing example in this repo for the exact column format.

### 4d. Adapter sequences (only if non-default)

`01-info_files/adapters.fasta` — the cutadapt-format adapter file. The repo ships a default; replace it only if your library prep used different adapters.

---

## 5. Sanity check

```bash
./gbs status
```

Expected output:
```
Project root: /path/to/os_gbs_data
Skills dir:   /path/to/os_gbs_data/.claude/skills
vLLM URL:     http://127.0.0.1:8000/v1
vLLM alive:   True
Model name:   qwen3-coder
GPU free MB:  4724      ← normal — vLLM has reserved its budget
```

`vLLM alive: False` means the server isn't running. Start it:

```bash
tmux new -d -s vllm 'bash infra/vllm_serve.sh 2>&1 | tee .gbs/vllm.log'
# wait 60-90 s for the model to load:
until curl -sf http://127.0.0.1:8000/v1/models > /dev/null; do sleep 5; done
echo "vLLM ready"
```

---

## 6. Run the pipeline

```bash
# Full pipeline (16 steps), background, output to a log
mkdir -p .gbs
nohup ./gbs orchestrator > .gbs/orchestrator-$(date +%Y%m%d-%H%M%S).log 2>&1 &
echo "PID: $!"
```

**Monitor in another terminal:**

```bash
# Real per-step log (with real timestamps + status):
tail -F gbs-pipeline.log

# Per-step output files appearing:
watch -n 30 'echo "trimmed: $(ls 02-raw/trimmed/ 2>/dev/null | wc -l)"; \
             echo "samples: $(ls -d 03-samples/*/ 2>/dev/null | wc -l)"; \
             echo "BAMs:    $(ls 04-all_samples/*.sorted.bam 2>/dev/null | wc -l)"; \
             echo "final:   $(ls final_snp_panel.vcf 2>/dev/null && echo yes || echo no)"'

# Confirm agent is alive:
pgrep -af gbs-agent
```

**When it finishes:**

```bash
ls -la final_snp_panel.vcf
grep -cv '^#' final_snp_panel.vcf      # SNP count (typical: 100-300)
head final_snp_panel_summary.txt        # per-chromosome summary
cat gbs-pipeline-timing.csv            # per-step duration + token usage
```

---

## 7. Other commands

```bash
./gbs orchestrator 5             # resume from step 5
./gbs orchestrator 8 --only      # run only step 8
./gbs orchestrator 8 --only --clean   # clean step 8 outputs first, then run
./gbs run gbs-5-bwa              # run a single skill standalone (no orchestrator)
./gbs debugger 9 "vcftools error" # manually invoke autonomous debugger on a step
bash clean_pipeline.sh all        # wipe ALL pipeline outputs, keep raw data
bash clean_pipeline.sh 5          # clean only step 5 outputs
```

**Browse what each step did:**

```bash
.venv/bin/python 00-scripts/browse_transcripts.py list
.venv/bin/python 00-scripts/browse_transcripts.py show 5 --commands
```

---

## Manual Python install (if you skipped install_os.sh)

```bash
cd os_gbs_data
python3.11 -m venv .venv
.venv/bin/pip install --upgrade pip

# torch — cu118 wheels are forward-compatible with any driver ≥ 470:
.venv/bin/pip install torch==2.7.1 torchvision==0.22.1 torchaudio==2.7.1 \
    --index-url https://download.pytorch.org/whl/cu118

# vLLM 0.10.1 is the FIRST version with the qwen3_coder tool parser.
# transformers MUST be pinned to 4.55.x — vLLM 0.10.1 declares
# transformers>=4.55 with no upper bound, but 5.x removes APIs vLLM uses.
.venv/bin/pip install vllm==0.10.1
.venv/bin/pip install "transformers==4.55.4"

# The agent itself:
.venv/bin/pip install -e ./agent

# Pre-download the model (~30 GB):
.venv/bin/huggingface-cli download Qwen/Qwen3-Coder-30B-A3B-Instruct-FP8
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `vLLM alive: False` after `./gbs serve` | Model still loading | Wait 60-90 s, retry |
| `RuntimeError: NVIDIA driver too old` | torch built for newer CUDA than driver supports | Use the cu118 wheel commands in section 6 above; do NOT `pip install vllm` (it pulls cu130 torch) |
| `ValueError: type fp8e4nv not supported` | A100/Ampere doesn't have hardware FP8 | The shipped `infra/vllm_serve.sh` already drops `--kv-cache-dtype fp8`. Don't re-add it. |
| `AttributeError: Qwen2Tokenizer has no attribute all_special_tokens_extended` | transformers 5.x got installed | `.venv/bin/pip install "transformers==4.55.4"` |
| `ConnectError: Connection refused` mid-pipeline | vLLM crashed | Check `.gbs/vllm.log` tail; restart the tmux session |
| Step 2 (radtags) hangs in agent polling loop | agent's `pgrep -f` self-matched (fixed in this repo) | Make sure you're on the latest commit — the `b581e2a` and `481394a` commits include the fix |
| Step report says FAILURE but output files exist | The model judged its own work poorly | Check the actual files — you can run `./gbs orchestrator <next-step>` to resume |
| Pipeline reports fake timestamps like "2023-05-15 10:30:00" | Model copied SKILL.md template literally | The REAL timestamps are in `gbs-pipeline.log` |

---

## What this project is

This pipeline was originally written for Claude Code (Anthropic API). The `agent/` directory adds a thin Python runtime that reads the same `.claude/skills/SKILL.md` files but drives them with a self-hosted Qwen3-Coder-30B-A3B-FP8 model on vLLM. **The bioinformatics scripts in `00-scripts/` are unchanged**; only the LLM-orchestration layer is replaced. See `agent/README.md` for the architecture diagram and `docs/superpowers/specs/2026-05-01-os-gbs-port-design.md` for the design rationale.
