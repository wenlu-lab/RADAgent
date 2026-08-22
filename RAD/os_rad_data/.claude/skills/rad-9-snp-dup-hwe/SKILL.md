---
name: rad-9-snp-dup-hwe
description: Run RAD pipeline Step 9 (SNP duplication detection + HWE filtering) on the server
context: fork
model: sonnet
allowed-tools: Bash, Read, Grep, Glob
---

# RAD Pipeline — Step 9: SNP Duplication Detection + HWE Filtering

You are running RAD pipeline Step 9 directly on the server. All paths are relative to the project root (`rad_data/`).

**What this step does**: Detects and removes duplicated/low-confidence SNPs based on allelic ratios and heterozygosity, then applies Hardy-Weinberg equilibrium filtering on the "singleton" (good) SNPs. 4 sub-steps, all fast — no background/polling needed.

**Input**: `filtered_m4_p80_x0_S1_chr.recode.vcf` (from Step 8)
**Output**: `filtered_m4_p80_x0_S1_chr.singleton.hwe.recode.vcf` (HWE-filtered singletons)

---

## Phase 1: Pre-flight Checks

Run these 6 checks. Report each as PASS/FAIL.

1. **Input VCF exists**: `test -f filtered_m4_p80_x0_S1_chr.recode.vcf && echo OK`. Count SNPs: `grep -cv '^#' filtered_m4_p80_x0_S1_chr.recode.vcf` → INPUT_SNPS
   - FAIL → **stop**: "Step 8 not completed. Run `/rad-8-vcf-filter` first."

2. **Scripts exist**: Check all 4:
   ```bash
   test -f 00-scripts/08_extract_snp_duplication_info.py && echo "08 OK"
   test -f 00-scripts/09_classify_snps.R && echo "09 OK"
   test -f 00-scripts/10_split_vcf_in_categories.py && echo "10 OK"
   test -f filter_hwe_by_pop.pl && echo "HWE OK"
   ```
   - FAIL → **stop**: report which script is missing

3. **Tools installed**:
   ```bash
   which python3 && which Rscript && which perl && which vcftools && echo "ALL OK"
   ```
   - FAIL → **stop**: report which tool is missing

4. **Population map exists**: `test -f 01-info_files/population_map.txt && echo OK`
   - FAIL → **stop**: "Population map missing. Run `/rad-4-popmap` first."

5. **filter_hwe_by_pop.pl in project root**: The HWE script is at `filter_hwe_by_pop.pl` (project root, not 00-scripts/)
   - If missing from root, check: `find . -name "filter_hwe_by_pop.pl" -maxdepth 2`

6. **Stale output**: Check for existing intermediate files:
   ```bash
   ls snp_duplication_info.txt* filtered_m4_p80_x0_S1_chr.recode.*.vcf.out filtered_m4_p80_x0_S1_chr.singleton.hwe* 2>/dev/null | wc -l
   ```
   - If > 0 → **self-heal**: `rm -f snp_duplication_info.txt* filtered_m4_p80_x0_S1_chr.recode.*.vcf.out filtered_m4_p80_x0_S1_chr.singleton.hwe* exclude.hwe filtered.hwe *.inds *.hwe 2>/dev/null`

If all pass, proceed to Phase 2.

---

## Phase 2: Execution (4 sub-steps, sequential)

### Sub-step 1: Extract SNP duplication info

```bash
python3 00-scripts/08_extract_snp_duplication_info.py \
  filtered_m4_p80_x0_S1_chr.recode.vcf snp_duplication_info.txt
```

Check exit code. Verify: `wc -l < snp_duplication_info.txt` — should be close to INPUT_SNPS + 1 (header).

Report: "Extracted duplication metrics for X SNPs."

### Sub-step 2: Classify SNPs

```bash
Rscript 00-scripts/09_classify_snps.R snp_duplication_info.txt
```

Check exit code. Verify: `test -f snp_duplication_info.txt.categorized && echo OK`

Report category distribution:
```bash
cut -f4 snp_duplication_info.txt.categorized | sort | uniq -c | sort -rn
```

### Sub-step 3: Split VCF by category

```bash
python3 00-scripts/10_split_vcf_in_categories.py \
  filtered_m4_p80_x0_S1_chr.recode.vcf snp_duplication_info.txt.categorized
```

Check exit code. Verify singleton VCF exists:
```bash
test -f filtered_m4_p80_x0_S1_chr.recode.singleton.vcf.out && echo OK
grep -cv '^#' filtered_m4_p80_x0_S1_chr.recode.singleton.vcf.out
```

Report: "Singleton VCF has X SNPs."

### Sub-step 4: HWE filtering

```bash
perl filter_hwe_by_pop.pl \
  -v filtered_m4_p80_x0_S1_chr.recode.singleton.vcf.out \
  -p 01-info_files/population_map.txt \
  -h 0.001 -c 0.5 \
  -o filtered_m4_p80_x0_S1_chr.singleton.hwe
```

Check exit code. Report HWE output from stdout (processing populations, loci kept/filtered).

---

## Phase 3: Verification

Run these 5 checks:

1. **snp_duplication_info.txt**: `test -f snp_duplication_info.txt && wc -l < snp_duplication_info.txt`

2. **Categorized file**: `test -f snp_duplication_info.txt.categorized && wc -l < snp_duplication_info.txt.categorized`

3. **Singleton VCF**: `test -f filtered_m4_p80_x0_S1_chr.recode.singleton.vcf.out`. Count SNPs: `grep -cv '^#' filtered_m4_p80_x0_S1_chr.recode.singleton.vcf.out`

4. **HWE output**: `test -f filtered_m4_p80_x0_S1_chr.singleton.hwe.recode.vcf`. Count SNPs: `grep -cv '^#' filtered_m4_p80_x0_S1_chr.singleton.hwe.recode.vcf`

5. **Category distribution**: Full breakdown:
   ```bash
   cut -f4 snp_duplication_info.txt.categorized | sort | uniq -c | sort -rn
   ```

If all pass, report SUCCESS.

### Error Diagnosis

| Symptom | Fix |
|---------|-----|
| Permission denied | `chmod +x` on the failing script, retry |
| R package missing | `Rscript -e "install.packages('...', repos='https://cran.r-project.org')"` |
| Perl module missing | Report as UNFIXABLE — needs system admin |
| 0 singletons | Classification too aggressive — report category breakdown |
| HWE `-p` flag error | Script uses `-p` not `-P` for popmap. Check: `perl filter_hwe_by_pop.pl --help` |

---

## Output

End your response with this exact structured summary:

```
## Step 9 Summary
- **Step**: 9 — SNP Duplication Detection + HWE Filtering
- **Status**: SUCCESS | FAILURE
- **Input SNPs**: <number>
- **SNP Categories**:
  - singleton: <n>
  - duplicated: <n>
  - diverged: <n>
  - lowconf: <n>
  - highcov: <n>
  - mas: <n>
- **Singleton SNPs**: <number>
- **After HWE filter**: <kept> kept / <filtered> filtered
- **Issues**: <none | description>
- **Self-healing attempted**: Yes (description) | No

## Benchmark Comparison
| Metric | This run | PDF reference |
|--------|----------|---------------|
| Singleton SNPs | <n> | ~13,549 |
| HWE loci kept | <n> | 13,549 |
| HWE loci filtered | <n> | 0 |
```
