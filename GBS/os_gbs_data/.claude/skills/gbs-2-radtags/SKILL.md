---
name: gbs-2-radtags
description: Run GBS pipeline Step 2 (process_radtags enzyme filtering) on the server
context: fork
model: sonnet
allowed-tools: Bash, Read, Grep, Glob
---

# GBS Pipeline — Step 2: process_radtags Enzyme Filtering

You are running GBS pipeline Step 2 directly on the server using **96 CPUs**. All paths are relative to the project root (`gbs_data/`).

**What this step does**: Checks restriction enzyme (sbfI) cut sites, filters low-quality reads, and truncates reads to 120 bp. Reads from `02-raw/` (original raw FASTQs, NOT trimmed). Expects ~76% retained reads and ~23% "RAD cutsite not found" — this is normal for sbfI.

**Command**: `bash 00-scripts/02_process_radtags_1_enzyme_parallel_pe.sh 120 sbfI 96`
- `120` = truncate length (bp)
- `sbfI` = restriction enzyme
- `96` = parallel jobs

**Input**: `02-raw/*_1.fastq.gz` + `*_2.fastq.gz`, `01-info_files/lane_info.txt`, `01-info_files/sample_information.csv`
**Output**: `03-samples/{LANE}/` with 5 files per lane (4 `.fq.gz` + 1 log), audit copies in `10-log_files/`

## Pre-flight Checks

Run these 7 checks before executing. Report each as PASS/FAIL.

