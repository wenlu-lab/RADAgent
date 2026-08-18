# 🤖 Agentic Scientific Pipelines

RADAgent is an agentic framework for automating end-to-end restriction site-associated DNA sequencing (RAD-seq) analysis with open-weight large language models.

## 📦 Installation

Fresh-server setup is ~45–60 min, dominated by the model download.

### 1. Hardware check

```bash
nvidia-smi                      # need ≥75 GB VRAM total (A100 80GB / H100 80GB)
df -h ~                         # need ≥65 GB free disk for the model cache (bf16 weights ~60 GB)
free -h                         # need ≥32 GB RAM
nvidia-smi | grep "Driver Ver"  # need a driver supporting CUDA 11.8+ (driver ≥ 470)
```

If the card has < 75 GB VRAM, the bf16 30B model won't fit — use a smaller variant or
multi-GPU (not covered here).

### 2. System + bioinformatics tools

`setup.sh` does **not** install these (they need `sudo` and are OS-specific). On Ubuntu/Debian:

```bash
sudo apt update
sudo apt install -y \
    python3.11 python3.11-venv python3-pip \
    bwa samtools bcftools vcftools \
    ncbi-blast+ cutadapt parallel perl r-base git curl
```

**Stacks 2.x** (`process_radtags`, `gstacks`, `populations`) — apt ships v1, you need v2:

```bash
conda install -c bioconda stacks=2.66
```

**plink2:** `conda install -c bioconda plink2` (or download from
<https://www.cog-genomics.org/plink/2.0/>).

**R package `bigsnpr`** (step 10):

```bash
sudo R -e 'install.packages("bigsnpr", repos="https://cloud.r-project.org")'
```

Verify everything is on `$PATH`:

```bash
for tool in bwa samtools bcftools vcftools blastn makeblastdb cutadapt parallel \
            process_radtags gstacks populations plink2 Rscript perl python3.11; do
  command -v "$tool" >/dev/null && echo "OK   $tool" || echo "MISS $tool"
done
```

Resolve any `MISS` before continuing.

### 3. Python venv + model (automated)

```bash
git clone <your-repo-url> os_gbs_data
cd os_gbs_data
bash setup.sh
```

`setup.sh` is idempotent and will: verify hardware/driver/Python, warn about any missing
bioinformatics tools, create `.venv/` with the pinned `torch` + `transformers==4.55.4`,
install the agent (`pip install -e ./agent`, which pulls `accelerate`/`huggingface_hub`/
`textual`/`rich`), then pre-download the ~60 GB bf16 model.

<details>
<summary>Manual Python install (if you'd rather not use setup.sh)</summary>

```bash
python3.11 -m venv .venv
.venv/bin/pip install --upgrade pip
# torch — cu118 wheels are forward-compatible with any driver ≥ 470:
.venv/bin/pip install torch==2.7.1 torchvision==0.22.1 torchaudio==2.7.1 \
    --index-url https://download.pytorch.org/whl/cu118
# pin transformers to the validated release first, so pip won't pull an untested 5.x:
.venv/bin/pip install "transformers==4.55.4"
.venv/bin/pip install -e ./agent   # pulls accelerate, huggingface_hub, textual, rich
.venv/bin/huggingface-cli download Qwen/Qwen3-Coder-30B-A3B-Instruct
```
</details>

The `./gbs` wrapper calls the venv binaries directly — you never need to
`source .venv/bin/activate`.

### 4. Add your data

```
02-raw/                        # ** your raw paired-end FASTQs **
├── SAMPLE001_1.fastq.gz       #    forward reads (_1)
├── SAMPLE001_2.fastq.gz       #    reverse reads (_2)
└── ...
08-genome/genome.fasta         # ** your reference genome **
01-info_files/
├── sample_information.csv      # ** you provide — sample/population map (see below) **
└── adapters.fasta             #    cutadapt adapters (default shipped; replace if needed)
```

BWA and BLAST indexes for the genome are built automatically by the pipeline if missing
(or build them once yourself: `bwa index 08-genome/genome.fasta` and
`makeblastdb -dbtype nucl -in 08-genome/genome.fasta -input_type fasta -title genome.fasta`).

**`sample_information.csv` format** — one row per sample:

```csv
#Lane,Barcode,Population,Sample,PopulationID,PlatePosition,,
SRR30282941,TGACACC,P01,ROW-04-22,1,A01,,Notes
SRR30282940,CTCACT,P01,ROW-05-22,1,A02,,DO NOT modify the column titles in the header line
```

- Don't modify the header titles or the order of the first six columns.
- Use plate-position format `A01`, not `A1`.
- Lane names must match your FASTQ prefixes (without `_1.fastq.gz`).

### 5. Sanity-check

There is no server to start — the model loads in-process on the first agent call.

```bash
./gbs status
```

Expected `./gbs status`:

```
Project root: /path/to/os_gbs_data
Skills dir:   /path/to/os_gbs_data/.claude/skills
Model id:     Qwen/Qwen3-Coder-30B-A3B-Instruct
Torch dtype:  auto
Device map:   auto
Max ctx tok:  32768
GPU free MB:  80000      ← the card should be ~empty before the first run
```

The GPU should be nearly empty here; the ~60 GB load happens when you launch the
orchestrator (or `./gbs run`). Make sure no other process is holding VRAM.

---

## 🚀 Quick Start

```bash
./gbs status           # sanity check — prints model id + GPU free

# run the full pipeline in the background, logging to .gbs/ (gives the viewer a session log)
# the model loads in-process on the first call (a few minutes), then stays resident
nohup ./gbs orchestrator > .gbs/orchestrator-$(date +%Y%m%d-%H%M%S).log 2>&1 &

./gbs view             # watch it live in the TUI
```

---
