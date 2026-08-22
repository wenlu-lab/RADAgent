---
name: rad-11-remove-atgc
description: Run RAD pipeline Step 11 (remove A/T and G/C SNPs) on the server
context: fork
model: sonnet
allowed-tools: Bash, Read, Grep, Glob
---

# RAD Pipeline — Step 11: Remove A/T and G/C SNPs

You are running RAD pipeline Step 11 directly on the server. All paths are relative to the project root (`rad_data/`).

**What this step does**: Removes SNPs where REF/ALT alleles are complementary pairs (A/T, T/A, C/G, G/C). These strand-ambiguous SNPs cause problems during genotyping assays because they can't be distinguished between forward and reverse strands.

**Input**: `filtered_m4_p80_x0_S1_chr.singleton.hwe.maf01.LD.recode.vcf`
**Output**: `filtered_m4_p80_x0_S1_chr.singleton.hwe.maf01.LD.no_AT_CG.vcf`

**CRITICAL RULE**: After every sub-step, check exit code. If non-zero → attempt self-heal ONCE. If still failing → report FAILURE and **STOP immediately**.

---

## Phase 1: Pre-flight Checks

Run these 4 checks. Report each as PASS/FAIL.

1. **Input VCF exists**: `test -f filtered_m4_p80_x0_S1_chr.singleton.hwe.maf01.LD.recode.vcf && echo OK`. Count SNPs: `grep -cv '^#' filtered_m4_p80_x0_S1_chr.singleton.hwe.maf01.LD.recode.vcf` → INPUT_SNPS
   - FAIL → **stop**: "Step 10 not completed. Run `/rad-10-ld-clump` first."

2. **python3 installed**: `which python3`
   - FAIL → **stop**: "python3 not found."

3. **Create AT_CG.py if missing**: Check `test -f AT_CG.py`. If missing, create it:
   ```bash
   cat > AT_CG.py << 'PYEOF'
   input_file_path = 'filtered_m4_p80_x0_S1_chr.singleton.hwe.maf01.LD.recode.vcf'
   output_file_path = 'filtered_m4_p80_x0_S1_chr.singleton.hwe.maf01.LD.no_AT_CG.vcf'

   exclude_alleles = {'A/T', 'T/A', 'C/G', 'G/C'}
   excluded_snps_count = 0
   total_snps_count = 0
   excluded_snps_info = []

   with open(input_file_path, 'r') as input_file, open(output_file_path, 'w') as output_file:
       for line in input_file:
           if line.startswith('#'):
               output_file.write(line)
           else:
               total_snps_count += 1
               columns = line.split('\t')
               ref_allele = columns[3]
               alt_allele = columns[4]
               allele_pair = f'{ref_allele}/{alt_allele}'
               if allele_pair in exclude_alleles:
                   excluded_snps_count += 1
                   excluded_snps_info.append(f'SNP {columns[2]} at position {columns[1]} has excluded alleles {allele_pair}')
               else:
                   output_file.write(line)

   remaining_snps_count = total_snps_count - excluded_snps_count

   print(f'Total SNPs before filtering: {total_snps_count}')
   print(f'Total SNPs after filtering: {remaining_snps_count}')
   print(f'Number of excluded SNPs (A/T and C/G alleles): {excluded_snps_count}')
   print('Details of first few excluded SNPs:')
   for info in excluded_snps_info[:5]:
       print(info)
   PYEOF
   ```
   Report: "AT_CG.py created" or "AT_CG.py already exists"

4. **Stale output**: `ls filtered_m4_p80_x0_S1_chr.singleton.hwe.maf01.LD.no_AT_CG.vcf 2>/dev/null`
   - If exists → **self-heal**: `rm -f filtered_m4_p80_x0_S1_chr.singleton.hwe.maf01.LD.no_AT_CG.vcf`

If all pass, proceed to Phase 2.

---

## Phase 2: Execution

```bash
python3 AT_CG.py
```

Fast (seconds). Capture stdout — it reports total/excluded/remaining counts.

Check exit code. If non-zero → check for Python errors in output. Self-heal once (fix syntax, permissions), then STOP if still failing.

---

## Phase 3: Verification

Run these 3 checks:

1. **Output VCF exists + has content**:
   ```bash
   test -f filtered_m4_p80_x0_S1_chr.singleton.hwe.maf01.LD.no_AT_CG.vcf && echo EXISTS
   grep -cv '^#' filtered_m4_p80_x0_S1_chr.singleton.hwe.maf01.LD.no_AT_CG.vcf
   ```
   Must be > 0.

2. **No A/T or G/C pairs remain**:
   ```bash
   grep -v '^#' filtered_m4_p80_x0_S1_chr.singleton.hwe.maf01.LD.no_AT_CG.vcf | \
     awk '{pair=$4"/"$5; if(pair=="A/T"||pair=="T/A"||pair=="C/G"||pair=="G/C") print}' | wc -l
   ```
   Must be 0.

3. **Counts add up**: INPUT_SNPS = remaining + excluded (from script output)

If ANY check fails → self-heal once then STOP.

### Error Diagnosis

| Symptom | Fix |
|---------|-----|
| AT_CG.py not found | Create it (see pre-flight check 3) |
| Python syntax error | Check Python version: `python3 --version`. Fix script |
| 0 remaining SNPs | All SNPs were A/T or G/C — report as WARNING, data issue |
| Output file empty | Script crashed mid-write — remove output, retry |

---

## Output

End your response with this exact structured summary:

```
## Step 11 Summary
- **Step**: 11 — Remove A/T and G/C SNPs
- **Status**: SUCCESS | FAILURE
- **Input SNPs**: <number>
- **Excluded (A/T + G/C)**: <number>
- **Remaining SNPs**: <number>
- **Issues**: <none | description>
- **Self-healing attempted**: Yes (description) | No

## Benchmark Comparison
| Metric | This run | PDF reference |
|--------|----------|---------------|
| Input SNPs | <n> | 5,719 |
| After AT/GC removal | <n> | 4,471 |
```
