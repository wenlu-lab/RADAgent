# 08-genome

## Required file (not committed)

This folder must contain the reference genome FASTA before the pipeline can run:

```
08-genome/genome.fasta
```

The file is ~3.8 GB and is excluded from version control via `.gitignore`. The pipeline will error out if it is missing.

## How to provide it

Copy the reference into this directory:

```bash
cp /path/to/your/genome.fasta RAD/os_rad_data/08-genome/genome.fasta
```

The file must be named exactly `genome.fasta` (the alignment scripts in `00-scripts/` reference this name).
