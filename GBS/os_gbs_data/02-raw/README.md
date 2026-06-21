# 02-raw

## Required files (not committed)

This folder must contain the raw paired-end sequencing reads before the pipeline can run. The full dataset is ~**101 GB across ~953 files** and is excluded from version control via `.gitignore`. The pipeline will error out if these are missing.

## Expected layout

Paired-end FASTQ files, gzipped, named by SRA run accession:

```
02-raw/SRR<accession>_1.fastq.gz    # forward reads (R1)
02-raw/SRR<accession>_2.fastq.gz    # reverse reads (R2)
```

Every sample must have both `_1` and `_2` files. The downstream scripts in `00-scripts/` (cutadapt, process_radtags, bwa) expect this exact naming.

## How to provide it

If you already have the data locally:

```bash
cp /path/to/your/fastq/*.fastq.gz GBS/os_gbs_data/02-raw/
```

Verify the count after copying:

```bash
ls GBS/os_gbs_data/02-raw/*.fastq.gz | wc -l   # should match 2 x sample count
```
