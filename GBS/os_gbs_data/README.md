# GBS Pipeline — Self-Hosted Agentic Genotyping-by-Sequencing

An end-to-end GBS (Genotyping-by-Sequencing) bioinformatics pipeline that takes raw
paired-end Illumina FASTQ files and produces a final SNP panel VCF with markers evenly
distributed across all chromosomes — ready for genotyping-array design.

The 16 steps run **autonomously from a single command**, driven by a small Python agent
runtime (`agent/`) that loads a **self-hosted Qwen3-Coder model in-process via Hugging
Face `transformers`** — no inference server, no commercial LLM API required. Each step is
executed by an LLM "subagent" that follows a detailed `SKILL.md` spec, with **4 layers of
built-in error handling**.

```
Raw FASTQs ─▶ Trim ─▶ Enzyme Filter ─▶ Align ─▶ Genotype ─▶ Filter ─▶ SNP Panel
 (paired-end)  Step 1     Step 2        Step 5    Step 6-7   Steps 8-15  final_snp_panel.vcf
```

- **Input:** paired-end FASTQ files + reference genome + sample-information CSV
- **Output:** `final_snp_panel.vcf` — quality-filtered, LD-pruned, BLAST-validated SNPs

> This README supersedes the old `SETUP.md` and `00-scripts/browse_transcripts.py`
> documentation. Everything you need is here.

---

## Current stack

This repo runs the pipeline on a **self-hosted** LLM. The concrete setup it's built and
tested against:

| Component | Value |
|---|---|
| Model | `Qwen/Qwen3-Coder-30B-A3B-Instruct` (bf16, ~60 GB in VRAM) — see note on the FP8 variant below |
| Inference | **in-process** Hugging Face `transformers` (no server); tool calls parsed by `gbs/qwen3_coder_parser.py` |
| Python | 3.11, in a project-local `.venv/` |
| Pinned deps | `torch==2.7.1` (cu118 wheels), `transformers==4.55.4`, `accelerate`, `huggingface_hub`, `textual`/`rich` (viewer) |
| Runtime | the `gbs-agent` package in `agent/`, invoked via the `./gbs` CLI |
| GPU | 1× NVIDIA A100 80GB / H100 80GB (≥75 GB VRAM) |

> **Why bf16, not FP8:** transformers' FP8 quantizer requires GPU compute capability
> ≥ 8.9 (Ada/Hopper). The A100 is 8.0 (Ampere), so the `-FP8` checkpoint won't load
> in-process there — use the bf16 checkpoint (default). On a 4090/H100 you can set
> `GBS_MODEL_ID=Qwen/Qwen3-Coder-30B-A3B-Instruct-FP8`.
>
> **Effective context window:** in-process `transformers` has no PagedAttention, so the
> usable window is much smaller than vLLM's 262K (default `GBS_MAX_CONTEXT_TOKENS=32768`,
> tune to your GPU). Long agentic loops also re-encode the prompt each turn, so a run is
> slower than the old vLLM setup. This is the accepted trade-off for loading the model
> directly with no server.

The bioinformatics scripts in `00-scripts/` are plain Bash/Python/R/Perl and are **not**
LLM-specific. The skills in `.claude/skills/` were originally authored for Claude Code;
the `agent/` runtime reads those same `SKILL.md` files and drives them with the local
model. See `agent/README.md` for a deeper architecture write-up.

### How the agent runtime works

```
./gbs orchestrator
   │
   ▼
[orchestrator: one Python process, model loaded in-process]
   │   • runs Bash pre-flight + on-disk cross-checks
   │   • writes timing/status to gbs-pipeline.log
   │   • decides retries / invokes the debugger
   │
   └── Skill("gbs-5-bwa") ── in-process run_skill() ─▶ [step subagent, fresh-context messages]
                                                                │  Bash / Read / Grep / Glob
                                                                ▼
                                                           bwa mem … | samtools …
```

