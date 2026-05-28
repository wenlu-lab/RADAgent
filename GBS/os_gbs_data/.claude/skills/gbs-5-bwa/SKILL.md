---
name: gbs-5-bwa
description: Run GBS pipeline Step 5 (BWA alignment) on the server
context: fork
model: sonnet
allowed-tools: Bash, Read, Grep, Glob
---

# GBS Pipeline — Step 5: BWA Alignment (Autonomous)

You are running GBS pipeline Step 5 directly on the server. All paths are relative to the project root (`gbs_data/`). This skill is **fully autonomous** — once invoked, it handles indexing, alignment, monitoring, and verification without user intervention.

**What this step does**: Aligns all paired-end samples from `04-all_samples/` to the reference genome using `bwa mem`, filters for quality ≥ 10, sorts and indexes BAM files. Uses GNU parallel: 12 samples concurrently × 8 threads each = 96 CPUs.

**Input**: `04-all_samples/*.{1,2}.fq.gz`, `08-genome/genome.fasta`
**Output**: `04-all_samples/*.sorted.bam` + `.sorted.bam.bai`

---

## Phase 1: Pre-flight Checks

Run these 7 checks. Report each as PASS/FAIL.

1. **Samples exist**: `ls 04-all_samples/*.1.fq.gz | wc -l` → EXPECTED_SAMPLES. `ls 04-all_samples/*.2.fq.gz | wc -l` — must match
   - FAIL → **stop**: "Step 3 not completed. Run `/gbs-3-rename` first."

2. **Genome exists**: `test -f 08-genome/genome.fasta && echo OK`
   - FAIL → **stop**: "Genome not found at 08-genome/genome.fasta. Please provide the reference genome file."

3. **BWA index exists**: `test -f 08-genome/genome.fasta.bwt && echo OK`
   - FAIL → proceed to **Phase 2A: Build BWA Index**

4. **Samtools index exists**: `test -f 08-genome/genome.fasta.fai && echo OK`
   - FAIL → **self-heal**: `samtools faidx 08-genome/genome.fasta` (fast, seconds)

5. **BWA installed**: `which bwa`
   - FAIL → **stop**: "bwa not found."

6. **samtools installed**: `which samtools`
   - FAIL → **stop**: "samtools not found."

7. **GNU parallel installed**: `which parallel`
   - FAIL → **stop**: "GNU parallel required."

If BWA index exists (check 3 passed), skip Phase 2A and go directly to Phase 2B.

---

## Phase 2A: Build BWA Index (if missing)

Launch the index build and monitor with adaptive polling:

```bash
nohup bwa index 08-genome/genome.fasta > 10-log_files/bwa_index.log 2>&1 &
```

Report: "BWA index building... will monitor until complete."

### Adaptive polling for index build

Poll by checking if `08-genome/genome.fasta.bwt` exists AND if the `bwa index` process is still running.

**Schedule:**
```
Poll 1:  sleep 120  (2 min)   → check
Poll 2:  sleep 300  (5 min)   → check
Poll 3:  sleep 600  (10 min)  → check
Poll 4:  sleep 1200 (20 min)  → check
Poll 5+: sleep 1800 (30 min)  → check (cap here)
```

**Each poll runs:**
```bash
test -f 08-genome/genome.fasta.bwt && echo "INDEX_DONE" || echo "INDEX_BUILDING"
pgrep -f 'bwa index' > /dev/null && echo "PROCESS_ALIVE" || echo "PROCESS_DEAD"
```

**Exit conditions:**
- `INDEX_DONE` → report success, proceed to Phase 2B
- `PROCESS_DEAD` + `INDEX_NOT_DONE` → **FAILURE** — report error from `10-log_files/bwa_index.log`
- Total wall time > 4 hours → **FAILURE** — report timeout

**IMPORTANT**: Use `Bash(command="sleep N", timeout=<N*1000 + 10000>)` for each sleep. Set timeout slightly above the sleep duration so it doesn't get killed early.

---

## Phase 2B: Launch Alignment + Monitor

### Launch

```bash
nohup bash -c '
ls 04-all_samples/*.1.fq.gz | parallel -j 12 '\''
  base=$(basename {} .1.fq.gz)
  bwa mem -t 8 -R "@RG\tID:${base}\tSM:${base}\tPL:Illumina" \
    08-genome/genome.fasta {} 04-all_samples/${base}.2.fq.gz 2>/dev/null |
    samtools view -Sb -q 10 - > 04-all_samples/${base}.bam &&
  samtools sort --threads 8 -o 04-all_samples/${base}.sorted.bam \
    04-all_samples/${base}.bam &&
  samtools index 04-all_samples/${base}.sorted.bam &&
  rm 04-all_samples/${base}.bam
'\''
' > 10-log_files/bwa_alignment.log 2>&1 &
```

Report: "Alignment launched for EXPECTED_SAMPLES samples. Monitoring progress..."

### Adaptive polling for alignment

Poll by counting `04-all_samples/*.sorted.bam` files.

**Strategy**: Estimate rate from early polls, then calculate optimal intervals.

