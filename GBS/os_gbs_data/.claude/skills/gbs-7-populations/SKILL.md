---
name: gbs-7-populations
description: Run GBS pipeline Step 7 (Stacks populations) on the server
context: fork
model: sonnet
allowed-tools: Bash, Read, Grep, Glob
---

# GBS Pipeline — Step 7: Stacks populations (Autonomous)

You are running GBS pipeline Step 7 directly on the server. All paths are relative to the project root (`gbs_data/`). This skill is **fully autonomous** — it launches populations, monitors with adaptive polling, and verifies output.

**What this step does**: Filters loci by sample coverage (`-r 0.6` = 60% of individuals must have it), computes population summary statistics, and exports to VCF/FASTA/TreeMix. Reads gstacks catalog from `05-stacks/`, writes output back to the same directory.

**Command**: `populations -P 05-stacks -M 01-info_files/population_map.txt -t 20 -p 1 -r 0.6 --ordered-export --fasta-loci --vcf --treemix`

**Input**: `05-stacks/catalog.*` (from gstacks), `01-info_files/population_map.txt`
**Output**: `05-stacks/populations.snps.vcf` + summary stats, FASTA, TreeMix files

---

## Phase 1: Pre-flight Checks

Run these 5 checks. Report each as PASS/FAIL.

1. **gstacks output exists**: `test -f 05-stacks/catalog.fa.gz && test -f 05-stacks/catalog.calls && echo OK`
   - FAIL → **stop**: "Step 6 not completed. Run `/gbs-6-gstacks` first."

2. **Population map exists**: `test -f 01-info_files/population_map.txt && echo OK`. Count lines: `wc -l < 01-info_files/population_map.txt` → EXPECTED_SAMPLES
   - FAIL → **stop**: "Population map missing. Run `/gbs-4-popmap` first."

3. **populations installed**: `which populations`
   - FAIL → **stop**: "populations (Stacks suite) not found."

4. **Script exists**: `test -f 00-scripts/stacks2_populations_reference.sh && echo OK`
   - FAIL → **stop**: "Populations script missing from 00-scripts/."

5. **Stale populations output**: `ls 05-stacks/populations.* 2>/dev/null | wc -l`
   - If > 0 → **self-heal**: `rm -f 05-stacks/populations.*` (preserves catalog files from gstacks)
   - Also ensure: `mkdir -p 10-log_files`

If all pass, proceed to Phase 2.

---

## Phase 2: Launch + Monitor

### Launch

```bash
nohup bash 00-scripts/stacks2_populations_reference.sh > 10-log_files/populations_run.log 2>&1 &
```

Capture PID: `echo $!`

Report: "populations launched for EXPECTED_SAMPLES samples (20 threads). Monitoring..."

### Adaptive Polling

populations is mostly single-threaded, runtime ~10-30 min. Shorter intervals than gstacks.

**Schedule:**
```
Poll 1:  sleep 120   (2 min)
Poll 2:  sleep 300   (5 min)
Poll 3:  sleep 600   (10 min)
Poll 4+: sleep 600   (10 min cap)
```

**Each poll runs:**
```bash
# Process alive?
pgrep -f 'populations' > /dev/null 2>&1 && echo "PROCESS_ALIVE" || echo "PROCESS_DONE"
# Log size:
wc -c < 10-log_files/populations_run.log 2>/dev/null
# Last progress line:
tail -3 10-log_files/populations_run.log 2>/dev/null
# Completion marker:
test -f 05-stacks/populations.snps.vcf && echo "VCF_EXISTS" || echo "NO_VCF_YET"
```

Report each poll: `"Poll N: populations running, log at X bytes — next check in Y min"`

**IMPORTANT**: Use `Bash(command="sleep N", timeout=<N*1000 + 10000>)` for each sleep.

**Exit conditions:**
- `PROCESS_DONE` + `VCF_EXISTS` → proceed to Phase 3 (Verification)
- `PROCESS_DONE` + no VCF → **FAILURE** — read last 20 lines of log: `tail -20 10-log_files/populations_run.log`. Report error
- Total wall time > 2 hours → **FAILURE** — report timeout
- 3 consecutive polls with log size unchanged AND process alive → **WARNING** — report potential stall

---

## Phase 3: Verification + QC

populations has completed. Run these 5 checks:

1. **VCF exists**: `test -f 05-stacks/populations.snps.vcf && echo OK`

2. **VCF has content**: Count variant lines:
   ```bash
   grep -cv '^#' 05-stacks/populations.snps.vcf
   ```
   Must be > 0.

3. **Summary stats exist**:
   ```bash
   test -f 05-stacks/populations.sumstats_summary.tsv && echo OK
   test -f 05-stacks/populations.log.distribs && echo OK
   ```

4. **Parse log for key metrics**: Extract from populations output:
   ```bash
   grep -E 'Removed|Kept|variant sites|samples per locus|pi:' 10-log_files/populations_run.log
   ```
   Extract:
   - Loci removed / input count
   - Loci kept
   - Variant sites remaining
   - Mean samples per locus
   - Pi (nucleotide diversity)

5. **Audit copies**: `ls 10-log_files/*populations* 10-log_files/*population_map*`

If all pass, report SUCCESS with benchmark comparison.

### Error Diagnosis

| Symptom | Diagnosis | Fix |
|---------|-----------|-----|
| Permission denied | Script not executable | `chmod +x 00-scripts/stacks2_populations_reference.sh`, retry |
| Stale output conflict | Previous populations run | `rm -f 05-stacks/populations.*`, retry |
| "unable to open catalog" | gstacks output missing/corrupt | Re-run `/gbs-6-gstacks` |
| 0 loci kept | Filters too strict for data | Report with log — may need to adjust `-r` parameter |

---

## Output

End your response with this exact structured summary:

```
## Step 7 Summary
- **Step**: 7 — Stacks populations
- **Status**: SUCCESS | FAILURE
- **Loci input**: <from gstacks>
- **Loci kept**: <number>
- **Loci removed**: <number>
- **Variant sites**: <number>
- **Mean samples/locus**: <number>
- **Total polls**: <number>
- **Issues**: <none | description>
- **Self-healing attempted**: Yes (description) | No

## Benchmark Comparison
| Metric | This run | PDF reference |
|--------|----------|---------------|
| Loci kept | <n> | 7,193 |
| Variant sites | <n> | 147,220 |
| Samples/locus | <n> | 398.63 |
| Pi | <n> | 0.045245 |
```