Every orchestrator and subagent conversation is recorded as JSONL under `.gbs/` — which
is exactly what the **`./gbs view`** TUI reads (see [Viewing runs](#viewing-runs-gbs-view)).

---

## Quick start

Assuming the system tools and model are already installed (see [Installation](#installation)):

```bash
./gbs status           # sanity check — prints model id + GPU free

# run the full pipeline in the background, logging to .gbs/ (gives the viewer a session log)
# the model loads in-process on the first call (a few minutes), then stays resident
nohup ./gbs orchestrator > .gbs/orchestrator-$(date +%Y%m%d-%H%M%S).log 2>&1 &

./gbs view             # watch it live in the TUI
```

---

## Installation

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

## Running the pipeline

```bash
# Full pipeline (16 steps), in the background, logging to .gbs/ so the viewer sees the run:
nohup ./gbs orchestrator > .gbs/orchestrator-$(date +%Y%m%d-%H%M%S).log 2>&1 &
echo "PID: $!"
```

**Monitor** (in another terminal) — the richest option is the TUI (`./gbs view`); for a
plain tail:

```bash
tail -F gbs-pipeline.log        # real per-step log with timestamps + status
pgrep -af gbs-agent             # confirm the agent process is alive
```

**When it finishes:**

```bash
grep -cv '^#' final_snp_panel.vcf    # SNP count (typical: 100–300)
head final_snp_panel_summary.txt     # per-chromosome summary
cat gbs-pipeline-timing.csv          # per-step duration + token usage
```

---

## Viewing runs (`./gbs view`)

A live, keyboard-driven terminal UI for browsing pipeline runs recorded under `.gbs/` —
both **while a run is in progress** and **after it finishes**. It replaces the old
`browse_transcripts.py` script.

```bash
./gbs view                 # open the live run if one is active, else the most recent
./gbs view e24cd335        # open a specific run by session-id prefix
./gbs view --no-live       # static mode (no background polling)
```

### Layout — three panes + a status bar

```
┌ RUNS ─────────┬ STEPS ───────────────────────┬ DETAIL ─────────────┐
│ ✓ 05-30 12:53 │ ✓  5 BWA Alignment   1h15m #2 │ Step 5: BWA …       │
│ ✗ 05-30 09:19 │ ✗  5 BWA Alignment   48m   #1 │ FAILED · 48m · 3.2M │
│   ● ← live     │ ·· Orchestrator              │ $ bwa mem …         │
└───────────────┴──────────────────────────────┴─────────────────────┘
 [c] commands-only: OFF   [e] errors-only: OFF   [l] live-follow: ON   [/] search: off
```

- **RUNS** — one line per pipeline run. Glyph = run status (`✓` complete, `✗` stopped,
  `⟳` running, `·` unknown); a trailing **`●`** = the run is live.
- **STEPS** — steps of the selected run. Glyph = step status, then step number
  (`··` = the Orchestrator/Debugger lane), title, duration, and `#N` = attempt number
  for retried steps.
- **DETAIL** — the selected step's activity: header + meta line
  (`STATUS · duration · tokens · errors`), then events in order — agent narration, each
  `$ command`, and its output **verbatim** (errors shown in red, e.g. `[exit 1]`).
- **Status bar** (under the header) — always shows which toggles are ON/OFF and the
  active search term, updating the instant you press a key.

### Keys

| Key | Action |
|---|---|
| `↑` `↓` | Move within the focused list (the view updates as you move) |
| `Tab` / `Shift+Tab` | Switch focus between the Runs / Steps / Detail panes |
| `c` | **Commands-only** — show just the `$ command` lines |
| `e` | **Errors-only** — show only commands/results that failed (`[exit N]`, timeouts) |
| `/` | **Search** within the detail pane (Enter applies, `Esc` clears) |
| `o` | Jump to the **Orchestrator lane** — what the controller did to launch/verify/retry steps |
| `l` | Toggle **live-follow** (auto-refresh + tail the active step) |
| `r` | Refresh from disk now |
| `q` | Quit |

`c` and `e` are mutually exclusive (turning one on turns the other off — the status bar
shows it). Moving the cursor manually turns live-follow off so a refresh won't yank you
away; press `l` to re-engage.

### What's recorded under `.gbs/`

```
.gbs/
├── orchestrator-<YYYYMMDD-HHMMSS>.log   # one per run: "Session: <id>" + final status table
└── transcripts/<session_id>/
    ├── gbs-orchestrator.jsonl           # the orchestrator's transcript
    └── subagents/agent-<id>.jsonl       # one per step / debugger invocation
```

One session directory = one `./gbs orchestrator` run. Retried steps appear as repeated
attempts; a debugger invocation appears as its own entry.

---

## Pipeline steps

| Step | Skill | Description | Est. time |
|------|-------|-------------|-----------|
| 0 | `gbs-0-lane-info` | Parse FASTQs to generate the lane-info list | 5s |
| 1 | `gbs-1-cutadapt` | Trim Illumina adapters (parallel) | ~10min |
| 2 | `gbs-2-radtags` | Enzyme filtering with `process_radtags` (parallel) | ~30min |
| 3 | `gbs-3-rename` | Rename per-lane outputs to per-sample names | 10s |
| 4 | `gbs-4-popmap` | Generate the population map from the sample CSV | 1s |
| 5 | `gbs-5-bwa` | Align to the reference with BWA-MEM (parallel) | ~1-2hr |
| 6 | `gbs-6-gstacks` | Reference-based genotyping | ~30-60min |
| 7 | `gbs-7-populations` | Population-level filtering and export | ~10-30min |
| 8 | `gbs-8-vcf-filter` | VCF filtering + chromosome selection | ~1min |
| 9 | `gbs-9-snp-dup-hwe` | SNP duplication detection + HWE filtering | ~2min |
| 10 | `gbs-10-ld-clump` | Linkage-disequilibrium pruning (`bigsnpr`) | ~5min |
| 11 | `gbs-11-remove-atgc` | Remove strand-ambiguous A/T and G/C SNPs | 5s |
| 12 | `gbs-12-maf-filter` | Minor-allele-frequency filter (MAF ≥ 0.1) | 5s |
| 13 | `gbs-13-flanking` | Remove SNPs in complex/duplicated regions | 10s |
| 14 | `gbs-14-blast-map` | BLAST validation of SNP uniqueness | ~2min |
| 15 | `gbs-15-even-dist` | Select the final panel with even chromosome coverage | 5s |

---

## `./gbs` command reference

```bash
./gbs status                      # environment + model/GPU info + recent sessions
./gbs view [session] [--no-live]  # browse runs in the TUI
./gbs orchestrator                # run the full pipeline (steps 0-15)
./gbs orchestrator 5              # resume from step 5
./gbs orchestrator 8 --only       # run only step 8
./gbs orchestrator 8 --only --clean   # clean step 8 outputs first, then run it
./gbs run gbs-5-bwa               # run one skill standalone (no orchestrator)
./gbs debugger 9 "vcftools error" # manually invoke the autonomous debugger on a step
```

**Cleaning outputs:**

```bash
bash clean_pipeline.sh all        # wipe ALL pipeline outputs (keeps raw data)
bash clean_pipeline.sh 5          # clean only step 5
bash clean_pipeline.sh 5-10       # clean steps 5 through 10
bash clean_pipeline.sh indexes    # clean BWA + BLAST indexes (expensive to rebuild)
```

**Resetting the Python env** (separate from pipeline data — wipes `.venv/` + caches):

```bash
bash clean_env.sh                 # then re-run `bash setup.sh` to rebuild
```

---

## Error handling (4 layers)

1. **Step self-heal** — each step runs pre-flight checks and auto-fixes common issues
   (missing directories, permissions, stale files).
2. **Step retry** — after self-healing, the step retries its execution once internally.
3. **Orchestrator retry** — if a step still fails, the orchestrator retries the whole step.
4. **Autonomous debugger** — if all else fails, `gbs-debugger` reads the failed step's
   `SKILL.md`, investigates the actual system state, diagnoses the root cause, applies a
   targeted fix, validates it, and resumes. It has **zero hardcoded per-step knowledge**.

In the TUI, retries and debugger runs are visible directly: a retried step shows
`#1` (✗) then `#2` (✓), and the debugger appears as its own entry — press `o`/scroll to
see the orchestrator's decisions.

---

## Outputs

| File | Contents |
|---|---|
| `final_snp_panel.vcf` | The deliverable — quality-filtered SNPs across all chromosomes |
| `final_snp_panel_summary.txt` | Per-chromosome breakdown (length, SNP count, sources) |
| `snp_distribution.txt` | Tab-delimited SNP positions for visualization |
| `gbs-pipeline.log` | Execution timeline with real timestamps + per-step status |
| `gbs-pipeline-timing.csv` | Per-step duration + token usage (latest run) |
| `gbs-pipeline-token-report.txt` | Markdown token/timing report (latest run) |

---

## Adapting for your organism

The shipped configuration targets a crayfish genome with the **sbfI** restriction enzyme
and 94 chromosomes (`NC_091150.1`–`NC_091243.1`). For a different organism, update:

- **Enzyme** — `00-scripts/02_process_radtags_1_enzyme_parallel_pe.sh` and the Step 2 skill.
- **Chromosome names** — the chromosome filter in `.claude/skills/gbs-8-vcf-filter/SKILL.md`.
- **Chromosome count** — Step 15's even-distribution logic.

The pipeline detects sample counts and chromosome names from your actual data at run time;
review the per-step skills under `.claude/skills/` if you hit validation errors (they
carry expected values calibrated to the original dataset).

---

## Validation (optional)

The pipeline runtime has parity/e2e tests for *bioinformatics correctness* (these run the
real tools; they are not viewer tests):

```bash
pytest tests/test_step_parity.py   # per-step outputs vs tests/reference/step_N.json
pytest tests/test_e2e.py           # full clean run + validate final_snp_panel.vcf (~4h)
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| First run pauses minutes before any output | The ~60 GB model is loading into VRAM (one-time per process) | Normal — watch `nvidia-smi`; it stays resident after |
| `RuntimeError: NVIDIA driver too old` | torch built for newer CUDA than the driver | Use the cu118 torch wheels (Installation §3) |
| CUDA out of memory during a long step | Context too large for in-process KV cache (no PagedAttention) | Lower `GBS_MAX_CONTEXT_TOKENS` (e.g. `export GBS_MAX_CONTEXT_TOKENS=24576`) and re-run |
| `FP8 quantized models is only supported on ... compute capability >= 8.9` | You pointed `GBS_MODEL_ID` at the `-FP8` checkpoint on an Ampere GPU (A100 = 8.0) | Use the default bf16 checkpoint (`Qwen/Qwen3-Coder-30B-A3B-Instruct`); FP8 only loads on 4090/H100 |
| `./gbs status` shows little GPU free before a run | Another process is holding VRAM | Free the card; the model needs ~60 GB contiguous |
| A step reports FAILURE but output files exist | The model judged its own work poorly | Check the files; resume with `./gbs orchestrator <next-step>` |
| Log shows fake timestamps like "2023-05-15…" | Model copied a SKILL.md template literally | The real timestamps are in `gbs-pipeline.log` / the `.gbs` transcripts |

---

## Repository layout

```
os_gbs_data/
├── .claude/skills/      # 18 SKILL.md modules — the per-step specs the agent follows
├── agent/               # gbs-agent: the Python runtime + ./gbs CLI (see agent/README.md)
│   └── gbs/viewer/      #   the ./gbs view TUI (model.py = parser, app.py = Textual UI)
├── 00-scripts/          # Bash/Python/R/Perl bioinformatics scripts (LLM-agnostic)
├── 01-info_files/       # adapters.fasta + your sample_information.csv
├── 02-raw/              # ** your raw FASTQs **
├── 04-all_samples/      # generated: renamed samples + BAM alignments
├── 05-stacks/           # generated: genotyping catalogs + VCFs
├── 08-genome/           # ** your reference genome **
├── 10-log_files/        # generated: timestamped execution logs
├── .gbs/                # generated: run logs + JSONL transcripts (what ./gbs view reads)
├── infra/               # deployment notes (model loads in-process; no server)
├── tests/               # pipeline parity/e2e tests
├── docs/superpowers/    # design specs + implementation plans
├── setup.sh             # one-shot venv + model installer
├── clean_pipeline.sh    # remove pipeline outputs by step
├── clean_env.sh         # wipe .venv/ + Python caches for a clean reinstall
└── gbs                  # the ./gbs CLI entry point
```
