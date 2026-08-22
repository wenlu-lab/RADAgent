---
name: rad-3-rename
description: Run RAD pipeline Step 3 (rename samples) on the server
context: fork
model: sonnet
allowed-tools: Bash, Read, Grep, Glob
---

# RAD Pipeline — Step 3: Rename Samples

You are running RAD pipeline Step 3 directly on the server. All paths are relative to the project root (`rad_data/`).

**What this step does**: Reads `sample_information.csv` to map per-lane process_radtags output from `03-samples/{LANE}/` into per-sample files with human-readable names in `04-all_samples/`. Uses hard links when a sample appears once, concatenation when it appears across multiple lanes.

**Command**: `bash 00-scripts/03_rename_samples_pe.sh`

**Input**: `03-samples/` (from Step 2), `01-info_files/sample_information.csv`
**Output**: Renamed/linked reads in `04-all_samples/` as `{Population}_{Sample}.{1,2}.fq.gz`, logs in `10-log_files/`

## Pre-flight Checks

Run these 6 checks before executing. Report each as PASS/FAIL.

1. **Step 2 completed**: `ls -d 03-samples/*/ | wc -l` → record as EXPECTED_LANES. Must be > 0. Spot-check one lane: `ls $(ls -d 03-samples/*/ | head -1)*.fq.gz | wc -l` — must have ≥ 4 files
   - FAIL → **stop immediately**: "Step 2 not completed. Run `/rad-2-radtags` first."

2. **sample_information.csv exists**: `test -f 01-info_files/sample_information.csv && echo OK`. Count data rows: `grep -cvE '^#|^Lane' 01-info_files/sample_information.csv` → record as EXPECTED_SAMPLES
   - FAIL → **stop immediately**: "sample_information.csv missing from 01-info_files/. This file must be provided manually — it maps lanes to sample names."

3. **Script exists**: `test -f 00-scripts/03_rename_samples_pe.sh && echo OK`
   - FAIL → **stop immediately**: "Rename script missing from 00-scripts/."

4. **perl installed**: `which perl`
   - FAIL → **stop immediately**: "perl is required by this script but not found on the system."

5. **Required dirs**: Check `04-all_samples/` and `10-log_files/` exist
   - FAIL → **self-heal**: `mkdir -p 04-all_samples 10-log_files`

6. **Stale output**: `ls 04-all_samples/*.fq.gz 2>/dev/null | wc -l`
   - If > 0 → **self-heal**: `rm -f 04-all_samples/*` and report as cleaned

Checks 1–4 are critical (stop with actionable message). Checks 5–6 self-heal.

## Execution

Run the step:

```
bash 00-scripts/03_rename_samples_pe.sh
```

No CPU parameter needed — sequential script. Fast because it creates hard links (no data copying for samples that appear once). Capture both stdout and stderr.

## Verification

After execution, run these 5 checks:

1. **File count**: `ls 04-all_samples/*.fq.gz | wc -l` — must equal EXPECTED_SAMPLES × 2 (one `.1.fq.gz` + one `.2.fq.gz` per sample)
2. **File naming**: `ls 04-all_samples/ | head -10` — all must match pattern `{Pop}_{Sample}.{1,2}.fq.gz` (e.g., `P01_ROW-04-22.1.fq.gz`)
3. **No empty files**: `find 04-all_samples/ -name '*.fq.gz' -empty | wc -l` — must be 0
4. **Hard links confirmed (spot-check)**: Compare inodes of 2-3 files between source and target:
   ```
   ls -i 04-all_samples/*.1.fq.gz | head -3
   ```
   Then find matching source in `03-samples/` and verify same inode number.
5. **Log exists**: `ls 10-log_files/*03_rename_samples*` — timestamped log and script audit copy should exist

If all 5 pass, report SUCCESS. If any fail, proceed to error diagnosis.

## Error Diagnosis and Self-Healing

Diagnose failures and attempt to self-heal (max 1 retry per issue):

| Symptom | Diagnosis | Fix |
|---------|-----------|-----|
| Permission denied on script | Script not executable | `chmod +x 00-scripts/03_rename_samples_pe.sh` then **retry** |
| `04-all_samples/` missing | Directory not created | `mkdir -p 04-all_samples` then **retry** |
| Hard link fails (cross-device) | Source and target on different filesystems | Report as **UNFIXABLE** — same filesystem expected |
| 0 output files | CSV lane names don't match `03-samples/` dir names | Check: `head -5 01-info_files/sample_information.csv` and `ls 03-samples/ | head -5`. Report the naming mismatch |
| Stale files causing issues | Previous partial run | `rm -f 04-all_samples/*` then **retry** |
| Temp files left behind | Script interrupted before cleanup | `rm -f renaming_01l.txt renaming_02l.txt renaming_01r.txt renaming_02r.txt` then **retry** |

After a self-healing fix, re-run and re-verify. Only attempt self-healing **once** per issue.

## Output

End your response with this exact structured summary format:

```
## Step 3 Summary
- **Step**: 3 — Rename Samples
- **Status**: SUCCESS | FAILURE
- **Files in 04-all_samples/**: <number> / <expected> expected
- **Sample naming pattern**: {Pop}_{Sample}.{1,2}.fq.gz
- **Hard links confirmed**: Yes | No
- **Log files**: <number>
- **Issues**: <none | description>
- **Self-healing attempted**: Yes (description) | No
```
