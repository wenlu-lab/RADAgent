---
name: gbs-10-ld-clump
description: Run GBS pipeline Step 10 (LD clumping) on the server
context: fork
model: sonnet
allowed-tools: Bash, Read, Grep, Glob
---

# GBS Pipeline — Step 10: LD Clumping

You are running GBS pipeline Step 10 directly on the server. All paths are relative to the project root (`gbs_data/`).

**What this step does**: Reduces linkage disequilibrium by removing SNP pairs with r² ≥ 0.2. Requires converting chromosome names to numbers (PLINK/bigsnpr requirement), running LD pruning in R, then restoring original NC_ names. 6 sub-steps, mostly fast except the R LD clumping (~minutes).

**Input**: `filtered_m4_p80_x0_S1_chr.singleton.hwe.recode.vcf`
**Output**: `filtered_m4_p80_x0_S1_chr.singleton.hwe.maf01.LD.recode.vcf` (LD-pruned VCF), `LD_regions.txt`

**CRITICAL RULE**: After every sub-step, check the exit code. If non-zero → attempt self-heal ONCE (see Error Diagnosis table). If self-heal fails → report FAILURE and **STOP immediately**. Do NOT proceed to the next sub-step.

---

## Phase 1: Pre-flight Checks

Run these 5 checks. Report each as PASS/FAIL.

1. **Input VCF exists**: `test -f filtered_m4_p80_x0_S1_chr.singleton.hwe.recode.vcf && echo OK`. Count SNPs: `grep -cv '^#' filtered_m4_p80_x0_S1_chr.singleton.hwe.recode.vcf` → INPUT_SNPS
   - FAIL → **stop**: "Step 9 not completed. Run `/gbs-9-snp-dup-hwe` first."

2. **Tools installed**:
   ```bash
   which vcftools && which plink && which Rscript && echo "ALL OK"
   ```
   - FAIL → **stop**: report which tool is missing

3. **bigsnpr R package**:
   ```bash
   Rscript -e "library(bigsnpr); cat('bigsnpr OK\n')" 2>&1
   ```
   - FAIL → **stop**: "R bigsnpr package not installed."

4. **Stale output**: Remove existing intermediates:
   ```bash
   rm -f filtered_m4_p80_x0_S1_chr.singleton.hwe.maf01* ld_clump.R 2>/dev/null
   ```

5. **Disk space**: `df -h . | tail -1` — verify > 10 GB free

If all pass, proceed to Phase 2.

---

## Phase 2: Execution (6 sub-steps, sequential)

### Sub-step 1: MAF filter (0.01)

```bash
vcftools --vcf filtered_m4_p80_x0_S1_chr.singleton.hwe.recode.vcf \
  --maf 0.01 --recode --out filtered_m4_p80_x0_S1_chr.singleton.hwe.maf01
```

Report sites kept from vcftools output.

### Sub-step 2: Rename chromosomes NC_ → numbers

