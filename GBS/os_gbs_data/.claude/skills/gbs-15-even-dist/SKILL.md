---
name: gbs-15-even-dist
description: Run GBS pipeline Step 15 (even distribution of SNPs across chromosomes) on the server
context: fork
model: sonnet
allowed-tools: Bash, Read, Grep, Glob
---

# GBS Pipeline — Step 15: Even Distribution of SNPs (FINAL STEP)

You are running GBS pipeline Step 15 (the final step) directly on the server. All paths are relative to the project root (`gbs_data/`).

**What this step does**: Selects additional SNPs from the available pool to fill chromosomal gaps, ensuring even distribution across all 94 chromosomes. The 10 BLAST-validated SNPs are the "core" panel; additional SNPs are drawn from the 203-SNP MAF-filtered pool to cover empty chromosomes.

**Input**:
- `blast_filtered_snps.vcf` (10 core BLAST-validated SNPs)
- `filtered_m4_p80_x0_S1_chr.singleton.hwe.maf10.LD.no_AT_CG.recode.vcf` (203-SNP available pool)
- `08-genome/genome.fasta.fai` (chromosome lengths)

**Output**: `final_snp_panel.vcf`, `final_snp_panel_summary.txt`, `snp_distribution.txt`

**CRITICAL RULE**: Check exit code after each sub-step. If non-zero → self-heal ONCE. If still failing → report FAILURE and **STOP**.

---

## Phase 1: Pre-flight Checks

Run these 4 checks. Report each as PASS/FAIL.

1. **Core SNPs exist**: `test -f blast_filtered_snps.vcf && echo OK`. Count: `grep -cv '^#' blast_filtered_snps.vcf` → CORE_SNPS
   - FAIL → **stop**: "Step 14 not completed. Run `/gbs-14-blast-map` first."

2. **SNP pool exists**: `test -f filtered_m4_p80_x0_S1_chr.singleton.hwe.maf10.LD.no_AT_CG.recode.vcf && echo OK`. Count: `grep -cv '^#' filtered_m4_p80_x0_S1_chr.singleton.hwe.maf10.LD.no_AT_CG.recode.vcf` → POOL_SNPS
   - FAIL → **stop**: "MAF-filtered pool missing. Run `/gbs-12-maf-filter` first."

3. **Genome index exists**: `test -f 08-genome/genome.fasta.fai && echo OK`
   - FAIL → **self-heal**: `samtools faidx 08-genome/genome.fasta`

