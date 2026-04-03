---
name: gbs-14-blast-map
description: Run GBS pipeline Step 14 (SNP mapping against reference genome via BLAST) on the server
context: fork
model: sonnet
allowed-tools: Bash, Read, Grep, Glob
---

# GBS Pipeline — Step 14: SNP Mapping Against Reference Genome

You are running GBS pipeline Step 14 directly on the server. All paths are relative to the project root (`gbs_data/`).

**What this step does**: Extracts flanking sequences around each candidate SNP, BLASTs them against the reference genome, and removes SNPs that map to multiple locations (paralogous), have PID/QAL issues, or low complexity.

**Input**: `filtered_flanking.vcf` (12 SNPs from Step 13)
**Output**: `blast_output.txt` (BLAST mapping results), final filtered SNP list

**CRITICAL RULE**: Check exit code after each sub-step. If non-zero → self-heal ONCE. If still failing → report FAILURE and **STOP**.

**Commands follow the exact same interface as the PDF TODO document** so others can reference the same workflow.

---

## Phase 1: Pre-flight Checks

Run these 5 checks. Report each as PASS/FAIL.

1. **Input VCF exists**: `test -f filtered_flanking.vcf && echo OK`. Count: `grep -cv '^#' filtered_flanking.vcf` → INPUT_SNPS
   - FAIL → **stop**: "Step 13 not completed. Run `/gbs-13-flanking` first."

2. **Genome exists**: `test -f 08-genome/genome.fasta && echo OK`
   - FAIL → **stop**: "Genome not found at 08-genome/genome.fasta."

3. **Tools installed**:
   ```bash
   which blastn && which makeblastdb && which vcftools && which perl && which samtools && echo "ALL OK"
   ```
   - FAIL → **stop**: report which tool is missing

4. **Genome FASTA index**: `test -f 08-genome/genome.fasta.fai && echo OK`
   - FAIL → **self-heal**: `samtools faidx 08-genome/genome.fasta`