```bash
for i in filtered_m4_p80_x0_S1_chr.singleton.hwe.maf01.recode.vcf; do
  sed -i.bak \
    -e 's/NC_091150.1/1/g' -e 's/NC_091151.1/2/g' -e 's/NC_091152.1/3/g' \
    -e 's/NC_091153.1/4/g' -e 's/NC_091154.1/5/g' -e 's/NC_091155.1/6/g' \
    -e 's/NC_091156.1/7/g' -e 's/NC_091157.1/8/g' -e 's/NC_091158.1/9/g' \
    -e 's/NC_091159.1/10/g' -e 's/NC_091160.1/11/g' -e 's/NC_091161.1/12/g' \
    -e 's/NC_091162.1/13/g' -e 's/NC_091163.1/14/g' -e 's/NC_091164.1/15/g' \
    -e 's/NC_091165.1/16/g' -e 's/NC_091166.1/17/g' -e 's/NC_091167.1/18/g' \
    -e 's/NC_091168.1/19/g' -e 's/NC_091169.1/20/g' -e 's/NC_091170.1/21/g' \
    -e 's/NC_091171.1/22/g' -e 's/NC_091172.1/23/g' -e 's/NC_091173.1/24/g' \
    -e 's/NC_091174.1/25/g' -e 's/NC_091175.1/26/g' -e 's/NC_091176.1/27/g' \
    -e 's/NC_091177.1/28/g' -e 's/NC_091178.1/29/g' -e 's/NC_091179.1/30/g' \
    -e 's/NC_091180.1/31/g' -e 's/NC_091181.1/32/g' -e 's/NC_091182.1/33/g' \
    -e 's/NC_091183.1/34/g' -e 's/NC_091184.1/35/g' -e 's/NC_091185.1/36/g' \
    -e 's/NC_091186.1/37/g' -e 's/NC_091187.1/38/g' -e 's/NC_091188.1/39/g' \
    -e 's/NC_091189.1/40/g' -e 's/NC_091190.1/41/g' -e 's/NC_091191.1/42/g' \
    -e 's/NC_091192.1/43/g' -e 's/NC_091193.1/44/g' -e 's/NC_091194.1/45/g' \
    -e 's/NC_091195.1/46/g' -e 's/NC_091196.1/47/g' -e 's/NC_091197.1/48/g' \
    -e 's/NC_091198.1/49/g' -e 's/NC_091199.1/50/g' -e 's/NC_091200.1/51/g' \
    -e 's/NC_091201.1/52/g' -e 's/NC_091202.1/53/g' -e 's/NC_091203.1/54/g' \
    -e 's/NC_091204.1/55/g' -e 's/NC_091205.1/56/g' -e 's/NC_091206.1/57/g' \
    -e 's/NC_091207.1/58/g' -e 's/NC_091208.1/59/g' -e 's/NC_091209.1/60/g' \
    -e 's/NC_091210.1/61/g' -e 's/NC_091211.1/62/g' -e 's/NC_091212.1/63/g' \
    -e 's/NC_091213.1/64/g' -e 's/NC_091214.1/65/g' -e 's/NC_091215.1/66/g' \
    -e 's/NC_091216.1/67/g' -e 's/NC_091217.1/68/g' -e 's/NC_091218.1/69/g' \
    -e 's/NC_091219.1/70/g' -e 's/NC_091220.1/71/g' -e 's/NC_091221.1/72/g' \
    -e 's/NC_091222.1/73/g' -e 's/NC_091223.1/74/g' -e 's/NC_091224.1/75/g' \
    -e 's/NC_091225.1/76/g' -e 's/NC_091226.1/77/g' -e 's/NC_091227.1/78/g' \
    -e 's/NC_091228.1/79/g' -e 's/NC_091229.1/80/g' -e 's/NC_091230.1/81/g' \
    -e 's/NC_091231.1/82/g' -e 's/NC_091232.1/83/g' -e 's/NC_091233.1/84/g' \
    -e 's/NC_091234.1/85/g' -e 's/NC_091235.1/86/g' -e 's/NC_091236.1/87/g' \
    -e 's/NC_091237.1/88/g' -e 's/NC_091238.1/89/g' -e 's/NC_091239.1/90/g' \
    -e 's/NC_091240.1/91/g' -e 's/NC_091241.1/92/g' -e 's/NC_091242.1/93/g' \
    -e 's/NC_091243.1/94/g' \
    "$i"
done
```

Verify: `grep -v '^#' filtered_m4_p80_x0_S1_chr.singleton.hwe.maf01.recode.vcf | cut -f1 | sort -un | head -5` — should show numbers, not NC_.

### Sub-step 3: Convert to PLINK BED

```bash
plink --vcf filtered_m4_p80_x0_S1_chr.singleton.hwe.maf01.recode.vcf \
  --double-id --make-bed --recode \
  --out filtered_m4_p80_x0_S1_chr.singleton.hwe.maf01 --aec --chr-set 94
```

Verify: `.bed`, `.bim`, `.fam` files exist.

### Sub-step 4: LD clumping in R (bigsnpr)

Create the R script:

```bash
cat > ld_clump.R << 'REOF'
library(bigsnpr)

file_name <- "filtered_m4_p80_x0_S1_chr.singleton.hwe.maf01"

# Remove old backing file if exists
f_bk <- paste0(file_name, ".bk")
if (file.exists(f_bk)) file.remove(f_bk)

# Read PLINK BED
snp_readBed(paste0(file_name, ".bed"))

# Attach
obj.bigSNP <- snp_attach(paste0(file_name, ".rds"))
G <- obj.bigSNP$genotypes
SNPs <- obj.bigSNP$map$marker.ID
CHR <- obj.bigSNP$map$chromosome
POS <- obj.bigSNP$map$physical.pos

# Impute missing genotypes
G <- snp_fastImputeSimple(G, method = "mean0", ncores = 32)

# LD clumping with r2 = 0.2
newpc <- snp_autoSVD(G, infos.chr = CHR, infos.pos = POS,
                     thr.r2 = 0.2, size = 10, roll.size = 0)

# Extract kept SNPs
which_pruned <- attr(newpc, "subset")
keep_snp_ids <- SNPs[which_pruned]

# Write kept SNP IDs
write.table(keep_snp_ids,
            file = paste0(file_name, "_LDclump_SNP.txt"),
            sep = "\t", quote = FALSE, row.names = FALSE, col.names = FALSE)

cat(paste0("SNPs after clumping: ", length(keep_snp_ids),
           " out of ", nrow(obj.bigSNP$map), "\n"))
REOF
```

