---
name: gbs-13-flanking
description: Run GBS pipeline Step 13 (flanking variants filter) on the server
context: fork
model: sonnet
allowed-tools: Bash, Read, Grep, Glob
---

# GBS Pipeline — Step 13: Flanking Variants Filter

You are running GBS pipeline Step 13 directly on the server. All paths are relative to the project root (`gbs_data/`).

**What this step does**: For each candidate SNP, counts how many other SNPs and indels are within a 150bp window on the same chromosome (using the full chr-filtered VCF as reference). Removes candidates with >3 nearby SNPs or >1 nearby indel — these regions indicate paralogous/duplicated loci or assembly errors.

**Input**: `filtered_m4_p80_x0_S1_chr.singleton.hwe.maf10.LD.no_AT_CG.recode.vcf` (candidates, 203 SNPs)
**Reference**: `filtered_m4_p80_x0_S1_chr.recode.vcf` (all chr-filtered variants from Step 8, ~64K variants)
**Output**: `filtered_flanking.vcf` (candidates passing flanking filter), `count.txt` (per-SNP counts)

**CRITICAL RULE**: Check exit code after each sub-step. If non-zero → self-heal ONCE. If still failing → report FAILURE and **STOP**.

---

## Phase 1: Pre-flight Checks

Run these 4 checks. Report each as PASS/FAIL.

1. **Input VCF exists**: `test -f filtered_m4_p80_x0_S1_chr.singleton.hwe.maf10.LD.no_AT_CG.recode.vcf && echo OK`. Count SNPs: `grep -cv '^#' filtered_m4_p80_x0_S1_chr.singleton.hwe.maf10.LD.no_AT_CG.recode.vcf` → INPUT_SNPS
   - FAIL → **stop**: "Step 12 not completed. Run `/gbs-12-maf-filter` first."

2. **Reference VCF exists**: `test -f filtered_m4_p80_x0_S1_chr.recode.vcf && echo OK`
   - FAIL → **stop**: "Reference VCF from Step 8 missing. Run `/gbs-8-vcf-filter` first."

3. **python3 installed**: `which python3`
   - FAIL → **stop**: "python3 not found."

4. **Create count_snp_indel.py if missing**: Check `test -f count_snp_indel.py`. If missing, create it:

```bash
cat > count_snp_indel.py << 'PYEOF'
import sys

WINDOW = 150  # bp upstream and downstream

candidate_vcf = 'filtered_m4_p80_x0_S1_chr.singleton.hwe.maf10.LD.no_AT_CG.recode.vcf'
reference_vcf = 'filtered_m4_p80_x0_S1_chr.recode.vcf'
output_vcf = 'filtered_flanking.vcf'

# Load all reference variants indexed by chromosome
ref_variants = {}  # chr -> list of (pos, is_indel)
with open(reference_vcf) as f:
    for line in f:
        if line.startswith('#'):
            continue
        cols = line.split('\t', 6)
        chrom = cols[0]
        pos = int(cols[1])
        ref_allele = cols[3]
        alt_allele = cols[4]
        is_indel = len(ref_allele) != len(alt_allele)
        if chrom not in ref_variants:
            ref_variants[chrom] = []
        ref_variants[chrom].append((pos, is_indel))

# Sort reference variants by position for efficient searching
for chrom in ref_variants:
    ref_variants[chrom].sort()

# Process candidates
print(f"CHROM\tPOS\tID\tNEARBY_SNPS\tNEARBY_INDELS\tSTATUS")

kept_count = 0
removed_snp_count = 0
removed_indel_count = 0
total = 0

header_lines = []
kept_lines = []

with open(candidate_vcf) as f:
    for line in f:
        if line.startswith('#'):
            header_lines.append(line)
            continue
        total += 1
        cols = line.split('\t', 6)
        chrom = cols[0]
        pos = int(cols[1])
        snp_id = cols[2]

        # Count nearby variants in reference
        nearby_snps = 0
        nearby_indels = 0
        if chrom in ref_variants:
            for ref_pos, is_indel in ref_variants[chrom]:
                if ref_pos < pos - WINDOW:
                    continue
                if ref_pos > pos + WINDOW:
                    break
                if ref_pos == pos:
                    continue  # skip self
                if is_indel:
                    nearby_indels += 1
                else:
                    nearby_snps += 1

        # Apply filter
        if nearby_snps > 3 or nearby_indels > 1:
            status = "REMOVED"
            if nearby_snps > 3:
                removed_snp_count += 1
            if nearby_indels > 1:
                removed_indel_count += 1
        else:
            status = "KEPT"
            kept_count += 1
            kept_lines.append(line)

        print(f"{chrom}\t{pos}\t{snp_id}\t{nearby_snps}\t{nearby_indels}\t{status}")

# Write filtered VCF
with open(output_vcf, 'w') as out:
    for h in header_lines:
        out.write(h)
    for l in kept_lines:
        out.write(l)

# Summary to stderr
sys.stderr.write(f"\nFlanking filter summary:\n")
sys.stderr.write(f"  Total candidates: {total}\n")
sys.stderr.write(f"  Removed (>3 nearby SNPs): {removed_snp_count}\n")
sys.stderr.write(f"  Removed (>1 nearby indel): {removed_indel_count}\n")
sys.stderr.write(f"  Kept: {kept_count}\n")
PYEOF
```

Report: "count_snp_indel.py created" or "already exists"

Also remove stale output: `rm -f count.txt filtered_flanking.vcf 2>/dev/null`

If all pass, proceed to Phase 2.

---

## Phase 2: Execution

```bash
python3 count_snp_indel.py > count.txt 2>&1
```

The script outputs per-SNP counts to stdout (→ count.txt) and a summary to stderr. It also writes `filtered_flanking.vcf` directly.

Check exit code. If non-zero → report error and **STOP**.

---

## Phase 3: Verification

Run these 3 checks:

1. **count.txt exists + has content**: `test -f count.txt && wc -l < count.txt` — should be INPUT_SNPS + 1 (header)

2. **Filtered VCF exists + count SNPs**:
   ```bash
   test -f filtered_flanking.vcf && echo EXISTS
   grep -cv '^#' filtered_flanking.vcf
   ```
   Must be > 0.

3. **No remaining SNPs violate filter**: Verify from count.txt:
   ```bash
   awk -F'\t' '$6=="KEPT" && ($4>3 || $5>1)' count.txt | wc -l
   ```
   Must be 0.

If ANY check fails → report FAILURE and **STOP**.

### Error Diagnosis

| Symptom | Fix |
|---------|-----|
| Python error | Check: `python3 --version`. Fix script syntax |
| Reference VCF too large for memory | Use indexed approach or stream. Report if >16GB |
| 0 SNPs kept | Filter too aggressive — report counts and suggest relaxing thresholds |

---

## Output

End your response with this exact structured summary:

```
## Step 13 Summary
- **Step**: 13 — Flanking Variants Filter
- **Status**: SUCCESS | FAILURE
- **Input SNPs**: <number>
- **SNPs removed (>3 nearby SNPs)**: <number>
- **SNPs removed (>1 nearby indel)**: <number>
- **Remaining SNPs**: <number>
- **Issues**: <none | description>
- **Self-healing attempted**: Yes (description) | No
```
