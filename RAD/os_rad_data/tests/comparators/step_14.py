"""Step 14 — BLAST validation."""
from pathlib import Path


def comparator(project_root: Path) -> dict:
    blast_vcf = project_root / "blast_filtered_snps.vcf"
    blast_kept = project_root / "blast_kept_ids.txt"
    blast_input = project_root / "blast_input.txt"
    return {
        "blast_filtered_vcf_exists": blast_vcf.is_file(),
        "blast_kept_count": len(blast_kept.read_text().strip().splitlines()) if blast_kept.is_file() else 0,
        "blast_input_seq_count": sum(1 for l in blast_input.open() if l.startswith(">")) if blast_input.is_file() else 0,
    }
