---
name: rad-8-vcf-filter
description: Run RAD pipeline Step 8 (VCF filtering + chromosome selection) on the server
context: fork
model: sonnet
allowed-tools: Bash, Read, Grep, Glob
---

# RAD Pipeline — Step 8: VCF Filtering + Chromosome Selection

You are running RAD pipeline Step 8 directly on the server. All paths are relative to the project root (`rad_data/`).

**What this step does**: Filters the populations VCF on coverage/genotype rate/allele count, generates distribution graphs, converts to PLINK format, and filters to keep only named chromosomes (94 NC_ accessions). All fast commands — no background/polling needed.

**Input**: `05-stacks/populations.snps.vcf`
**Output**: `filtered_m4_p80_x0_S1.vcf`, `filtered_m4_p80_x0_S1_chr.recode.vcf`, PLINK files, graphs

---

## Phase 1: Pre-flight Checks

Run these 5 checks. Report each as PASS/FAIL.

1. **populations VCF exists**: `test -f 05-stacks/populations.snps.vcf && echo OK`
   - FAIL → **stop**: "Step 7 not completed. Run `/rad-7-populations` first."

2. **Filter script exists**: `test -f 00-scripts/05_filter_vcf_fast.py && echo OK`
   - FAIL → **stop**: "Filter script 05_filter_vcf_fast.py missing from 00-scripts/."

3. **Tools installed**: Check each:
   ```bash
   which python3 && which bcftools && which vcftools && echo "ALL OK"
   ```
   - FAIL → **stop**: report which tool is missing.

4. **Graph script exists**: `test -f 00-scripts/05_filter_vcf.py && echo OK`
   - FAIL → **skip graphs** sub-step (non-critical), continue with rest

5. **Stale output**: Check for existing output files:
   ```bash
   ls filtered_m4_p80_x0_S1*.vcf filtered_m4_p80_x0_S1*.ped filtered_m4_p80_x0_S1*.map filtered_m4_p80_x0_S1*.chrom-map.txt 2>/dev/null | wc -l
   ```
   - If > 0 → **self-heal**: `rm -f filtered_m4_p80_x0_S1* graphs_filtered_m4_p80_x0_S1* 2>/dev/null`

If all critical checks pass, proceed to Phase 2.

---

## Phase 2: Execution (4 sub-steps, sequential)

### Sub-step 1: Basic SNP filtering

```bash
python3 00-scripts/05_filter_vcf_fast.py 05-stacks/populations.snps.vcf 4 80 0 1 filtered_m4_p80_x0_S1.vcf
```

Parameters: min_cov=4, percent_genotypes=80, max_pop_fail=0, min_mas=1.

Check exit code. If non-zero, report error and **stop**.

Report: count variants in output: `grep -cv '^#' filtered_m4_p80_x0_S1.vcf`

### Sub-step 2: Distribution graphs (optional)

Only run if `00-scripts/05_filter_vcf.py` exists (check 4 passed):

```bash
python3 00-scripts/05_filter_vcf.py -i filtered_m4_p80_x0_S1.vcf -o graphs_filtered_m4_p80_x0_S1 -g
```

If this fails, report as WARNING but continue — graphs are non-critical QC.

### Sub-step 3: PLINK conversion

```bash
bcftools view -H filtered_m4_p80_x0_S1.vcf | cut -f 1 | uniq | awk '{print $0"\t"$0}' > filtered_m4_p80_x0_S1.chrom-map.txt
```

```bash
vcftools --vcf filtered_m4_p80_x0_S1.vcf --plink --chrom-map filtered_m4_p80_x0_S1.chrom-map.txt --out filtered_m4_p80_x0_S1
```

Check exit codes. Report any errors.

### Sub-step 4: Chromosome filtering (keep 94 chromosomes)