4. **Create even_distribute_snps.py if missing + stale cleanup**:
   Remove stale: `rm -f final_snp_panel.vcf final_snp_panel_summary.txt snp_distribution.txt 2>/dev/null`

   If `even_distribute_snps.py` does not exist, create it:
   ```bash
   cat > even_distribute_snps.py << 'PYEOF'
   #!/usr/bin/env python3
   """
   even_distribute_snps.py - Select SNPs for even distribution across chromosomes

   Selects additional SNPs from the available pool to ensure coverage across
   all chromosomes, prioritizing chromosomes with no existing markers.

   Selection strategy:
   1. Keep all core BLAST-validated SNPs
   2. For each chromosome with no core SNP, select the most centrally-located
      SNP from the available pool
   3. For large chromosomes, add additional SNPs spaced evenly

   Output:
   - final_snp_panel.vcf       : VCF with all selected SNPs
   - final_snp_panel_summary.txt: Per-chromosome summary
   - snp_distribution.txt      : Tab-delimited positions for plotting
   """
   import sys
   import os

   CORE_VCF = 'blast_filtered_snps.vcf'
   POOL_VCF = 'filtered_m4_p80_x0_S1_chr.singleton.hwe.maf10.LD.no_AT_CG.recode.vcf'
   GENOME_FAI = '08-genome/genome.fasta.fai'
   OUTPUT_VCF = 'final_snp_panel.vcf'
   SUMMARY_FILE = 'final_snp_panel_summary.txt'
   DIST_FILE = 'snp_distribution.txt'

   # Target chromosomes (NC_091150.1 through NC_091243.1 = 94 chromosomes)
   TARGET_PREFIX = 'NC_0911'

   # --- Load chromosome lengths ---
   chr_lengths = {}
   chr_order = []
   with open(GENOME_FAI) as f:
       for line in f:
           parts = line.strip().split('\t')
           chrom = parts[0]
           length = int(parts[1])
           if chrom.startswith(TARGET_PREFIX):
               chr_lengths[chrom] = length
               chr_order.append(chrom)

   print(f"Loaded {len(chr_lengths)} target chromosomes")

   # --- Load core SNPs ---
   core_snps = {}  # chrom -> list of (pos, line)
   core_header = []
   with open(CORE_VCF) as f:
       for line in f:
           if line.startswith('#'):
               core_header.append(line)
               continue
           cols = line.split('\t')
           chrom = cols[0]
           pos = int(cols[1])
           if chrom not in core_snps:
               core_snps[chrom] = []
           core_snps[chrom].append((pos, line))

   core_count = sum(len(v) for v in core_snps.values())
   core_chroms = set(core_snps.keys())
   print(f"Core SNPs: {core_count} on {len(core_chroms)} chromosomes")

   # --- Load pool SNPs ---
   pool_snps = {}  # chrom -> list of (pos, line)
   pool_header = []
   with open(POOL_VCF) as f:
       for line in f:
           if line.startswith('#'):
               if not core_header:
                   pool_header.append(line)
               continue
           cols = line.split('\t')
           chrom = cols[0]
           pos = int(cols[1])
           if chrom.startswith(TARGET_PREFIX):
               if chrom not in pool_snps:
                   pool_snps[chrom] = []
               pool_snps[chrom].append((pos, line))

   pool_count = sum(len(v) for v in pool_snps.values())
   pool_chroms = set(pool_snps.keys())
   print(f"Pool SNPs: {pool_count} on {len(pool_chroms)} chromosomes")

   # --- Selection algorithm ---
   selected = {}  # chrom -> list of (pos, line, source)

   # Step 1: Include all core SNPs
   for chrom, snps in core_snps.items():
       selected[chrom] = [(pos, line, 'CORE') for pos, line in snps]

   # Step 2: For chromosomes with no core SNP, pick the most central SNP from pool
   empty_chroms = [c for c in chr_order if c not in core_chroms]
   filled_from_pool = 0

   for chrom in empty_chroms:
       if chrom in pool_snps and len(pool_snps[chrom]) > 0:
           chr_len = chr_lengths[chrom]
           center = chr_len // 2
           # Pick SNP closest to center
           best = min(pool_snps[chrom], key=lambda x: abs(x[0] - center))
           selected[chrom] = [(best[0], best[1], 'POOL_FILL')]
           filled_from_pool += 1

   # Step 3: For large chromosomes (>50Mb), add more SNPs if available
   # Target: ~1 SNP per 10Mb for large chromosomes
   additional = 0
   for chrom in chr_order:
       chr_len = chr_lengths[chrom]
       current = len(selected.get(chrom, []))
       target = max(1, chr_len // 10_000_000)  # 1 per 10Mb

       if current < target and chrom in pool_snps:
           existing_pos = set(s[0] for s in selected.get(chrom, []))
           candidates = [(p, l) for p, l in pool_snps[chrom] if p not in existing_pos]

           # Select candidates evenly spaced
           needed = target - current
           if candidates and needed > 0:
               candidates.sort(key=lambda x: x[0])
               # Pick evenly spaced from candidates
               if len(candidates) <= needed:
                   picks = candidates
               else:
                   step = len(candidates) / needed
                   picks = [candidates[int(i * step)] for i in range(needed)]

               if chrom not in selected:
                   selected[chrom] = []
               for pos, line in picks:
                   selected[chrom].append((pos, line, 'POOL_EVEN'))
                   additional += 1

   # --- Write output VCF ---
   header = core_header if core_header else pool_header
   all_selected = []
   for chrom in chr_order:
       if chrom in selected:
           for pos, line, source in sorted(selected[chrom]):
               all_selected.append((chrom, pos, line, source))

   with open(OUTPUT_VCF, 'w') as out:
       for h in header:
           out.write(h)
       for chrom, pos, line, source in all_selected:
           out.write(line)

   # --- Write summary ---
   total_selected = len(all_selected)
   covered_chroms = len([c for c in chr_order if c in selected])

   with open(SUMMARY_FILE, 'w') as out:
       out.write("CHROMOSOME\tLENGTH_MB\tNUM_SNPS\tSOURCES\tPOSITIONS\n")
       for chrom in chr_order:
           length_mb = chr_lengths[chrom] / 1_000_000
           if chrom in selected:
               snps = sorted(selected[chrom])
               num = len(snps)
               sources = ','.join(s[2] for s in snps)
               positions = ','.join(str(s[0]) for s in snps)
           else:
               num = 0
               sources = 'NONE'
               positions = '-'
           out.write(f"{chrom}\t{length_mb:.1f}\t{num}\t{sources}\t{positions}\n")

   # --- Write distribution file (for plotting) ---
   with open(DIST_FILE, 'w') as out:
       out.write("CHROMOSOME\tPOSITION\tSOURCE\n")
       for chrom, pos, line, source in all_selected:
           out.write(f"{chrom}\t{pos}\t{source}\n")

   # --- Print summary ---
   print(f"\n{'='*60}")
   print(f"FINAL SNP PANEL SUMMARY")
   print(f"{'='*60}")
   print(f"Core BLAST-validated SNPs:  {core_count}")
   print(f"Added from pool (gap-fill): {filled_from_pool}")
   print(f"Added from pool (even dist): {additional}")
   print(f"Total final panel:          {total_selected}")
   print(f"Chromosomes covered:        {covered_chroms} / {len(chr_order)}")
   print(f"Chromosomes with NO SNPs:   {len(chr_order) - covered_chroms}")
   print(f"{'='*60}")
   print(f"Output files:")
   print(f"  {OUTPUT_VCF}")
   print(f"  {SUMMARY_FILE}")
   print(f"  {DIST_FILE}")

   # List uncovered chromosomes
   uncovered = [c for c in chr_order if c not in selected]
   if uncovered:
       print(f"\nWARNING: {len(uncovered)} chromosomes have no SNPs (not in pool either):")
       for c in uncovered:
           print(f"  {c} ({chr_lengths[c]/1_000_000:.1f} Mb)")
   PYEOF
   chmod +x even_distribute_snps.py
   ```

