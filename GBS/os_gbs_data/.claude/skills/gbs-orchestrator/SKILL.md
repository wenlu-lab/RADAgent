---
name: gbs-orchestrator
description: Run the complete 16-step GBS pipeline (steps 0-15) sequentially. Each step has 4 layers of error defense: step self-heal, step retry, orchestrator retry, and autonomous debugger. Use when user says "run full pipeline", "run all steps", "orchestrate pipeline", or "resume from step N". Invoke with /gbs-orchestrator [start-step] [--clean].
argument-hint: [start-step] [--clean] [--only]
allowed-tools: Bash, Read, Grep, Glob, Skill, Write
---

# GBS Pipeline — Master Orchestrator

Run all 16 steps of the GBS bioinformatics pipeline in sequence. Each step is executed by invoking its dedicated skill (`/gbs-0-lane-info` through `/gbs-15-even-dist`) as a forked subagent. This orchestrator stays in the main conversation to coordinate, log, and handle failures. Token tracking is handled by `00-scripts/gbs_token_tracker.py` and written to `gbs-pipeline-token-report.txt` (not displayed to user).

## Arguments

Parse `$ARGUMENTS` for:
- **start-step** (integer 0-15, default: 0) — step to start from. Enables resume after failure.
- **--clean** flag — if present, clean outputs from start step onward before running.
- **--only** flag — if present, run ONLY the specified step (not steps after it). Useful for testing a single step.

Examples:
- `/gbs-orchestrator` — full pipeline from step 0 through 15
- `/gbs-orchestrator 5` — resume from step 5 through 15
- `/gbs-orchestrator 5 --clean` — clean steps 5-15, then run from step 5
- `/gbs-orchestrator --clean` — clean all, then run from step 0
- `/gbs-orchestrator 0 --only` — run ONLY step 0
- `/gbs-orchestrator 8 --only --clean` — clean step 8, run only step 8

## Step Registry

| Step | Skill | Title | Est. Time |
|------|-------|-------|-----------|
| 0 | gbs-0-lane-info | Prepare Lane Info | 5s |
| 1 | gbs-1-cutadapt | Cutadapt Adapter Trimming | 10min |
| 2 | gbs-2-radtags | process_radtags Enzyme Filtering | 30min |
| 3 | gbs-3-rename | Rename Samples | 10s |
| 4 | gbs-4-popmap | Prepare Population Map | 1s |
| 5 | gbs-5-bwa | BWA Alignment | 1-2hr |
| 6 | gbs-6-gstacks | gstacks Genotyping | 30-60min |
| 7 | gbs-7-populations | Stacks populations | 10-30min |
| 8 | gbs-8-vcf-filter | VCF Filtering + Chr Selection | 1min |
| 9 | gbs-9-snp-dup-hwe | SNP Duplication + HWE | 2min |
| 10 | gbs-10-ld-clump | LD Clumping | 5min |
| 11 | gbs-11-remove-atgc | Remove A/T and G/C SNPs | 5s |
| 12 | gbs-12-maf-filter | MAF 0.1 Filter | 5s |
| 13 | gbs-13-flanking | Flanking Variants Filter | 10s |
| 14 | gbs-14-blast-map | BLAST Mapping | 2min |
| 15 | gbs-15-even-dist | Even Distribution (Final Panel) | 5s |

---

## Phase 1: Pre-flight

1. **Verify project root**: Run `test -d 02-raw && test -d 00-scripts && echo OK`. If FAIL, try `cd ~/gbs_data` and recheck. If still FAIL → stop: "Not in gbs_data directory."

2. **Parse arguments**: Extract START_STEP, CLEAN, and ONLY flags from `$ARGUMENTS`.
   - If `$ARGUMENTS` contains a number (0-15), that's START_STEP
   - If `$ARGUMENTS` contains `--clean`, set CLEAN=true
   - If `$ARGUMENTS` contains `--only`, set ONLY=true — run ONLY START_STEP, then stop (END_STEP = START_STEP)
   - Default: START_STEP=0, CLEAN=false, ONLY=false
   - If ONLY is false: END_STEP = 15 (run through to end)

