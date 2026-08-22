---
name: rad-6-gstacks
description: Run RAD pipeline Step 6 (gstacks genotyping) on the server
context: fork
model: sonnet
allowed-tools: Bash, Read, Grep, Glob
---

# RAD Pipeline — Step 6: gstacks Reference-Based Genotyping (Autonomous)

You are running RAD pipeline Step 6 directly on the server. All paths are relative to the project root (`rad_data/`). This skill is **fully autonomous** — it launches gstacks, monitors with adaptive polling, and verifies output.

**What this step does**: Runs `gstacks` in reference-based mode to read 476 BAM files, build loci, and call SNPs/genotypes. Single multi-threaded process (96 threads internally).

**Input**: `04-all_samples/*.sorted.bam`, `01-info_files/population_map.txt`
**Output**: `05-stacks/` (catalog files, VCF, logs)

---

## Phase 1: Pre-flight Checks

Run these 6 checks. Report each as PASS/FAIL.

1. **BAM files exist**: `ls 04-all_samples/*.sorted.bam | wc -l` → EXPECTED_SAMPLES. Must be > 0
   - FAIL → **stop**: "Step 5 not completed. Run `/rad-5-bwa` first."

2. **Population map exists**: `test -f 01-info_files/population_map.txt && echo OK`. Count lines: `wc -l < 01-info_files/population_map.txt` — must equal EXPECTED_SAMPLES
   - FAIL → **stop**: "Population map missing. Run `/rad-4-popmap` first."

3. **Population map matches BAMs**: Verify all names in population_map.txt have corresponding `.sorted.bam`:
   ```bash
   cut -f1 01-info_files/population_map.txt | while read -r NAME; do
     test -f "04-all_samples/${NAME}.sorted.bam" || echo "MISSING: $NAME"
   done
   ```
   Must produce no output (all match).
   - FAIL → **stop**: report mismatched names

4. **gstacks installed**: `which gstacks`
   - FAIL → **stop**: "gstacks (Stacks suite) not found."

5. **Script exists**: `test -f 00-scripts/stacks2_gstacks_reference.sh && echo OK`
   - FAIL → **stop**: "gstacks script missing from 00-scripts/."

6. **Stale output / required dirs**:
   - If `ls 05-stacks/ 2>/dev/null | head -1` returns content → **self-heal**: `rm -rf 05-stacks`
   - Ensure dirs exist: `mkdir -p 05-stacks 10-log_files`

If all pass, proceed to Phase 2.

---

## Phase 2: Launch + Monitor

### Launch

```bash
nohup bash 00-scripts/stacks2_gstacks_reference.sh > 10-log_files/gstacks_run.log 2>&1 &
```

Capture PID: `echo $!`

Report: "gstacks launched for EXPECTED_SAMPLES samples (96 threads). Monitoring..."

### Adaptive Polling

gstacks is a single monolithic process — no per-sample progress counter. Monitor by checking process liveness and log growth.

**Schedule (escalating backoff):**
```
Poll 1:  sleep 120   (2 min)
Poll 2:  sleep 300   (5 min)
Poll 3:  sleep 600   (10 min)
Poll 4:  sleep 1200  (20 min)
Poll 5+: sleep 1800  (30 min cap)
```

**Each poll runs:**
```bash
# Process alive?
pgrep -f 'gstacks' > /dev/null 2>&1 && echo "PROCESS_ALIVE" || echo "PROCESS_DONE"
# Log size (growing = working):
wc -c < 10-log_files/gstacks_run.log 2>/dev/null
# Last progress line:
tail -3 10-log_files/gstacks_run.log 2>/dev/null
# Output marker:
test -f 05-stacks/catalog.fa.gz && echo "OUTPUT_EXISTS" || echo "NO_OUTPUT_YET"
```

Report each poll: `"Poll N: gstacks running, log at X bytes — next check in Y min"`

**IMPORTANT**: Use `Bash(command="sleep N", timeout=<N*1000 + 10000>)` for each sleep. Set timeout slightly above the sleep duration.

**Exit conditions:**
- `PROCESS_DONE` + `OUTPUT_EXISTS` → proceed to Phase 3 (Verification)
- `PROCESS_DONE` + no output → **FAILURE** — read last 20 lines of log: `tail -20 10-log_files/gstacks_run.log`. Report error
- Total wall time > 6 hours → **FAILURE** — report timeout
- 3 consecutive polls with log size unchanged AND process alive → **WARNING** — report potential stall, continue polling

---

## Phase 3: Verification + QC

gstacks has completed. Run these 5 checks:

1. **Output directory has files**: `ls 05-stacks/ | wc -l` — must be > 0

2. **Catalog files exist**: Check for key outputs:
   ```bash
   test -f 05-stacks/catalog.fa.gz && echo "catalog.fa.gz OK"
   test -f 05-stacks/catalog.calls && echo "catalog.calls OK"
   ```

3. **Log distribs exists**: `test -f 05-stacks/gstacks.log.distribs && echo OK`

4. **Parse gstacks output for stats**: Extract key metrics from the log:
   ```bash
   grep -E 'Read [0-9]+ BAM records|kept [0-9]+ primary|Built [0-9]+ loci|effective per-sample coverage|consistent phasing' 10-log_files/gstacks_run.log
   ```
   Extract:
   - Total BAM records read
   - Primary alignments kept (%)
   - Loci built
   - Mean per-sample coverage
   - Phasing success rate (%)

5. **Script audit copies**: `ls 10-log_files/*gstacks* 10-log_files/*population_map*`

If all pass, report SUCCESS with benchmark comparison.

### Error Diagnosis (if verification fails)

| Symptom | Diagnosis | Fix |
|---------|-----------|-----|
| Permission denied | Script not executable | `chmod +x 00-scripts/stacks2_gstacks_reference.sh`, retry |
| Stale 05-stacks/ | Previous failed run | `rm -rf 05-stacks`, retry |
| "No such file" in log | BAM or pop map path wrong | Check paths in script match actual locations |
| Out of memory | Too many samples for available RAM | Report as **UNFIXABLE** — need more memory or reduce samples |
| 0 loci built | Wrong enzyme or genome mismatch | Report with log excerpt |

---

## Output

End your response with this exact structured summary:

```
## Step 6 Summary
- **Step**: 6 — gstacks Reference-Based Genotyping
- **Status**: SUCCESS | FAILURE
- **BAM records read**: <number>
- **Primary alignments kept**: <percentage>
- **Loci built**: <number>
- **Mean coverage**: <number>x
- **Phasing rate**: <percentage>
- **Threads used**: 96
- **Total polls**: <number>
- **Issues**: <none | description>
- **Self-healing attempted**: Yes (description) | No

## Benchmark Comparison
| Metric | This run | PDF reference |
|--------|----------|---------------|
| BAM records | <n> | 733,633,497 |
| Alignments kept | <x>% | 97.3% |
| Loci built | <n> | 143,420 |
| Mean coverage | <x>x | 99.0x |
| Phasing rate | <x>% | 86.8% |
```
