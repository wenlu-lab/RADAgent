"""Step 13 — Flanking variants filter."""
from pathlib import Path


def comparator(project_root: Path) -> dict:
    vcf = project_root / "filtered_flanking.vcf"
    if not vcf.is_file():
        return {"vcf_exists": False}
    snp_count = sum(1 for line in vcf.open() if not line.startswith("#"))
    return {"vcf_exists": True, "snp_count": snp_count}