3. **Record pipeline start time**:
   ```bash
   date +%s > /tmp/gbs_pipeline_start.txt
   ```

4. **Initialize timing tracker**:
   ```bash
   python3 00-scripts/gbs_token_tracker.py --init
   ```

5. **Initialize log**:
   ```bash
   echo "" >> gbs-pipeline.log
   echo "================================================" >> gbs-pipeline.log
   echo "GBS Pipeline Run — $(date '+%Y-%m-%d %H:%M:%S')" >> gbs-pipeline.log
   echo "Starting from step: <START_STEP>" >> gbs-pipeline.log
   echo "Clean mode: <yes/no>" >> gbs-pipeline.log
   echo "================================================" >> gbs-pipeline.log
   ```

6. **Report to user**: "Starting GBS pipeline from step START_STEP. Clean mode: yes/no."

---

## Phase 2: Clean (if --clean)

If CLEAN is true:

```bash
bash clean_pipeline.sh <START_STEP>-15
echo "[$(date '+%Y-%m-%d %H:%M:%S')] CLEAN: Removed outputs for steps <START_STEP>-15" >> gbs-pipeline.log
```

If START_STEP is 0, use `bash clean_pipeline.sh all` instead.

Report: "Cleaned outputs for steps START_STEP through 15."

---

## Phase 3: Sequential Execution

For each step N from START_STEP to END_STEP (15 normally, or START_STEP if `--only`):

### Step N execution procedure:

**3a. Record step start time:**
```bash
date +%s > /tmp/gbs_step_start.txt
echo "[$(date '+%Y-%m-%d %H:%M:%S')] STEP <N>: <Title> — STARTING" >> gbs-pipeline.log
```

Report to user: "Step N/15: Title — starting..."

**3b. Invoke the step skill:**

Use the Skill tool:
```
skill: gbs-<N>-<name>  (from the Step Registry table above, e.g., step 0 → gbs-0-lane-info, step 5 → gbs-5-bwa)
```

Wait for the forked subagent to complete and return its result. This may take seconds (fast steps) or hours (steps 5, 6, 7 which use internal nohup+polling).

**3c. Parse the result:**

Search the returned text for status:
- If text contains `SUCCESS` (look for `**Status**: SUCCESS` or `Status: SUCCESS`) → STATUS = SUCCESS
- If text contains `FAILURE` or `FAIL` → STATUS = FAILURE
- If neither found → STATUS = FAILURE with note "Could not parse step result"

**3c-bis. On-disk cross-check (MANDATORY before treating any non-SUCCESS as failure):**

The subagent's self-report is sometimes wrong. It may have produced correct
output files but failed to summarize them, or it may have hallucinated a
problem (e.g. misreading disk space, miscounting files). Trusting the
subagent blindly has caused several incorrect pipeline aborts where the
underlying bioinformatics work had actually succeeded.

If STATUS is anything other than SUCCESS, run the on-disk check for this
step (table below). If the check exits 0 (outputs present and non-empty),
OVERRIDE STATUS to SUCCESS and log the override. Otherwise leave STATUS as
FAILURE and proceed to 3f.

First compute EXPECTED_LANES (number of lanes from step 0 output):
```bash
EL=$(wc -l < 01-info_files/lane_info.txt 2>/dev/null || echo 0)
```

Run the row matching the current step N as a SINGLE Bash call. Exit code 0
= outputs are valid; non-zero = outputs missing or incomplete.

