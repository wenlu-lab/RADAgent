#!/bin/bash
# Clean GBS pipeline outputs — keeps raw FASTQs, scripts, genome, and skill-created tools
# Usage: ./clean_pipeline.sh [step|range|all]
#   No args  = clean everything (steps 0-15 + logs)
#   0        = clean Step 0 only
#   0-3      = clean Steps 0 through 3
#   5        = clean Step 5 only
#   all      = clean everything
#   indexes  = clean BWA + BLAST indexes (expensive to rebuild!)
#
# Pipeline steps:
#   0  = Lane info
#   1  = Cutadapt trimming
#   2  = process_radtags
#   3  = Rename samples
#   4  = Population map
#   5  = BWA alignment
#   6  = gstacks
#   7  = Stacks populations
#   8  = VCF filtering + chr selection
#   9  = SNP duplication + HWE
#   10 = LD clumping
#   11 = AT/GC removal
#   12 = MAF 0.1 filter
#   13 = Flanking variants filter
#   14 = BLAST mapping
#   15 = Even distribution (final panel)

cd ~/os_gbs_data || { echo "ERROR: ~/os_gbs_data not found"; exit 1; }

clean_step0() {
  echo "Cleaning Step 0 (lane_info.txt)..."
  rm -f 01-info_files/lane_info.txt
}

clean_step1() {
  echo "Cleaning Step 1 (trimmed FASTQs)..."
  rm -rf 02-raw/trimmed
}

clean_step2() {
  echo "Cleaning Step 2 (process_radtags)..."
  rm -rf 03-samples
  rm -f 01-info_files/.temp.*.barcodes
}

