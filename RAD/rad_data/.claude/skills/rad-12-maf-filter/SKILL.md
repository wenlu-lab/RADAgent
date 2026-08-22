---
name: rad-12-maf-filter
description: Run RAD pipeline Step 12 (MAF 0.1 filter) on the server
context: fork
model: sonnet
allowed-tools: Bash, Read, Grep, Glob
---

# RAD Pipeline — Step 12: MAF 0.1 Filter

You are running RAD pipeline Step 12 directly on the server. All paths are relative to the project root (`rad_data/`).

**What this step does**: Applies a stricter minor allele frequency filter (MAF ≥ 0.1 / 10%) to remove rare variants. Only keeps SNPs where the minor allele appears in at least 10% of individuals.

**Input**: `filtered_m4_p80_x0_S1_chr.singleton.hwe.maf01.LD.no_AT_CG.vcf`
**Output**: `filtered_m4_p80_x0_S1_chr.singleton.hwe.maf10.LD.no_AT_CG.recode.vcf`

**CRITICAL RULE**: Check exit code after execution. If non-zero → self-heal ONCE. If still failing → report FAILURE and **STOP**.

---

## Phase 1: Pre-flight Checks

Run these 3 checks. Report each as PASS/FAIL.

1. **Input VCF exists**: `test -f filtered_m4_p80_x0_S1_chr.singleton.hwe.maf01.LD.no_AT_CG.vcf && echo OK`. Count SNPs: `grep -cv '^#' filtered_m4_p80_x0_S1_chr.singleton.hwe.maf01.LD.no_AT_CG.vcf` → INPUT_SNPS
   - FAIL → **stop**: "Step 11 not completed. Run `/rad-11-remove-atgc` first."

2. **vcftools installed**: `which vcftools`
   - FAIL → **stop**: "vcftools not found."

3. **Stale output**: `ls filtered_m4_p80_x0_S1_chr.singleton.hwe.maf10.LD.no_AT_CG* 2>/dev/null | wc -l`
   - If > 0 → **self-heal**: `rm -f filtered_m4_p80_x0_S1_chr.singleton.hwe.maf10.LD.no_AT_CG*`

If all pass, proceed to Phase 2.

---

## Phase 2: Execution

```bash
vcftools --vcf filtered_m4_p80_x0_S1_chr.singleton.hwe.maf01.LD.no_AT_CG.vcf \
  --maf 0.1 --recode \
  --out filtered_m4_p80_x0_S1_chr.singleton.hwe.maf10.LD.no_AT_CG
```

Fast (seconds). Capture stdout — it reports individuals and sites kept.

Check exit code. If non-zero → report FAILURE and **STOP**.

---

## Phase 3: Verification

Run these 2 checks:

1. **Output VCF exists + has content**:
   ```bash
   test -f filtered_m4_p80_x0_S1_chr.singleton.hwe.maf10.LD.no_AT_CG.recode.vcf && echo EXISTS
   grep -cv '^#' filtered_m4_p80_x0_S1_chr.singleton.hwe.maf10.LD.no_AT_CG.recode.vcf
   ```
   Must be > 0.

2. **Individuals kept**:
   ```bash
   grep '^#CHROM' filtered_m4_p80_x0_S1_chr.singleton.hwe.maf10.LD.no_AT_CG.recode.vcf | awk '{print NF-9}'
   ```
   Must equal expected sample count.

If ANY check fails → report FAILURE and **STOP**.

### Error Diagnosis

| Symptom | Fix |
|---------|-----|
| vcftools error | Check input VCF format: `head -1 input.vcf`. Report error |
| 0 sites kept | MAF 0.1 too strict for this dataset — report as WARNING |

---

## Output

End your response with this exact structured summary:

```
## Step 12 Summary
- **Step**: 12 — MAF 0.1 Filter
- **Status**: SUCCESS | FAILURE
- **Input SNPs**: <number>
- **After MAF 0.1 filter**: <number>
- **Individuals kept**: <number>
- **Issues**: <none | description>
- **Self-healing attempted**: Yes (description) | No

## Benchmark Comparison
| Metric | This run | PDF reference |
|--------|----------|---------------|
| Input SNPs | <n> | 4,471 |
| After MAF 0.1 | <n> | 2,059 |
| Individuals | <n> | 476 |
```