| N | On-disk completeness check |
|---|----------------------------|
| 0 | `test -s 01-info_files/lane_info.txt` |
| 1 | `[ "$(ls 02-raw/trimmed/*.fastq.gz 2>/dev/null \| wc -l)" -ge $((EL*2)) ] && [ "$(find 02-raw/trimmed/ -name '*.fastq.gz' -empty 2>/dev/null \| wc -l)" -eq 0 ]` |
| 2 | `[ "$(ls -d 03-samples/*/ 2>/dev/null \| wc -l)" -ge "$EL" ] && [ "$(find 03-samples/ -name '*.fq.gz' -empty 2>/dev/null \| wc -l)" -eq 0 ]` |
| 3 | `[ "$(ls 04-all_samples/*.fq.gz 2>/dev/null \| wc -l)" -ge $((EL*2)) ]` |
| 4 | `test -s 01-info_files/population_map.txt` |
| 5 | `[ "$(ls 04-all_samples/*.sorted.bam 2>/dev/null \| wc -l)" -ge "$EL" ] && [ "$(find 04-all_samples/ -name '*.sorted.bam' -empty 2>/dev/null \| wc -l)" -eq 0 ]` |
| 6 | `test -s 05-stacks/catalog.fa.gz && test -s 05-stacks/catalog.calls && grep -q 'gstacks is done' 10-log_files/gstacks_run.log 2>/dev/null` |
| 7 | `test -s 05-stacks/populations.snps.vcf && [ "$(grep -cv '^#' 05-stacks/populations.snps.vcf \| head -1)" -gt 0 ]` |
| 8 | `test -s filtered_m4_p80_x0_S1_chr.recode.vcf` |
| 9 | `test -s filtered_m4_p80_x0_S1_chr.singleton.hwe.recode.vcf` |
| 10 | `test -s filtered_m4_p80_x0_S1_chr.singleton.hwe.maf01.LD.recode.vcf` |
| 11 | `ls filtered_m4_p80_x0_S1_chr.singleton.hwe.maf01.LD.no_AT_CG.*vcf 2>/dev/null \| head -1 \| xargs -r test -s` |
| 12 | `test -s filtered_m4_p80_x0_S1_chr.singleton.hwe.maf10.LD.no_AT_CG.recode.vcf` |
| 13 | `test -s filtered_flanking.vcf && [ "$(grep -cv '^#' filtered_flanking.vcf \| head -1)" -gt 0 ]` |
| 14 | `test -s blast_output.txt` |
| 15 | `test -s final_snp_panel.vcf && [ "$(grep -cv '^#' final_snp_panel.vcf \| head -1)" -gt 0 ]` |

If the check exits 0 → OVERRIDE STATUS to SUCCESS and log:
```bash
echo "[$(date '+%Y-%m-%d %H:%M:%S')] STEP <N>: <Title> — VERIFIED ON DISK (subagent reported $ORIGINAL_STATUS but output files are valid)" >> gbs-pipeline.log
```
then proceed to 3d as SUCCESS. Do NOT enter 3f retry.

If the check exits non-zero → leave STATUS as FAILURE and proceed normally
to 3f (retry → debugger → stop).

**3d. Record step end time, tokens, and log:**
```bash
STEP_START=$(cat /tmp/gbs_step_start.txt)
STEP_END=$(date +%s)
DURATION=$((STEP_END - STEP_START))

# Record step timing + tokens to CSV (token tracker handles extraction)
python3 00-scripts/gbs_token_tracker.py --record-step <N> "<Title>" <STATUS> $STEP_START $STEP_END

echo "[$(date '+%Y-%m-%d %H:%M:%S')] STEP <N>: <Title> — <STATUS> (${DURATION}s)" >> gbs-pipeline.log
```

**3e. Report to user:**

Format duration as human-readable (< 60s → "Xs", 60-3600s → "Xm Ys", > 3600s → "Xh Ym Zs").

Report to user: "Step N: Title — STATUS (duration)"

**3f. If FAILURE → RETRY ONCE at orchestrator level:**

The step skill already attempted its own internal self-heal. But the orchestrator gets one more retry in case the failure was transient (e.g., temp disk full, process killed by OOM, race condition).