clean_step3() {
  echo "Cleaning Step 3 (renamed samples)..."
  rm -f 04-all_samples/*.fq.gz
  rm -f renaming_01l.txt renaming_02l.txt renaming_01r.txt renaming_02r.txt 2>/dev/null
}

clean_step4() {
  echo "Cleaning Step 4 (population map)..."
  rm -f 01-info_files/population_map.txt
}

clean_step5() {
  echo "Cleaning Step 5 (BWA alignment)..."
  rm -f 04-all_samples/*.bam
  rm -f 04-all_samples/*.sorted.bam
  rm -f 04-all_samples/*.sorted.bam.bai
}

clean_step6() {
  echo "Cleaning Step 6 (gstacks)..."
  rm -f 05-stacks/catalog.*
  rm -f 05-stacks/gstacks.*
}

clean_step7() {
  echo "Cleaning Step 7 (populations)..."
  rm -f 05-stacks/populations.*
}

clean_step8() {
  echo "Cleaning Step 8 (VCF filtering + chr selection)..."
  rm -f filtered_m4_p80_x0_S1.vcf
  rm -f filtered_m4_p80_x0_S1.chrom-map.txt
  rm -f filtered_m4_p80_x0_S1.map
  rm -f filtered_m4_p80_x0_S1.ped
  rm -f filtered_m4_p80_x0_S1.log
  rm -f filtered_m4_p80_x0_S1_chr.recode.vcf
  rm -rf graphs_filtered_m4_p80_x0_S1
  rm -rf .temp_graph_folder
}

clean_step9() {
  echo "Cleaning Step 9 (SNP duplication + HWE)..."
  rm -f snp_duplication_info.txt*
  rm -f filtered_m4_p80_x0_S1_chr.recode.singleton.vcf.out
  rm -f filtered_m4_p80_x0_S1_chr.recode.duplicate*.vcf.out
  rm -f filtered_m4_p80_x0_S1_chr.recode.diverged.vcf.out
  rm -f filtered_m4_p80_x0_S1_chr.recode.lowconf.vcf.out
  rm -f filtered_m4_p80_x0_S1_chr.recode.highcov.vcf.out
  rm -f filtered_m4_p80_x0_S1_chr.recode.mas.vcf.out
  rm -f filtered_m4_p80_x0_S1_chr.recode.singleton.vcf
  rm -f filtered_m4_p80_x0_S1_chr.recode.duplicated.vcf
  rm -f filtered_m4_p80_x0_S1_chr.recode.diverged.vcf
  rm -f filtered_m4_p80_x0_S1_chr.recode.lowconf.vcf
  rm -f filtered_m4_p80_x0_S1_chr.recode.highcov.vcf
  rm -f filtered_m4_p80_x0_S1_chr.recode.mas.vcf
  rm -f filtered_m4_p80_x0_S1_chr.singleton.hwe*
  rm -f *.inds *.hwe exclude.hwe filtered.hwe 2>/dev/null
  # rm -f filter_hwe_by_pop.pl
}

clean_step10() {
  echo "Cleaning Step 10 (LD clumping)..."
  rm -f filtered_m4_p80_x0_S1_chr.singleton.hwe.maf01*
  rm -f ld_clump.R
  rm -f LD_regions.txt
}

clean_step11() {
  echo "Cleaning Step 11 (AT/GC removal)..."
  rm -f filtered_m4_p80_x0_S1_chr.singleton.hwe.maf01.LD.no_AT_CG.vcf
  rm -f AT_CG.py
}

clean_step12() {
  echo "Cleaning Step 12 (MAF 0.1 filter)..."
  rm -f filtered_m4_p80_x0_S1_chr.singleton.hwe.maf10.LD.no_AT_CG.recode.vcf
  rm -f filtered_m4_p80_x0_S1_chr.singleton.hwe.maf10.LD.no_AT_CG.log
}

clean_step13() {
  echo "Cleaning Step 13 (flanking variants filter)..."
  rm -f filtered_flanking.vcf
  rm -f count.txt
  rm -f count_snp_indel.py
}

clean_step14() {
  echo "Cleaning Step 14 (BLAST mapping)..."
  rm -f flanking_input.txt flanking_output.txt
  rm -f blast_input.txt blast_output.txt blast_output.txt.blast_raw
  rm -f blast_filtered_snps.vcf blast_kept_ids.txt
  rm -f snp_mapping.txt
  rm -f crayfish_mapping_snps.frq crayfish_mapping_snps.log
  rm -f flanking_sequences.fasta blast_results.txt
  rm -f snpFormat.pl map_new.pl extract_flanking.py
  rm -f blast_kept_snpids.txt
}

clean_step15() {
  echo "Cleaning Step 15 (even distribution / final panel)..."
  rm -f final_snp_panel.vcf final_snp_panel_summary.txt
  rm -f snp_distribution.txt
  rm -f even_distribute_snps.py
}

clean_indexes() {
  echo "Cleaning genome indexes (BWA + BLAST)..."
  echo "  WARNING: These are expensive to rebuild (~1 hour)"
  # BWA index
  rm -f 08-genome/genome.fasta.amb 08-genome/genome.fasta.ann
  rm -f 08-genome/genome.fasta.bwt 08-genome/genome.fasta.pac
  rm -f 08-genome/genome.fasta.sa
  # BLAST DB (single-volume and multi-volume)
  rm -f 08-genome/genome.fasta.nhr 08-genome/genome.fasta.nin
  rm -f 08-genome/genome.fasta.nsq 08-genome/genome.fasta.ndb
  rm -f 08-genome/genome.fasta.not 08-genome/genome.fasta.ntf
  rm -f 08-genome/genome.fasta.nto
  rm -f 08-genome/genome.fasta.*.nhr 08-genome/genome.fasta.*.nin
  rm -f 08-genome/genome.fasta.*.nsq
  rm -f 08-genome/genome.fasta.nal
  # Samtools index
  rm -f 08-genome/genome.fasta.fai
}

clean_logs() {
  echo "Cleaning log files..."
  rm -f 10-log_files/*
}

# Parse argument
ARG="${1:-all}"

if [ "$ARG" = "all" ]; then
  clean_step0; clean_step1; clean_step2; clean_step3; clean_step4
  clean_step5; clean_step6; clean_step7; clean_step8; clean_step9
  clean_step10; clean_step11; clean_step12; clean_step13; clean_step14
  clean_step15; clean_logs
  echo ""
  echo "NOTE: BWA/BLAST indexes NOT cleaned (use './clean_pipeline.sh indexes' to remove)"
elif [ "$ARG" = "indexes" ]; then
  clean_indexes
elif echo "$ARG" | grep -q '-'; then
  START=$(echo "$ARG" | cut -d- -f1)
  END=$(echo "$ARG" | cut -d- -f2)
  for i in $(seq $START $END); do
    clean_step$i
  done
  clean_logs
else
  clean_step$ARG
  clean_logs
fi

echo ""
echo "=== Remaining files ==="
echo "02-raw originals:  $(ls 02-raw/*.fastq.gz 2>/dev/null | wc -l) files"
echo "Scripts (00-scripts): $(ls 00-scripts/*.sh 00-scripts/*.py 00-scripts/*.R 00-scripts/utility_scripts/*.sh 2>/dev/null | wc -l) files"
echo "Skill-created tools: $(ls AT_CG.py count_snp_indel.py snpFormat.pl map_new.pl extract_flanking.py even_distribute_snps.py filter_hwe_by_pop.pl 2>/dev/null | wc -l) files"
echo "Genome:            $(ls 08-genome/genome.fasta 2>/dev/null | wc -l) file"
echo "BWA index:         $(ls 08-genome/genome.fasta.bwt 2>/dev/null | wc -l) file"
echo "BLAST DB:          $(ls 08-genome/genome.fasta.nhr 2>/dev/null | wc -l) file"
echo "Done."