If all pass, proceed to Phase 2.

---

## Phase 2: Execution

```bash
python3 even_distribute_snps.py
```

Fast (seconds). Capture all output.

---

## Phase 3: Verification

Run these 3 checks:

1. **Final panel VCF exists + count**:
   ```bash
   test -f final_snp_panel.vcf && echo EXISTS
   grep -cv '^#' final_snp_panel.vcf
   ```

2. **Chromosome coverage**:
   ```bash
   grep -v '^#' final_snp_panel.vcf | cut -f1 | sort -u | wc -l
   ```
   Report how many of 94 chromosomes are covered.

3. **Summary file**:
   ```bash
   cat final_snp_panel_summary.txt
   ```
   Show full per-chromosome breakdown.

If ANY check fails → report FAILURE and **STOP**.

---

## Output

End your response with this exact structured summary:

```
## Step 15 Summary (FINAL)
- **Step**: 15 — Even Distribution of SNPs
- **Status**: SUCCESS | FAILURE
- **Core SNPs (from BLAST)**: <number>
- **Added from pool (gap-fill)**: <number>
- **Added from pool (even dist)**: <number>
- **Final panel size**: <number>
- **Chromosomes covered**: <number> / 94
- **Chromosomes with NO SNPs**: <number>
- **Issues**: <none | description>
- **Self-healing attempted**: Yes (description) | No

## Final SNP Panel Distribution
<paste full contents of final_snp_panel_summary.txt>

## Pipeline Complete
All 15 steps of the GBS pipeline have been executed:
Steps 0-4: Sample prep (lane info → cutadapt → process_radtags → rename → pop map)
Steps 5-7: Alignment + genotyping (BWA → gstacks → populations)
Steps 8-10: VCF filtering (basic filter → chr select → dup/HWE → LD clump)
Steps 11-13: SNP QC (AT/GC removal → MAF 0.1 → flanking variants)
Steps 14-15: Panel design (BLAST mapping → even distribution)
Final output: final_snp_panel.vcf
```