1. **FASTQ pairs in 02-raw/**: Count R1 files: `ls 02-raw/*_1.fastq.gz | wc -l` → record as EXPECTED_LANES. Count R2: `ls 02-raw/*_2.fastq.gz | wc -l` — must match EXPECTED_LANES
   - FAIL → **stop immediately**

2. **sample_information.csv exists**: `test -f 01-info_files/sample_information.csv && echo OK`
   - FAIL → **stop immediately**

3. **lane_info.txt exists**: `test -f 01-info_files/lane_info.txt && echo OK`. Count lines: `wc -l < 01-info_files/lane_info.txt` — must equal EXPECTED_LANES
   - FAIL → **stop immediately** (run `/gbs-0-lane-info` first)

4. **Scripts exist**: Check both:
   - `test -f 00-scripts/02_process_radtags_1_enzyme_parallel_pe.sh && echo OK`
   - `test -f 00-scripts/utility_scripts/process_radtags_1_enzyme_pe.sh && echo OK`
   - FAIL → **stop immediately**

5. **process_radtags installed**: `which process_radtags`
   - FAIL → **stop immediately**

6. **GNU parallel installed**: `which parallel`
   - FAIL → use **Sequential Fallback** below

7. **Stale output / required dirs**:
   - If `ls 03-samples/ 2>/dev/null | head -1` returns content → **self-heal**: `rm -rf 03-samples/*`
   - Ensure dirs exist: `mkdir -p 03-samples 10-log_files`

Checks 1–5 are critical. Check 6 triggers fallback. Check 7 is auto-clean.

## Execution (launch + adaptive polling)

This step takes ~25-30 minutes for 476 lanes on 96 cores. Launch in the background and poll progress so the agent yields control during waits.

### Launch

```bash
nohup bash 00-scripts/02_process_radtags_1_enzyme_parallel_pe.sh 120 sbfI 96 \
  > 10-log_files/02_radtags_run.log 2>&1 &
```

Capture PID: `echo $!` (record as `RADTAGS_PID`).

Report: "process_radtags launched for EXPECTED_LANES lanes (96 parallel jobs). Monitoring..."

### Adaptive Polling

The script is a `parallel` batch over EXPECTED_LANES lanes — per-lane progress is visible by counting subdirs of `03-samples/`. Monitor by checking process liveness, log growth, and dir count.

**Schedule (escalating backoff):**
```
Poll 1:  sleep 120   (2 min)
Poll 2:  sleep 240   (4 min)
Poll 3:  sleep 600   (10 min)
Poll 4:  sleep 1200  (20 min)
Poll 5+: sleep 1200  (20 min cap)
```

**Each poll runs:**
```bash
# Process alive?  (use the pattern below — `pgrep -f 'process_radtags'` would
# match this very shell command's argv on some systems; use parent-script name)
pgrep -f '02_process_radtags_1_enzyme_parallel_pe.sh' > /dev/null 2>&1 \
  && echo "PROCESS_ALIVE" || echo "PROCESS_DONE"
# Lane progress:
echo "dirs: $(ls -d 03-samples/*/ 2>/dev/null | wc -l) / EXPECTED_LANES"
# Log size (growing = working):
wc -c < 10-log_files/02_radtags_run.log 2>/dev/null
# Last log lines:
tail -3 10-log_files/02_radtags_run.log 2>/dev/null
```

Report each poll: `"Poll N: process_radtags running, X / EXPECTED_LANES lanes done — next check in Y min"`.

**IMPORTANT**: Use `Bash(command="sleep N", timeout=<N*1000 + 10000>)` for each sleep. Set timeout slightly above the sleep duration.

**Exit conditions:**
- `PROCESS_DONE` + dir count == EXPECTED_LANES → proceed to Phase 3 (Verification)
- `PROCESS_DONE` + dir count < EXPECTED_LANES → proceed to Verification anyway; the per-lane checks will diagnose missing lanes
- 3 consecutive polls with dir count unchanged AND process alive → **WARNING** — report potential stall, continue polling
- Total wall time > 90 minutes → **FAILURE** — report timeout

## Verification

After execution, run these 6 checks:

1. **Lane directory count**: `ls -d 03-samples/*/ | wc -l` — must equal EXPECTED_LANES
2. **Files per lane (spot-check)**: Pick 3 random lanes and check each has 5 files:
   ```
   for d in $(ls -d 03-samples/*/ | head -3); do echo "=== $(basename $d) ==="; ls "$d" | wc -l; done
   ```
   Expect 5 files each: `{LANE}.1.fq.gz`, `{LANE}.2.fq.gz`, `{LANE}.rem.1.fq.gz`, `{LANE}.rem.2.fq.gz`, `process_radtags.02-raw.log`
3. **No empty .fq.gz files**: `find 03-samples/ -name '*.fq.gz' -empty | wc -l` — must be 0
4. **Retained read % (spot-check)**: Parse logs from 5 random lanes:
   ```
   for d in $(ls -d 03-samples/*/ | shuf | head -5); do
     echo "=== $(basename $d) ===";
     grep -E 'total sequences|retained reads' "$d"/process_radtags.02-raw.log;
   done
   ```
   Expect 50–95% retained. Below 50% = WARNING. Below 10% = FAILURE.
5. **Log files in 10-log_files/**: `ls 10-log_files/*process_radtags* | wc -l` — expect EXPECTED_LANES lane logs + 1 command log. Also check: `ls 10-log_files/*02_process_radtags_1_enzyme*` for script audit copy
6. **sample_information.csv audit copy**: `ls 10-log_files/*sample_information*` — timestamped copy should exist

If all 6 pass, report SUCCESS. If any fail, proceed to error diagnosis.

## Error Diagnosis and Self-Healing

Diagnose failures and attempt to self-heal (max 1 retry per issue):

| Symptom | Diagnosis | Fix |
|---------|-----------|-----|
| `parallel` not found | GNU parallel missing | Use **Sequential Fallback** below |
| Permission denied | Scripts not executable | `chmod +x 00-scripts/02_process_radtags_1_enzyme_parallel_pe.sh 00-scripts/utility_scripts/process_radtags_1_enzyme_pe.sh` then **retry** |
| Stale output | Previous partial run | `rm -rf 03-samples/*` then **retry** |
| Missing lane dirs (partial) | Some lanes failed | Compare `ls -d 03-samples/*/` against `cat 01-info_files/lane_info.txt` to find missing. Re-run utility script individually for each missing lane |
| 0 retained reads for a lane | Corrupt input or wrong enzyme | Check: `zcat 02-raw/<LANE>.fastq.gz | head -4`. Report as **UNFIXABLE** if input corrupt |
| process_radtags error | Wrong enzyme name | Verify enzyme: `process_radtags --renz_1 sbfI 2>&1 | head -3`. Report as **UNFIXABLE** if enzyme not recognized |

After a self-healing fix, re-run and re-verify. Only attempt self-healing **once** per issue.

### Sequential Fallback (if parallel is missing)

```bash
TRIM_LENGTH=120
ENZYME1=sbfI
mkdir -p 03-samples 10-log_files
TIMESTAMP=$(date +%Y-%m-%d_%Hh%Mm%Ss)
cp 00-scripts/02_process_radtags_1_enzyme_parallel_pe.sh "10-log_files/${TIMESTAMP}_02_process_radtags_1_enzyme_parallel_pe.sh"
cp 01-info_files/sample_information.csv "10-log_files/${TIMESTAMP}_sample_information.csv"

while read -r LANE; do
  echo "Processing lane: $LANE"
  bash 00-scripts/utility_scripts/process_radtags_1_enzyme_pe.sh "$TRIM_LENGTH" "$ENZYME1" "$LANE"
done < 01-info_files/lane_info.txt
```

## Output

End your response with this exact structured summary format:

```
## Step 2 Summary
- **Step**: 2 — process_radtags Enzyme Filtering
- **Status**: SUCCESS | FAILURE
- **Lane directories**: <number> / <expected> expected
- **Files per lane**: 5 (4 .fq.gz + 1 log)
- **Retained read % (spot-check)**: <lane1: X%, lane2: Y%, ...>
- **Log files in 10-log_files/**: <number>
- **CPUs used**: 96
- **Issues**: <none | description>
- **Self-healing attempted**: Yes (description) | No
```
