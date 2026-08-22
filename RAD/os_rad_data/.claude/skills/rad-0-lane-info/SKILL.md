---
name: rad-0-lane-info
description: Run RAD pipeline Step 0 (prepare lane info) directly on the server
context: fork
model: sonnet
allowed-tools: Bash, Read, Grep, Glob
---

# RAD Pipeline — Step 0: Prepare Lane Info

You are running RAD pipeline Step 0 directly on the server. All paths are relative to the project root (`rad_data/`). Before running any commands, detect the project root:

```
RAD_DIR="$(pwd)"
```

If the current directory does not contain `02-raw/` and `00-scripts/`, search upward or report FAILURE.

## Pre-flight Checks

Run these 5 checks before executing. If checks 1–2 fail, report the failure and **stop immediately**. Checks 3–4 can be self-healed.

1. **Raw data directory exists**: `test -d 02-raw && test -d 00-scripts && echo OK`
2. **FASTQ files exist**: `ls 02-raw/*_1.fastq.gz | head -5` must list files. Also count them: `ls 02-raw/*_1.fastq.gz | wc -l` — record this number as EXPECTED_LINES.
3. **Required directories exist**: Check `01-info_files/` and `10-log_files/` — if either is missing, **self-heal** by running `mkdir -p 01-info_files 10-log_files`
4. **Script exists**: `test -f 00-scripts/00_prepare_lane_info.sh && echo OK` — if missing, report **UNFIXABLE**
5. **Existing output**: If `test -f 01-info_files/lane_info.txt` succeeds, note it will be overwritten

Report each check as PASS/FAIL before continuing.

## Execution

Run the step:

```
bash 00-scripts/00_prepare_lane_info.sh
```

Capture both stdout and stderr.

## Verification

After execution, run these 5 checks:

1. **File exists**: `test -f 01-info_files/lane_info.txt && echo EXISTS`
2. **Line count**: `wc -l 01-info_files/lane_info.txt` — must equal EXPECTED_LINES (the count of `_1.fastq.gz` files recorded in pre-flight check 2)
3. **Line format**: `head -5 01-info_files/lane_info.txt` — each line must match pattern `SRR[0-9]+_1`. Verify no lines deviate: `grep -cvE '^SRR[0-9]+_1$' 01-info_files/lane_info.txt` — must be 0
4. **No empty lines**: `grep -c '^$' 01-info_files/lane_info.txt` — must be 0
5. **Log copy exists**: `ls 10-log_files/*00_prepare_lane_info*` — timestamped copy should exist

If all 5 pass, report SUCCESS. If any fail, proceed to error diagnosis.

## Error Diagnosis and Self-Healing

Diagnose failures and attempt to self-heal (max 1 retry):

| Symptom | Diagnosis | Fix |
|---------|-----------|-----|
| Empty `lane_info.txt` | No matching files or broken symlinks in `02-raw/` | Run `ls -la 02-raw/ | head -20` to inspect. If symlinks broken → report as **UNFIXABLE** |
| Wrong line count | Script found unexpected files or missed some | Show actual line count alongside `ls 02-raw/*_1.fastq.gz | wc -l`. Report mismatch details |
| Permission denied | Script not executable | Run `chmod +x 00-scripts/00_prepare_lane_info.sh` then **retry execution** |
| Log copy missing | `10-log_files/` was missing | Run `mkdir -p 10-log_files` then **retry execution** |
| Output dir missing | `01-info_files/` was missing | Run `mkdir -p 01-info_files` then **retry execution** |
| perl not found | perl is not installed | Run `which perl` to check. Report as **UNFIXABLE** if missing |

After self-healing fix, go back to Execution, re-run, and re-verify. Only attempt self-healing **once**. If the retry also fails, report FAILURE.

## Output

End your response with this exact structured summary format:

```
## Step 0 Summary
- **Step**: 0 — Prepare Lane Info
- **Status**: SUCCESS | FAILURE
- **lane_info.txt lines**: <number>
- **Expected lines**: <EXPECTED_LINES>
- **Sample IDs (first 5)**: <comma-separated list>
- **Sample IDs (last 5)**: <comma-separated list>
- **Issues**: <none | description>
- **Self-healing attempted**: Yes (description) | No
```
