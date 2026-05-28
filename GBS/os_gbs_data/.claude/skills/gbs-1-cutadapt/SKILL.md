---
name: gbs-1-cutadapt
description: Run GBS pipeline Step 1 (cutadapt paired-end adapter trimming) on the server
context: fork
model: sonnet
allowed-tools: Bash, Read, Grep, Glob
---

# GBS Pipeline — Step 1: Cutadapt Paired-End Adapter Trimming

You are running GBS pipeline Step 1 directly on the server using **96 CPUs**. All paths are relative to the project root (`gbs_data/`).

## Pre-flight Checks

Run these 6 checks before executing. If checks 1–4 fail, **stop immediately**. Check 5 triggers self-heal. Check 6 is auto-clean.

1. **FASTQ pairs present**: Count R1 files: `ls 02-raw/*_1.fastq.gz | wc -l` → record as EXPECTED_SAMPLES. Count R2 files: `ls 02-raw/*_2.fastq.gz | wc -l` — must equal EXPECTED_SAMPLES (confirms all pairs exist)
2. **Adapters file exists**: `test -f 01-info_files/adapters.fasta && echo OK`
3. **Script exists**: `test -f 00-scripts/01_cutadapt_PE.sh && echo OK`
4. **cutadapt installed**: `which cutadapt`
5. **GNU parallel installed**: `which parallel` — if FAIL, use the **Sequential Fallback** below
6. **Stale output**: `ls 02-raw/trimmed/*.fastq.gz 2>/dev/null | wc -l` — if > 0, **self-heal** by running `rm -rf 02-raw/trimmed/*` before proceeding. Also ensure `10-log_files/` exists: `mkdir -p 10-log_files`

Report each check as PASS/FAIL before continuing.

## Execution (launch + adaptive polling)

Cutadapt over EXPECTED_SAMPLES paired-end samples on 96 cores takes ~10-15 min. Launch in the background and poll with sleep so the agent does not burn its tool-call budget on rapid `ls` checks.

### Launch

```bash
nohup bash 00-scripts/01_cutadapt_PE.sh 96 > 10-log_files/01_cutadapt_run.log 2>&1 &
```

Capture PID: `echo $!` (record as `CUTADAPT_PID`).

Report: "cutadapt launched for EXPECTED_SAMPLES samples (96 parallel jobs). Monitoring..."

### Adaptive Polling

**Schedule (escalating backoff):**
```
Poll 1: sleep 120  (2 min)
Poll 2: sleep 240  (4 min)
Poll 3: sleep 600  (10 min)
Poll 4: sleep 600  (10 min cap)
```

**Each poll runs (as ONE Bash call):**
```bash
pgrep -f '01_cutadapt_PE.sh' > /dev/null 2>&1 && echo "PROCESS_ALIVE" || echo "PROCESS_DONE"
echo "trimmed: $(ls 02-raw/trimmed/*.fastq.gz 2>/dev/null | wc -l) / $((EXPECTED_SAMPLES*2))"
wc -c < 10-log_files/01_cutadapt_run.log 2>/dev/null
tail -3 10-log_files/01_cutadapt_run.log 2>/dev/null
```

Report each poll: `"Poll N: cutadapt running, X/Y files done — next check in Z min"`.

**IMPORTANT**: Use `Bash(command="sleep N", timeout=<N*1000 + 10000>)` for each sleep — set the timeout slightly above the sleep duration.

**Exit conditions:**
- `PROCESS_DONE` + trimmed count == EXPECTED_SAMPLES × 2 → proceed to Phase 3 (Verification)
- `PROCESS_DONE` + trimmed count < expected → proceed to Verification anyway; the per-sample checks will diagnose missing samples
- 3 consecutive polls with trimmed count unchanged AND process alive → **WARNING** — report potential stall, continue polling once more
- Total wall time > 45 min → **FAILURE** — report timeout

## Verification

After execution, run these 6 checks:

1. **Output directory exists**: `test -d 02-raw/trimmed && echo EXISTS`
2. **File count**: `ls 02-raw/trimmed/*.fastq.gz | wc -l` — must equal EXPECTED_SAMPLES × 2 (one R1 + one R2 per sample)
3. **No empty files**: `find 02-raw/trimmed/ -name '*.fastq.gz' -empty | wc -l` — must be 0
4. **Log exists**: `ls 10-log_files/*01_cutadapt*` — timestamped log and script copy should exist
5. **Pass rate**: Parse the cutadapt log to extract pass rates. Use: `grep -c 'Pairs written' 10-log_files/*01_cutadapt.log` to count processed samples. Then: `grep 'Pairs written' 10-log_files/*01_cutadapt.log | tail -5` to spot-check. Flag if any sample shows < 90% pass rate
6. **File naming**: `ls 02-raw/trimmed/ | head -5` — files must match pattern `SRR[0-9]+_R{1,2}.fastq.gz`

If all 6 pass, report SUCCESS. If any fail, proceed to error diagnosis.

## Error Diagnosis and Self-Healing

Diagnose failures and attempt to self-heal (max 1 retry per issue):

| Symptom | Diagnosis | Fix |
|---------|-----------|-----|
| `parallel` not found | GNU parallel not installed | Use **Sequential Fallback** below |
| Permission denied | Script not executable | `chmod +x 00-scripts/01_cutadapt_PE.sh` then **retry** |
| Stale files causing issues | Previous partial run | `rm -rf 02-raw/trimmed/*` then **retry** |
| Wrong file count (partial) | Some samples failed | Identify which samples are missing by comparing `ls 02-raw/*_1.fastq.gz` basenames against `ls 02-raw/trimmed/*_R1.fastq.gz` basenames. Re-run cutadapt individually for missing samples |
| 0 reads for a sample | Corrupt input or wrong adapters | Check with `zcat 02-raw/<sample>_1.fastq.gz | head -4`. Report as **UNFIXABLE** if input is corrupt |
| Empty output files | cutadapt filtered everything | Check `-m 50` threshold — all reads shorter than 50bp. Report as **UNFIXABLE** |

After a self-healing fix, re-run and re-verify. Only attempt self-healing **once** per issue.

### Sequential Fallback (if parallel is missing)

```bash
mkdir -p 02-raw/trimmed
for f in 02-raw/*_1.fastq.gz; do
  base=$(basename "$f" _1.fastq.gz)
  cutadapt \
    -a file:01-info_files/adapters.fasta \
    -A file:01-info_files/adapters.fasta \
    -o "02-raw/trimmed/${base}_R1.fastq.gz" \
    -p "02-raw/trimmed/${base}_R2.fastq.gz" \
    -e 0.2 \
    -m 50 \
    "02-raw/${base}_1.fastq.gz" \
    "02-raw/${base}_2.fastq.gz"
done
```

## Output

End your response with this exact structured summary format:

```
## Step 1 Summary
- **Step**: 1 — Cutadapt Adapter Trimming
- **Status**: SUCCESS | FAILURE
- **Trimmed files**: <number> / <expected> expected
- **Samples processed**: <number>
- **CPUs used**: 96
- **Average pass rate**: <percentage or N/A>
- **Total read pairs processed**: <number or N/A>
- **Issues**: <none | description>
- **Self-healing attempted**: Yes (description) | No
```