5. **Create scripts if missing + stale cleanup**:
   Remove stale output: `rm -f flanking_input.txt flanking_output.txt blast_input.txt blast_output.txt snp_mapping.txt crayfish_mapping_snps.* 2>/dev/null`

   **Create `snpFormat.pl` if missing** (`test -f snpFormat.pl`):
   ```bash
   cat > snpFormat.pl << 'PLEOF'
   #!/usr/bin/perl
   use strict;
   use warnings;
   use Getopt::Long;

   # snpFormat.pl - Extract flanking sequences around SNPs from a reference genome
   # Usage: ./snpFormat.pl --in flanking_input.txt --ref genome.fasta --out flanking_output.txt
   #
   # Input format (flanking_input.txt): tab-delimited
   #   CHROM  POS  SNP_ID  REF  ALT
   #
   # Output format (flanking_output.txt): tab-delimited
   #   SNP_ID  CHROM  POS  REF  ALT  FLANKING_SEQ  SNP_POS_IN_SEQ

   my ($infile, $reffile, $outfile);
   my $flank = 100;

   GetOptions(
       'in=s'    => \$infile,
       'ref=s'   => \$reffile,
       'out=s'   => \$outfile,
       'flank=i' => \$flank,
   ) or die "Usage: $0 --in <input> --ref <genome.fasta> --out <output> [--flank 100]\n";

   die "Missing --in\n" unless $infile;
   die "Missing --ref\n" unless $reffile;
   die "Missing --out\n" unless $outfile;

   # Check samtools available
   system("which samtools > /dev/null 2>&1") == 0 or die "samtools not found in PATH\n";

   open(my $IN, '<', $infile) or die "Cannot open $infile: $!\n";
   open(my $OUT, '>', $outfile) or die "Cannot open $outfile: $!\n";

   # Header
   print $OUT "SNP_ID\tCHROM\tPOS\tREF\tALT\tFLANKING_SEQ\tSNP_POS_IN_SEQ\n";

   while (my $line = <$IN>) {
       chomp $line;
       next if $line =~ /^#/ || $line =~ /^CHROM/;
       my @cols = split(/\t/, $line);
       my ($chrom, $pos, $id, $ref, $alt) = @cols[0..4];

       my $start = $pos - $flank;
       $start = 1 if $start < 1;
       my $end = $pos + $flank;

       # Extract sequence using samtools faidx
       my $region = "${chrom}:${start}-${end}";
       my $seq = `samtools faidx $reffile $region 2>/dev/null`;
       $seq =~ s/^>.*\n//;  # remove FASTA header
       $seq =~ s/\n//g;     # join lines
       $seq = uc($seq);

       my $snp_offset = $pos - $start;

       # Mark SNP in sequence: replace SNP position with [REF/ALT]
       my $marked_seq = substr($seq, 0, $snp_offset) . "[${ref}/${alt}]" . substr($seq, $snp_offset + 1);

       print $OUT "${id}\t${chrom}\t${pos}\t${ref}\t${alt}\t${marked_seq}\t${snp_offset}\n";
   }

   close($IN);
   close($OUT);

   my $count = `wc -l < $outfile` - 1;
   print "Extracted flanking sequences for $count SNPs\n";
   print "Output: $outfile\n";
   PLEOF
   chmod +x snpFormat.pl
   ```

   **Create `map_new.pl` if missing** (`test -f map_new.pl`):
   ```bash
   cat > map_new.pl << 'PLEOF'
   #!/usr/bin/perl
   use strict;
   use warnings;
   use Getopt::Long;

   # map_new.pl - BLAST flanking sequences against reference genome and evaluate mapping
   # Usage: perl map_new.pl -in blast_input.txt -ref genome.fasta -out blast_output.txt
   #
   # Input: FASTA file of flanking sequences (from snpFormat.pl output, converted to FASTA)
   # Output: tab-delimited mapping results with flags
   #
   # Flags:
   #   UNIQUE  - Single high-quality hit at expected location
   #   PID     - Multiple hits with high percent identity (paralogous)
   #   QAL     - Query alignment length issue (partial mapping)
   #   LOWCX   - Low complexity region (dust-masked)

   my ($infile, $reffile, $outfile);
   my $evalue = 1e-10;
   my $min_pident = 90;
   my $min_length = 150;

   GetOptions(
       'in=s'    => \$infile,
       'ref=s'   => \$reffile,
       'out=s'   => \$outfile,
       'evalue=f' => \$evalue,
   ) or die "Usage: $0 -in <fasta> -ref <genome.fasta> -out <output>\n";

   die "Missing -in\n" unless $infile;
   die "Missing -ref\n" unless $reffile;
   die "Missing -out\n" unless $outfile;

   # Build BLAST DB if needed
   unless (-f "${reffile}.nhr" || -f "${reffile}.nsq") {
       print "Building BLAST database...\n";
       system("makeblastdb -dbtype nucl -in $reffile -input_type fasta -title $reffile") == 0
           or die "makeblastdb failed\n";
   }

   # Run BLAST
   my $blast_raw = "${outfile}.blast_raw";
   print "Running BLAST...\n";
   my $blast_cmd = "blastn -query $infile -db $reffile " .
       "-outfmt '6 qseqid sseqid pident length mismatch gapopen qstart qend sstart send evalue bitscore qlen' " .
       "-out $blast_raw -evalue $evalue -dust yes";
   system($blast_cmd) == 0 or die "blastn failed\n";

   # Parse BLAST results
   my %hits;
   open(my $BLAST, '<', $blast_raw) or die "Cannot open $blast_raw: $!\n";
   while (<$BLAST>) {
       chomp;
       my @cols = split(/\t/);
       my $qid = $cols[0];
       push @{$hits{$qid}}, {
           subject  => $cols[1],
           pident   => $cols[2],
           length   => $cols[3],
           evalue   => $cols[10],
           bitscore => $cols[11],
           qlen     => $cols[12] || 0,
       };
   }
   close($BLAST);

   # Classify each SNP
   open(my $OUT, '>', $outfile) or die "Cannot open $outfile: $!\n";
   print $OUT "SNP_ID\tNUM_HITS\tBEST_PIDENT\tBEST_LENGTH\tFLAG\tSTATUS\n";

   # Read query IDs from input FASTA
   my @queries;
   open(my $FA, '<', $infile) or die "Cannot open $infile: $!\n";
   while (<$FA>) {
       if (/^>(\S+)/) {
           push @queries, $1;
       }
   }
   close($FA);

   my ($kept, $removed_pid, $removed_qal, $removed_lcx) = (0, 0, 0, 0);

   foreach my $qid (@queries) {
       my @qhits = @{$hits{$qid} || []};
       my $num_hits = scalar @qhits;

       # Get best hit stats
       my $best_pident = 0;
       my $best_length = 0;
       foreach my $h (@qhits) {
           $best_pident = $h->{pident} if $h->{pident} > $best_pident;
           $best_length = $h->{length} if $h->{length} > $best_length;
       }

       # Count high-quality hits
       my @good_hits = grep { $_->{pident} >= $min_pident && $_->{length} >= $min_length } @qhits;
       my $num_good = scalar @good_hits;

       # Classify
       my ($flag, $status);
       if ($num_good == 0) {
           $flag = "LOWCX";
           $status = "REMOVED";
           $removed_lcx++;
       } elsif ($num_good == 1) {
           # Check alignment length vs query length
           my $qlen = $good_hits[0]->{qlen};
           if ($qlen > 0 && $good_hits[0]->{length} < $qlen * 0.8) {
               $flag = "QAL";
               $status = "REMOVED";
               $removed_qal++;
           } else {
               $flag = "UNIQUE";
               $status = "KEPT";
               $kept++;
           }
       } else {
           $flag = "PID";
           $status = "REMOVED";
           $removed_pid++;
       }

       print $OUT "$qid\t$num_good\t$best_pident\t$best_length\t$flag\t$status\n";
   }

   close($OUT);

   # Summary
   my $total = scalar @queries;
   print "\n--- BLAST Mapping Summary ---\n";
   print "Total SNPs:              $total\n";
   print "Unique mappers (KEPT):   $kept\n";
   print "PID flag (REMOVED):      $removed_pid\n";
   print "QAL flag (REMOVED):      $removed_qal\n";
   print "Low complexity (REMOVED): $removed_lcx\n";
   print "Output: $outfile\n";
   PLEOF
   chmod +x map_new.pl
   ```

