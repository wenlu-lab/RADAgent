---
name: rad-4-popmap
description: Run RAD pipeline Step 4 (prepare population map) on the server
context: fork
model: sonnet
allowed-tools: Bash, Read, Grep, Glob
---

# RAD Pipeline — Step 4: Prepare Population Map

You are running RAD pipeline Step 4 directly on the server. All paths are relative to the project root (`rad_data/`).

**What this step does**: Generates `population_map.txt` from `sample_information.csv`. Maps each sample to its population ID using awk: `{Population}_{Sample}\t{PopulationID}`.

**Command**: `bash 00-scripts/04_prepare_population_map.sh`

**Input**: `01-info_files/sample_information.csv`
**Output**: `01-info_files/population_map.txt`

## Pre-flight Checks

Run these 5 checks before executing. Report each as PASS/FAIL.

1. **Step 3 completed**: `ls 04-all_samples/*.1.fq.gz | wc -l` → record as EXPECTED_SAMPLES. Must be > 0
   - FAIL → **stop immediately**: "Step 3 not completed. Run `/rad-3-rename` first."

2. **sample_information.csv exists**: `test -f 01-info_files/sample_information.csv && echo OK`. Count data rows: `grep -cv '#' 01-info_files/sample_information.csv` — should equal EXPECTED_SAMPLES
   - FAIL → **stop immediately**: "sample_information.csv missing from 01-info_files/. This file must be provided manually — it maps lanes to populations."

3. **Script exists**: `test -f 00-scripts/04_prepare_population_map.sh && echo OK`
   - FAIL → **stop immediately**: "Population map script missing from 00-scripts/."

4. **Required dirs**: `test -d 10-log_files && echo OK`
   - FAIL → **self-heal**: `mkdir -p 10-log_files`

5. **Stale output**: `test -f 01-info_files/population_map.txt`
   - If exists → **self-heal**: `rm -f 01-info_files/population_map.txt` and report as cleaned

## Execution

Run the step:

```
bash 00-scripts/04_prepare_population_map.sh
```

Instant — single awk command on a small CSV file.

## Verification

After execution, run these 4 checks:

1. **File exists**: `test -f 01-info_files/population_map.txt && echo EXISTS`
2. **Line count**: `wc -l < 01-info_files/population_map.txt` — must equal EXPECTED_SAMPLES
3. **Format valid**: `head -5 01-info_files/population_map.txt` — each line must be `{name}\t{popID}` (tab-separated, 2 fields). Verify: `awk -F'\t' 'NF!=2' 01-info_files/population_map.txt | wc -l` — must be 0
4. **Names match 04-all_samples/ (spot-check)**: For the first 5 entries, verify matching files exist:
   ```
   head -5 01-info_files/population_map.txt | while read -r NAME POP; do
     test -f "04-all_samples/${NAME}.1.fq.gz" && echo "MATCH: $NAME" || echo "MISSING: $NAME"
   done
   ```
   All must be MATCH.

If all 4 pass, report SUCCESS. If any fail, proceed to error diagnosis.

## Error Diagnosis and Self-Healing

Diagnose failures and attempt to self-heal (max 1 retry per issue):

| Symptom | Diagnosis | Fix |
|---------|-----------|-----|
| Permission denied | Script not executable | `chmod +x 00-scripts/04_prepare_population_map.sh` then **retry** |
| 0 lines in output | `grep -v "#"` didn't match any lines | Check header format: `head -1 01-info_files/sample_information.csv`. If header uses different comment char, adjust grep and run awk manually |
| Wrong line count | Duplicates or missing entries | Check `sort -u` dedup count vs raw count. Report details |
| Names don't match files | CSV Population_Sample naming differs from file naming | Compare `head -3 01-info_files/population_map.txt` with `ls 04-all_samples/ | head -3`. Report the naming mismatch |

After a self-healing fix, re-run and re-verify. Only attempt self-healing **once** per issue.

## Output

End your response with this exact structured summary format:

```
## Step 4 Summary
- **Step**: 4 — Prepare Population Map
- **Status**: SUCCESS | FAILURE
- **Lines in population_map.txt**: <number> / <expected> expected
- **Format valid**: Yes | No
- **All names match 04-all_samples/**: Yes | No
- **Unique populations**: <list>
- **Issues**: <none | description>
- **Self-healing attempted**: Yes (description) | No
```
