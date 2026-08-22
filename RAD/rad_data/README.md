# RAD Pipeline — AI-Automated Restriction-site Associated DNA sequencing

An end-to-end RAD (Restriction-site Associated DNA sequencing) bioinformatics pipeline automated through [Claude Code](https://claude.ai/claude-code) skills. The pipeline takes raw paired-end Illumina FASTQ files and produces a final SNP panel VCF with markers evenly distributed across all chromosomes — ready for genotyping array design.

The entire pipeline (16 steps) runs autonomously via a single command, with 4 layers of built-in error handling.

## Pipeline Overview

```
Raw FASTQs ──> Trim ──> Enzyme Filter ──> Align ──> Genotype ──> Filter ──> SNP Panel
  (952 files)   Step 1    Step 2          Step 5    Step 6-7     Steps 8-15   Final VCF
```

**Input**: Paired-end FASTQ files + reference genome + sample metadata CSV
**Output**: `final_snp_panel.vcf` — quality-filtered, LD-pruned, BLAST-validated SNP panel

## Directory Structure

```
rad_data/
├── .claude/skills/           # 18 Claude Code skill modules (the automation engine)
├── 00-scripts/               # Bash, Python, R, and Perl processing scripts
│   └── utility_scripts/      # Helper scripts
├── 01-info_files/            # Configuration and metadata
│   ├── adapters.fasta        # Illumina adapter sequences (included)
│   └── sample_information.csv  # ** YOU PROVIDE THIS **
├── 02-raw/                   # ** YOUR RAW FASTQ FILES GO HERE **
├── 04-all_samples/           # Generated: renamed samples + BAM alignments
├── 05-stacks/                # Generated: genotyping catalogs + VCFs
├── 08-genome/                # ** YOUR REFERENCE GENOME GOES HERE **
├── 10-log_files/             # Generated: timestamped execution logs
├── clean_pipeline.sh         # Utility to remove pipeline outputs by step
└── filter_hwe_by_pop.pl      # Hardy-Weinberg equilibrium filter (Perl)
```

Directories marked **generated** are populated by the pipeline. The `03-samples/` directory is created automatically during Step 2.

## Prerequisites

### Claude Code

Install [Claude Code](https://claude.ai/claude-code) (CLI, desktop app, or IDE extension). The skills in `.claude/skills/` are what drive the automation.

### System Tools

The following must be installed and available on `$PATH`:

| Tool | Used By | Purpose |
|------|---------|---------|
| `cutadapt` | Step 1 | Adapter trimming |
| `process_radtags` | Step 2 | Restriction enzyme filtering (Stacks) |
| `bwa` | Step 5 | Sequence alignment |
| `samtools` | Step 5 | BAM sorting and indexing |
| `gstacks` | Step 6 | Reference-based genotyping (Stacks) |
| `populations` | Step 7 | Population-level SNP export (Stacks) |
| `vcftools` | Steps 8-12 | VCF filtering and manipulation |
| `bcftools` | Step 8 | VCF format conversion |
| `plink` | Steps 8, 10 | PLINK format operations |
| `blastn`, `makeblastdb` | Step 14 | SNP uniqueness validation |
| `parallel` | Steps 1, 2, 5 | GNU parallel for multi-core execution |
| `perl` | Steps 3, 9 | Script execution |
| `python3` | Steps 8-15 | Python 3 processing scripts |
| `Rscript` | Step 10 | R with `bigsnpr` package (LD clumping) |

### R Package

```r
install.packages("bigsnpr")
```

## Setup

### 1. Clone or copy this repository

```bash
cp -r rad_data/ /your/workspace/rad_data/
cd /your/workspace/rad_data/
```

### 2. Add your raw FASTQ files

Place paired-end FASTQ files in `02-raw/`. File naming convention:

```
02-raw/
├── SRR30282941_1.fastq.gz    # Forward reads (read 1)
├── SRR30282941_2.fastq.gz    # Reverse reads (read 2)
├── SRR30282940_1.fastq.gz
├── SRR30282940_2.fastq.gz
└── ...
```

The `_1` / `_2` suffix before `.fastq.gz` distinguishes forward and reverse reads.

### 3. Add your reference genome

```
08-genome/
└── genome.fasta              # Reference genome (FASTA format)
```

BWA and BLAST indexes are built automatically by the pipeline if they don't exist.

### 4. Prepare your sample information CSV

Edit `01-info_files/sample_information.csv`. This file maps sequencing lanes to samples and populations:

```csv
#Lane,Barcode,Population,Sample,PopulationID,PlatePosition,,
SRR30282941,TGACACC,P01,ROW-04-22,1,A01,,Notes
SRR30282940,CTCACT,P01,ROW-05-22,1,A02,,DO NOT modify the column titles in the header line
SRR30282944,CTCCTTA,P01,ROW-03-22,1,A03,,DO NOT modify the order of the first six columns
```

**Rules**:
- Do NOT modify the column titles in the header line
- Do NOT modify the order of the first six columns
- Do NOT modify the plate position format (use `A01`, not `A1`)
- Lane names must match your FASTQ file prefixes (without `_1.fastq.gz`)

### 5. Configure for your organism

The pipeline is configured for a crayfish genome with **sbfI** restriction enzyme and 94 chromosomes (NC_091150.1 through NC_091243.1). If your organism differs, you'll need to update:

- **Enzyme**: Edit the `process_radtags` command in `00-scripts/02_process_radtags_1_enzyme_parallel_pe.sh` and the Step 2 skill
- **Chromosome names**: Update the chromosome filtering in Step 8's skill (`.claude/skills/rad-8-vcf-filter/SKILL.md`)
- **Chromosome count**: Update Step 15's even distribution logic if your genome has a different number of chromosomes

## Usage

Open Claude Code in the `rad_data/` directory and use slash commands:

### Run the full pipeline

```
/rad-orchestrator
```

Runs all 16 steps (0 through 15) sequentially. Estimated total time: ~3-4 hours depending on sample count and hardware.

### Resume from a specific step

```
/rad-orchestrator 5
```

Resumes from step 5 through 15 (assumes prior steps completed successfully).

### Clean and restart

```
/rad-orchestrator 0 --clean
```

Removes all outputs from step 0 onward, then reruns the full pipeline.

### Run a single step

```
/rad-orchestrator 8 --only
```

Runs only step 8. Useful for debugging or re-running individual steps.

### Run individual steps directly

Each step can also be invoked as a standalone skill:

```
/rad-0-lane-info
/rad-1-cutadapt
/rad-5-bwa
/rad-10-ld-clump
...
```

### Clean pipeline outputs

```bash
./clean_pipeline.sh           # Clean all outputs (steps 0-15)
./clean_pipeline.sh 5         # Clean only step 5
./clean_pipeline.sh 5-10      # Clean steps 5 through 10
./clean_pipeline.sh indexes   # Clean BWA + BLAST indexes (expensive to rebuild)
```

## Pipeline Steps

| Step | Skill | Description | Est. Time |
|------|-------|-------------|-----------|
| 0 | `rad-0-lane-info` | Parse FASTQs to generate lane info list | 5s |
| 1 | `rad-1-cutadapt` | Trim Illumina adapters (parallel) | 10min |
| 2 | `rad-2-radtags` | Enzyme filtering with `process_radtags` (parallel) | 30min |
| 3 | `rad-3-rename` | Rename per-lane outputs to per-sample names | 10s |
| 4 | `rad-4-popmap` | Generate population map from sample CSV | 1s |
| 5 | `rad-5-bwa` | Align to reference genome with BWA mem (parallel) | 1-2hr |
| 6 | `rad-6-gstacks` | Reference-based genotyping | 30-60min |
| 7 | `rad-7-populations` | Population-level filtering and export | 10-30min |
| 8 | `rad-8-vcf-filter` | VCF filtering + chromosome selection | 1min |
| 9 | `rad-9-snp-dup-hwe` | SNP duplication detection + HWE filtering | 2min |
| 10 | `rad-10-ld-clump` | Linkage disequilibrium pruning (r^2 >= 0.2) | 5min |
| 11 | `rad-11-remove-atgc` | Remove strand-ambiguous A/T and G/C SNPs | 5s |
| 12 | `rad-12-maf-filter` | Minor allele frequency filter (MAF >= 0.1) | 5s |
| 13 | `rad-13-flanking` | Remove SNPs in complex/duplicated regions | 10s |
| 14 | `rad-14-blast-map` | BLAST validation of SNP uniqueness in genome | 2min |
| 15 | `rad-15-even-dist` | Select final panel with even chromosome coverage | 5s |

## Error Handling

The pipeline implements 4 layers of error defense:

1. **Step self-heal**: Each step runs pre-flight checks and auto-fixes common issues (missing directories, permissions, stale files)
2. **Step retry**: After self-healing, each step retries its execution once internally
3. **Orchestrator retry**: If a step fails, the orchestrator retries the entire step once
4. **Autonomous debugger**: If all else fails, the `rad-debugger` skill performs deep root-cause analysis, reads the failed step's specification, applies a targeted fix, and validates before resuming

## Output

The final deliverable is `final_snp_panel.vcf` — a VCF file containing quality-filtered SNPs distributed across all chromosomes. Companion files:

- `final_snp_panel_summary.txt` — per-chromosome breakdown (chromosome, length, SNP count, sources)
- `snp_distribution.txt` — tab-delimited SNP positions for visualization
- `rad-pipeline.log` — execution timeline with timestamps
- `rad-pipeline-timing.csv` — detailed per-step timing metrics

## Browsing Step Transcripts

Every skill execution is recorded as a full conversation transcript (JSONL) by Claude Code. Use `00-scripts/browse_transcripts.py` to browse these:

```bash
# List all sessions that have transcripts
python3 00-scripts/browse_transcripts.py sessions

# List all steps from the latest pipeline run (with attempt count, size, timing)
python3 00-scripts/browse_transcripts.py list

# Show the full conversation for a step (all attempts if retried)
python3 00-scripts/browse_transcripts.py show 5

# If you ran the pipeline multiple times in one session, select a specific run
python3 00-scripts/browse_transcripts.py list --run 1
python3 00-scripts/browse_transcripts.py show 5 --run 1

# Show only a specific attempt
python3 00-scripts/browse_transcripts.py show 5 --attempt 1

# Show only the bash commands that were run
python3 00-scripts/browse_transcripts.py show 5 --commands

# Show only errors and failures
python3 00-scripts/browse_transcripts.py show 5 --errors

# Show a condensed summary (tool counts, commands, API crash status)
python3 00-scripts/browse_transcripts.py show 5 --summary

# Get the raw .jsonl file path (for piping to jq, less, etc.)
python3 00-scripts/browse_transcripts.py path 5
```

The transcripts are stored by Claude Code at `~/.claude/projects/<project-hash>/<session-id>/subagents/`. Each `.jsonl` file contains every tool call, bash command, reasoning step, and output from a single skill invocation — useful for auditing exactly what happened during a pipeline run, diagnosing failures, or understanding retry behavior.

## Autonomous Debugger

The `rad-debugger` skill (`.claude/skills/rad-debugger/SKILL.md`) is the 4th layer of error defense. When a step fails after self-heal + step retry + orchestrator retry, the orchestrator escalates to the debugger automatically.

The debugger has **zero hardcoded knowledge** of any step. It works by:

1. Reading the failed step's `SKILL.md` to understand what the step does and what it expects
2. Investigating the actual system state (logs, output files, disk space, processes)
3. Diagnosing the root cause and categorizing the error
4. Applying a targeted fix
5. Validating the fix before reporting back

It can also be invoked manually:

```
/rad-debugger 5                          # Debug step 5
/rad-debugger 8 "vcftools returned exit code 1"   # Debug with error context
```

The debugger runs on Opus and has access to Bash, Read, Grep, Glob, and Write tools.

## Skill Architecture

All automation lives in `.claude/skills/` as SKILL.md files. Each skill is a detailed specification that tells Claude Code:

- What pre-flight checks to run before execution
- The exact commands and scripts to execute
- How to verify success (expected output counts, file sizes, content checks)
- How to diagnose and self-heal common failures

The skills use the project's existing bash/python/R/perl scripts in `00-scripts/` — they orchestrate, they don't replace the underlying bioinformatics tools.

## Adapting for Your Project

To use this pipeline with different data:

1. Replace FASTQs in `02-raw/` and genome in `08-genome/`
2. Update `01-info_files/sample_information.csv` for your samples
3. Modify enzyme/chromosome parameters in skills if your organism differs (see Setup step 5)
4. Run `/rad-orchestrator`

The skill files in `.claude/skills/` contain hardcoded expected values calibrated to the original crayfish dataset (476 samples, 94 chromosomes). When adapting to a new dataset, the pipeline dynamically detects sample counts and chromosome names from your actual data — but review the skills if you encounter validation errors.