Run it:
```bash
Rscript ld_clump.R
```

Verify: `wc -l < filtered_m4_p80_x0_S1_chr.singleton.hwe.maf01_LDclump_SNP.txt`

### Sub-step 5: Reverse chromosome renaming on SNP IDs (conditional)

First check the SNP ID format: `head -1 filtered_m4_p80_x0_S1_chr.singleton.hwe.maf01_LDclump_SNP.txt`
- If IDs start with a number followed by `_` (e.g., `1_12345`): run the sed reverse rename
- If IDs are in `tag:pos:strand` format (e.g., `349:240:-`): **skip this sub-step** — the .bak VCF already has NC_ names. Log: "Skipped — SNP IDs not in chr_pos format, .bak extraction handles NC_ names."

If sed IS needed:
```bash
file="filtered_m4_p80_x0_S1_chr.singleton.hwe.maf01_LDclump_SNP.txt"
cp "$file" "${file}.bak"
sed -i '
s/^1_/NC_091150.1_/; s/^2_/NC_091151.1_/; s/^3_/NC_091152.1_/;
s/^4_/NC_091153.1_/; s/^5_/NC_091154.1_/; s/^6_/NC_091155.1_/;
s/^7_/NC_091156.1_/; s/^8_/NC_091157.1_/; s/^9_/NC_091158.1_/;
s/^10_/NC_091159.1_/; s/^11_/NC_091160.1_/; s/^12_/NC_091161.1_/;
s/^13_/NC_091162.1_/; s/^14_/NC_091163.1_/; s/^15_/NC_091164.1_/;
s/^16_/NC_091165.1_/; s/^17_/NC_091166.1_/; s/^18_/NC_091167.1_/;
s/^19_/NC_091168.1_/; s/^20_/NC_091169.1_/; s/^21_/NC_091170.1_/;
s/^22_/NC_091171.1_/; s/^23_/NC_091172.1_/; s/^24_/NC_091173.1_/;
s/^25_/NC_091174.1_/; s/^26_/NC_091175.1_/; s/^27_/NC_091176.1_/;
s/^28_/NC_091177.1_/; s/^29_/NC_091178.1_/; s/^30_/NC_091179.1_/;
s/^31_/NC_091180.1_/; s/^32_/NC_091181.1_/; s/^33_/NC_091182.1_/;
s/^34_/NC_091183.1_/; s/^35_/NC_091184.1_/; s/^36_/NC_091185.1_/;
s/^37_/NC_091186.1_/; s/^38_/NC_091187.1_/; s/^39_/NC_091188.1_/;
s/^40_/NC_091189.1_/; s/^41_/NC_091190.1_/; s/^42_/NC_091191.1_/;
s/^43_/NC_091192.1_/; s/^44_/NC_091193.1_/; s/^45_/NC_091194.1_/;
s/^46_/NC_091195.1_/; s/^47_/NC_091196.1_/; s/^48_/NC_091197.1_/;
s/^49_/NC_091198.1_/; s/^50_/NC_091199.1_/; s/^51_/NC_091200.1_/;
s/^52_/NC_091201.1_/; s/^53_/NC_091202.1_/; s/^54_/NC_091203.1_/;
s/^55_/NC_091204.1_/; s/^56_/NC_091205.1_/; s/^57_/NC_091206.1_/;
s/^58_/NC_091207.1_/; s/^59_/NC_091208.1_/; s/^60_/NC_091209.1_/;
s/^61_/NC_091210.1_/; s/^62_/NC_091211.1_/; s/^63_/NC_091212.1_/;
s/^64_/NC_091213.1_/; s/^65_/NC_091214.1_/; s/^66_/NC_091215.1_/;
s/^67_/NC_091216.1_/; s/^68_/NC_091217.1_/; s/^69_/NC_091218.1_/;
s/^70_/NC_091219.1_/; s/^71_/NC_091220.1_/; s/^72_/NC_091221.1_/;
s/^73_/NC_091222.1_/; s/^74_/NC_091223.1_/; s/^75_/NC_091224.1_/;
s/^76_/NC_091225.1_/; s/^77_/NC_091226.1_/; s/^78_/NC_091227.1_/;
s/^79_/NC_091228.1_/; s/^80_/NC_091229.1_/; s/^81_/NC_091230.1_/;
s/^82_/NC_091231.1_/; s/^83_/NC_091232.1_/; s/^84_/NC_091233.1_/;
s/^85_/NC_091234.1_/; s/^86_/NC_091235.1_/; s/^87_/NC_091236.1_/;
s/^88_/NC_091237.1_/; s/^89_/NC_091238.1_/; s/^90_/NC_091239.1_/;
s/^91_/NC_091240.1_/; s/^92_/NC_091241.1_/; s/^93_/NC_091242.1_/;
s/^94_/NC_091243.1_/;
' "$file"
```