If all pass, proceed to Phase 2.

---

## Phase 2: Execution (4 sub-steps, matching PDF commands)

### Sub-step 1: Generate SNP list + allele frequencies (exact PDF command)

```bash
grep -v '^#' filtered_flanking.vcf | awk -F'\t' '{print $1"\t"$2"\t"$3"\t"$4"\t"$5}' > flanking_input.txt
grep -v '^#' filtered_flanking.vcf | cut -f3 > snp_mapping.txt
vcftools --vcf filtered_m4_p80_x0_S1_chr.singleton.hwe.maf10.LD.no_AT_CG.recode.vcf --snps snp_mapping.txt --freq --out crayfish_mapping_snps
```

### Sub-step 2: Extract flanking sequences (snpFormat.pl — matches PDF)

```bash
./snpFormat.pl --in flanking_input.txt --ref 08-genome/genome.fasta --out flanking_output.txt
```

Then convert flanking_output.txt to FASTA for BLAST input:
```bash
awk -F'\t' 'NR>1 {gsub(/\[.*\]/, "", $6); print ">"$1"|"$2":"$3"|"$4">"$5; print $6}' flanking_output.txt > blast_input.txt
```

### Sub-step 3: Build BLAST database (exact PDF command)

```bash
makeblastdb -dbtype nucl -in 08-genome/genome.fasta -input_type fasta -title genome.fasta
```

### Sub-step 4: Map SNPs via BLAST (map_new.pl — matches PDF)

```bash
perl map_new.pl -in blast_input.txt -ref 08-genome/genome.fasta -out blast_output.txt
```

Then extract kept SNPs into a VCF:
```bash
# Get list of kept SNP IDs
awk -F'\t' '$6=="KEPT" {print $1}' blast_output.txt > blast_kept_ids.txt

# Extract kept SNPs from VCF
grep '^#' filtered_flanking.vcf > blast_filtered_snps.vcf
while read -r SNP_ID; do
  grep -P "\t${SNP_ID}\t" filtered_flanking.vcf >> blast_filtered_snps.vcf
done < blast_kept_ids.txt
```

---

## Phase 3: Verification

Run these 4 checks:

1. **flanking_output.txt exists**: `test -f flanking_output.txt && wc -l < flanking_output.txt` — should be INPUT_SNPS + 1 (header)

2. **blast_output.txt exists + has results**: `test -f blast_output.txt && cat blast_output.txt`

3. **blast_filtered_snps.vcf exists**: `test -f blast_filtered_snps.vcf && grep -cv '^#' blast_filtered_snps.vcf`

4. **Flag distribution**: `awk -F'\t' 'NR>1 {print $5}' blast_output.txt | sort | uniq -c`

If ANY check fails → report FAILURE and **STOP**.

### Error Diagnosis

| Symptom | Fix |
|---------|-----|
| snpFormat.pl permission denied | `chmod +x snpFormat.pl`, retry |
| samtools faidx region error | Check chromosome names match between VCF and genome |
| makeblastdb fails | Check disk space. Check genome format |
| map_new.pl no results | Check blast_input.txt is valid FASTA: `head blast_input.txt` |
| All SNPs get PID flag | Flanking region maps to many places — normal for repetitive regions |

---

## Output

End your response with this exact structured summary:

```
## Step 14 Summary
- **Step**: 14 — SNP Mapping Against Reference Genome
- **Status**: SUCCESS | FAILURE
- **Input SNPs**: <number>
- **Unique mappers (KEPT)**: <number>
- **PID flag (REMOVED)**: <number>
- **QAL flag (REMOVED)**: <number>
- **Low complexity (REMOVED)**: <number>
- **Final SNPs**: <number>
- **Issues**: <none | description>
- **Self-healing attempted**: Yes (description) | No
```