**Initial polls (rate discovery):**
```
Poll 1: sleep 120  (2 min)  → count BAMs → PREV=0, NOW=count1
Poll 2: sleep 600  (10 min) → count BAMs → NOW=count2, rate = (count2-count1)/10 samples/min
```

**Subsequent polls (adaptive):**

After rate is established, calculate next interval:

```
remaining = EXPECTED_SAMPLES - completed
est_minutes_left = remaining / rate
next_sleep = est_minutes_left / 5       # check ~5 more times
next_sleep = max(next_sleep, 5)          # floor: 5 min minimum
next_sleep = min(next_sleep, 60)         # cap: 60 min maximum
```

This naturally creates the curve:
- Early (few done, many left): long intervals (up to 60 min)
- Middle: medium intervals
- Late (almost done): short intervals (down to 5 min)

**Each poll runs:**
```bash
ls 04-all_samples/*.sorted.bam 2>/dev/null | wc -l
```

Report progress each poll: `"Progress: X / EXPECTED (Y%) — next check in Z min"`

**Exit conditions:**
- `completed == EXPECTED_SAMPLES` → proceed to Phase 3
- 3 consecutive polls with zero new BAMs AND process dead (`pgrep -f 'parallel.*bwa' | wc -l` = 0) → go to **Stall Recovery**
- Total wall time > 24 hours → **FAILURE** — report timeout

**IMPORTANT**: Use `Bash(command="sleep N", timeout=<N*1000 + 10000>)` for each sleep.

### Stall Recovery

If alignment stalled (process dead, BAMs incomplete):

```bash
comm -23 \
  <(ls 04-all_samples/*.1.fq.gz | xargs -I{} basename {} .1.fq.gz | sort) \
  <(ls 04-all_samples/*.sorted.bam 2>/dev/null | xargs -I{} basename {} .sorted.bam | sort) \
  > /tmp/missing_samples.txt
MISSING=$(wc -l < /tmp/missing_samples.txt)
```

If MISSING > 0, re-launch for missing samples only:

```bash
nohup bash -c '
cat /tmp/missing_samples.txt | parallel -j 12 '\''
  base={}
  bwa mem -t 8 -R "@RG\tID:${base}\tSM:${base}\tPL:Illumina" \
    08-genome/genome.fasta 04-all_samples/${base}.1.fq.gz 04-all_samples/${base}.2.fq.gz 2>/dev/null |
    samtools view -Sb -q 10 - > 04-all_samples/${base}.bam &&
  samtools sort --threads 8 -o 04-all_samples/${base}.sorted.bam \
    04-all_samples/${base}.bam &&
  samtools index 04-all_samples/${base}.sorted.bam &&
  rm 04-all_samples/${base}.bam
'\''
' >> 10-log_files/bwa_alignment.log 2>&1 &
```

Report: "Resumed MISSING missing samples." Then continue adaptive polling. Only attempt recovery **once**. If it stalls again, report FAILURE.

---

## Phase 3: Verification + QC

All sorted BAMs are present. Run these 5 checks:

1. **Sorted BAM count**: `ls 04-all_samples/*.sorted.bam | wc -l` — must equal EXPECTED_SAMPLES
2. **BAM index count**: `ls 04-all_samples/*.sorted.bam.bai | wc -l` — must equal EXPECTED_SAMPLES
3. **No empty BAMs**: `find 04-all_samples/ -name '*.sorted.bam' -empty | wc -l` — must be 0
4. **No unsorted BAMs left**: `ls 04-all_samples/*.bam 2>/dev/null | grep -v sorted | wc -l` — must be 0
5. **Alignment QC (benchmark)**: Run `samtools flagstat` and `bamtools stats` on 5 random sorted BAMs:
   ```
   for bam in $(ls 04-all_samples/*.sorted.bam | shuf | head -5); do
     echo "=== $(basename $bam) ==="
     samtools flagstat "$bam"
     echo "---"
     bamtools stats -in "$bam"
     echo ""
   done
   ```
   For each sample, extract and report:
   - Total reads, mapped %, properly paired %, singletons %
   - **PDF benchmarks**: ~100% mapped, 95.6% properly paired, 0.49% singletons
   - Flag any sample with <90% mapped or <85% properly paired as **WARNING**

---

## Output

End your response with this exact structured summary:

```
## Step 5 Summary
- **Step**: 5 — BWA Alignment
- **Status**: SUCCESS | FAILURE
- **Sorted BAM files**: <number> / <expected> expected
- **BAM index files**: <number>
- **Parallel config**: 12 jobs × 8 threads (96 CPUs)
- **Index build time**: <duration or skipped>
- **Alignment time**: <duration>
- **Total polls**: <number>
- **Stall recovery**: Yes (description) | No
- **Issues**: <none | description>

## Alignment QC (benchmark comparison)
PDF reference: ~100% mapped, 95.6% properly paired, 0.49% singletons
| Sample | Total reads | Mapped % | Properly paired % | Singletons % | Status |
|--------|-------------|----------|-------------------|---------------|--------|
| <name> | <n>         | <x>%     | <y>%              | <z>%          | OK/WARN|
| ...    | ...         | ...      | ...               | ...           | ...    |
```