Verify: `head -3 "$file"` — should show NC_ prefixes.

### Sub-step 6: Extract LD-pruned VCF

```bash
vcftools --vcf filtered_m4_p80_x0_S1_chr.singleton.hwe.maf01.recode.vcf.bak \
  --snps filtered_m4_p80_x0_S1_chr.singleton.hwe.maf01_LDclump_SNP.txt \
  --recode --out filtered_m4_p80_x0_S1_chr.singleton.hwe.maf01.LD
```

Report: individuals and sites kept.

### Sub-step 7: Create LD_regions.txt

```bash
sed 's/\(.*\)_\(.*\)/\1\t\2/' \
  filtered_m4_p80_x0_S1_chr.singleton.hwe.maf01_LDclump_SNP.txt > LD_regions.txt
```

Verify: `wc -l < LD_regions.txt` — must match LDclump_SNP.txt line count.

---

## Phase 3: Verification

Run these 5 checks:

1. **LDclump_SNP.txt exists**: `test -f filtered_m4_p80_x0_S1_chr.singleton.hwe.maf01_LDclump_SNP.txt && wc -l < filtered_m4_p80_x0_S1_chr.singleton.hwe.maf01_LDclump_SNP.txt`

2. **LD-pruned VCF exists**: `test -f filtered_m4_p80_x0_S1_chr.singleton.hwe.maf01.LD.recode.vcf && echo OK`. Count: `grep -cv '^#' filtered_m4_p80_x0_S1_chr.singleton.hwe.maf01.LD.recode.vcf`

3. **SNP IDs restored**: `head -3 filtered_m4_p80_x0_S1_chr.singleton.hwe.maf01_LDclump_SNP.txt` — must show NC_ prefixes

4. **Individuals in final VCF**: `grep '^#CHROM' filtered_m4_p80_x0_S1_chr.singleton.hwe.maf01.LD.recode.vcf | awk '{print NF-9}'`

5. **LD_regions.txt exists**: `test -f LD_regions.txt && wc -l < LD_regions.txt`

If ANY check fails → attempt self-heal from Error Diagnosis table ONCE. If still failing → report FAILURE and **STOP**.

### Error Diagnosis

| Symptom | Fix |
|---------|-----|
| bigsnpr not found | `Rscript -e "install.packages('bigsnpr')"` — needs admin |
| plink chr-set error | Check chr numbers in VCF after sed. May need `--allow-extra-chr` |
| R snp_autoSVD error | Check if BED files are valid: `plink --bfile ... --freq` |
| 0 SNPs after LD | r² threshold too strict — try 0.5 |
| sed didn't restore NC_ | Check SNP ID format in LDclump file before sed |

---

## Output

End your response with this exact structured summary:

```
## Step 10 Summary
- **Step**: 10 — LD Clumping
- **Status**: SUCCESS | FAILURE
- **Input SNPs (after HWE)**: <number>
- **After MAF 0.01 filter**: <number>
- **After LD clumping (r²<0.2)**: <number>
- **Final LD-pruned VCF sites**: <number>
- **Individuals kept**: <number>
- **Issues**: <none | description>
- **Self-healing attempted**: Yes (description) | No

## Benchmark Comparison
| Metric | This run | PDF reference |
|--------|----------|---------------|
| After MAF 0.01 | <n> | 10,160 |
| After LD clumping | <n> | 5,719 |
```