1. Log the first failure:
   ```bash
   echo "[$(date '+%Y-%m-%d %H:%M:%S')] STEP <N>: <Title> — FAILED (attempt 1), retrying..." >> gbs-pipeline.log
   ```

2. Report to user: "Step N failed on first attempt. Retrying once..."

3. **Re-invoke the same step skill** (second attempt):
   ```
   skill: gbs-<N>-<name>  (from the Step Registry table above, e.g., step 0 → gbs-0-lane-info, step 5 → gbs-5-bwa)
   ```

4. Parse the retry result the same way (3c: parse status, **3c-bis: on-disk cross-check — override to SUCCESS if outputs are present**, 3d: record timing + tokens + log).

5. **If retry succeeds OR 3c-bis verified outputs on disk**: Log as SUCCESS with note "(passed on retry)" or "(verified on disk)", continue to next step.

6. **If retry also fails → ESCALATE TO DEBUGGER (Layer 4):**

   Log the escalation:
   ```bash
   echo "[$(date '+%Y-%m-%d %H:%M:%S')] STEP <N>: <Title> — FAILED (attempt 2), escalating to debugger..." >> gbs-pipeline.log
   ```

   Report to user: "Step N failed after retry. Invoking autonomous debugger for deep root-cause analysis..."

   Record debugger start time:
   ```bash
   date +%s > /tmp/gbs_debugger_start.txt
   ```

   Capture the key error output from the retry attempt (last ~50 lines of the step's output text). Store it as ERROR_CONTEXT.

   Invoke the debugger skill with the step number and error context:
   ```
   skill: gbs-debugger
   args: "<N> <ERROR_CONTEXT>"
   ```

   Wait for the debugger subagent to complete.

   Record debugger timing:
   ```bash
   DBG_START=$(cat /tmp/gbs_debugger_start.txt)
   DBG_END=$(date +%s)
   DBG_DURATION=$((DBG_END - DBG_START))
   echo "[$(date '+%Y-%m-%d %H:%M:%S')] DEBUGGER: Step <N> analysis completed in ${DBG_DURATION}s" >> gbs-pipeline.log
   ```

   **Parse the debugger result:**
   - Search for `**Status**: FIX_APPLIED` → DEBUGGER_STATUS = FIX_APPLIED
   - Search for `**Status**: UNFIXABLE` → DEBUGGER_STATUS = UNFIXABLE
   - If neither found → DEBUGGER_STATUS = UNFIXABLE

   **7a. If FIX_APPLIED → RE-INVOKE THE STEP (attempt 3):**

   ```bash
   echo "[$(date '+%Y-%m-%d %H:%M:%S')] STEP <N>: <Title> — Debugger applied fix, re-running step (attempt 3)..." >> gbs-pipeline.log
   ```

   Report to user: "Debugger applied a fix. Re-running step N (attempt 3)..."

   Re-invoke the step skill:
   ```
   skill: gbs-<N>-<name>  (from the Step Registry table above)
   ```

   Parse result the same way (3c: parse status, **3c-bis: on-disk cross-check**, 3d: record timing + tokens + log).

   If SUCCESS (including 3c-bis on-disk override):
   ```bash
   echo "[$(date '+%Y-%m-%d %H:%M:%S')] STEP <N>: <Title> — SUCCESS (passed after debugger fix, attempt 3)" >> gbs-pipeline.log
   ```
   Report: "Step N succeeded after debugger intervention!" Continue to next step.

   If FAILURE → fall through to STOP (7b).

   **7b. If UNFIXABLE or attempt 3 FAILURE → STOP for real:**

   ```bash
   echo "[$(date '+%Y-%m-%d %H:%M:%S')] STEP <N>: <Title> — FAILED (all 4 layers exhausted), stopping pipeline" >> gbs-pipeline.log
   echo "[$(date '+%Y-%m-%d %H:%M:%S')] PIPELINE STOPPED — Step <N> failed after retry + debugger" >> gbs-pipeline.log
   echo "[$(date '+%Y-%m-%d %H:%M:%S')] Resume with: /gbs-orchestrator <N>" >> gbs-pipeline.log
   ```

   Report the failure to the user, including:
   - Which step failed (all attempts)
   - The debugger's diagnosis (root cause, error category, debug trail)
   - Time spent on the failed step + debugger
   - Resume command: `/gbs-orchestrator <N>` or `/gbs-orchestrator <N> --clean`

   Jump to Phase 4 (Final Summary) with partial results.

**Self-heal summary (4 layers of defense):**
```
Layer 1: Step skill pre-flight detects issue → self-heals (mkdir, chmod, rm stale, etc.)
Layer 2: Step skill retries execution once after self-heal
Layer 3: Orchestrator retries the entire step skill once (catches transient failures)
Layer 4: Debugger (Opus) performs deep root-cause analysis, applies fix, validates
→ Total: up to 4-5 attempts before giving up
```

**3g. If SUCCESS → continue:**

Proceed to step N+1.

---

## Phase 4: Final Summary

After all steps complete (or after failure stops execution):

**Compute total pipeline time:**
```bash
PIPELINE_START=$(cat /tmp/gbs_pipeline_start.txt)
PIPELINE_END=$(date +%s)
TOTAL_DURATION=$((PIPELINE_END - PIPELINE_START))
```

**Log completion:**
```bash
echo "[$(date '+%Y-%m-%d %H:%M:%S')] PIPELINE <COMPLETED|STOPPED> — Total time: ${TOTAL_DURATION}s" >> gbs-pipeline.log
```

**Display the summary** (focused on step execution and outcomes):

```
## GBS Pipeline Summary
Pipeline run: <timestamp>
Start step: <START_STEP> | Clean mode: <yes/no>
Total wall-clock time: <Xh Ym Zs>

| Step | Name | Status | Duration | Debugger | Notes |
|------|------|--------|----------|----------|-------|
| 0 | Prepare Lane Info | SUCCESS/FAILURE/SKIPPED | 5s | N/A | |
| 1 | Cutadapt Adapter Trimming | SUCCESS/FAILURE/SKIPPED | 8m 32s | N/A | |
| ... | ... | ... | ... | ... | |
| 15 | Even Distribution (Final) | SUCCESS/FAILURE/SKIPPED | 6s | N/A | |

Steps completed: <count> / 16
Pipeline status: **COMPLETE** | **FAILED at step <N>** | **PARTIAL (resumed from step <START>)**
Total wall-clock time: <Xh Ym Zs>
```

Build this table from `gbs-pipeline-timing.csv` (columns: STEP, TITLE, STATUS, DURATION_SEC). Convert duration to human-readable (Xs, Xm Ys, Xh Ym Zs). The Debugger column shows `N/A` for steps where the debugger was not invoked, and `FIX_APPLIED`/`UNFIXABLE` if it was.

Status values:
- **SUCCESS** — step ran and passed (with duration)
- **FAILURE** — step ran and failed (pipeline stopped here)
- **SKIPPED** — step before START_STEP (not run, assumed complete from prior run)
- **NOT RUN** — step after the failure point (never reached)

**Write token report to file** (not displayed to user):
```bash
python3 00-scripts/gbs_token_tracker.py --summary > gbs-pipeline-token-report.txt
```

### If pipeline completed successfully:

```
## Pipeline Complete!
All 16 steps executed successfully.
Final output: final_snp_panel.vcf
Total time: <Xh Ym Zs>
Token report: gbs-pipeline-token-report.txt
Log file: gbs-pipeline.log
```

### If pipeline failed:
```
## Pipeline Stopped
Failed at step <N>: <Title>
Time spent before failure: <Xh Ym Zs>
Review the step output above for details.
Resume with: /gbs-orchestrator <N>
Clean and retry: /gbs-orchestrator <N> --clean
```