```bash
vcftools --vcf filtered_m4_p80_x0_S1.vcf \
  --chr NC_091150.1 --chr NC_091151.1 --chr NC_091152.1 --chr NC_091153.1 \
  --chr NC_091154.1 --chr NC_091155.1 --chr NC_091156.1 --chr NC_091157.1 \
  --chr NC_091158.1 --chr NC_091159.1 --chr NC_091160.1 --chr NC_091161.1 \
  --chr NC_091162.1 --chr NC_091163.1 --chr NC_091164.1 --chr NC_091165.1 \
  --chr NC_091166.1 --chr NC_091167.1 --chr NC_091168.1 --chr NC_091169.1 \
  --chr NC_091170.1 --chr NC_091171.1 --chr NC_091172.1 --chr NC_091173.1 \
  --chr NC_091174.1 --chr NC_091175.1 --chr NC_091176.1 --chr NC_091177.1 \
  --chr NC_091178.1 --chr NC_091179.1 --chr NC_091180.1 --chr NC_091181.1 \
  --chr NC_091182.1 --chr NC_091183.1 --chr NC_091184.1 --chr NC_091185.1 \
  --chr NC_091186.1 --chr NC_091187.1 --chr NC_091188.1 --chr NC_091189.1 \
  --chr NC_091190.1 --chr NC_091191.1 --chr NC_091192.1 --chr NC_091193.1 \
  --chr NC_091194.1 --chr NC_091195.1 --chr NC_091196.1 --chr NC_091197.1 \
  --chr NC_091198.1 --chr NC_091199.1 --chr NC_091200.1 --chr NC_091201.1 \
  --chr NC_091202.1 --chr NC_091203.1 --chr NC_091204.1 --chr NC_091205.1 \
  --chr NC_091206.1 --chr NC_091207.1 --chr NC_091208.1 --chr NC_091209.1 \
  --chr NC_091210.1 --chr NC_091211.1 --chr NC_091212.1 --chr NC_091213.1 \
  --chr NC_091214.1 --chr NC_091215.1 --chr NC_091216.1 --chr NC_091217.1 \
  --chr NC_091218.1 --chr NC_091219.1 --chr NC_091220.1 --chr NC_091221.1 \
  --chr NC_091222.1 --chr NC_091223.1 --chr NC_091224.1 --chr NC_091225.1 \
  --chr NC_091226.1 --chr NC_091227.1 --chr NC_091228.1 --chr NC_091229.1 \
  --chr NC_091230.1 --chr NC_091231.1 --chr NC_091232.1 --chr NC_091233.1 \
  --chr NC_091234.1 --chr NC_091235.1 --chr NC_091236.1 --chr NC_091237.1 \
  --chr NC_091238.1 --chr NC_091239.1 --chr NC_091240.1 --chr NC_091241.1 \
  --chr NC_091242.1 --chr NC_091243.1 \
  --recode --out filtered_m4_p80_x0_S1_chr
```

Report: individuals kept, sites kept (from vcftools stdout).

---

## Phase 3: Verification

Run these 5 checks:

1. **Filtered VCF exists + has content**:
   ```bash
   test -f filtered_m4_p80_x0_S1.vcf && echo EXISTS
   grep -cv '^#' filtered_m4_p80_x0_S1.vcf
   ```

2. **Chrom-map exists**: `test -f filtered_m4_p80_x0_S1.chrom-map.txt && wc -l < filtered_m4_p80_x0_S1.chrom-map.txt`

3. **PLINK files exist**: `test -f filtered_m4_p80_x0_S1.ped && test -f filtered_m4_p80_x0_S1.map && echo OK`

4. **Chromosome-filtered VCF exists + content**:
   ```bash
   test -f filtered_m4_p80_x0_S1_chr.recode.vcf && echo EXISTS
   grep -cv '^#' filtered_m4_p80_x0_S1_chr.recode.vcf
   ```

5. **Sample count in chr-filtered VCF**: Extract from header:
   ```bash
   grep '^#CHROM' filtered_m4_p80_x0_S1_chr.recode.vcf | awk '{print NF-9}'
   ```
   Must match expected sample count.

If all pass, report SUCCESS.

### Error Diagnosis

| Symptom | Fix |
|---------|-----|
| Permission denied | `chmod +x 00-scripts/05_filter_vcf_fast.py 00-scripts/05_filter_vcf.py`, retry |
| python3 import error | Check: `python3 -c "import sys; print(sys.version)"`. Report missing modules |
| 0 sites after filter | Filters too strict — report and suggest adjusting parameters |
| vcftools error | Check vcftools stderr output. Report details |

---

## Output

End your response with this exact structured summary:

```
## Step 8 Summary
- **Step**: 8 — VCF Filtering + Chromosome Selection
- **Status**: SUCCESS | FAILURE
- **Input SNPs**: <from populations VCF>
- **After basic filter**: <number> sites
- **After chr filter**: <number> sites
- **Individuals kept**: <number>
- **Chromosomes kept**: 94
- **PLINK files**: Yes | No
- **Graphs generated**: Yes | No | Skipped
- **Issues**: <none | description>
- **Self-healing attempted**: Yes (description) | No

## Benchmark Comparison
| Metric | This run | PDF reference |
|--------|----------|---------------|
| Sites after basic filter | <n> | ~64,738 |
| Sites after chr filter | <n> | 64,655 |
| Individuals | <n> | 476 |
```
