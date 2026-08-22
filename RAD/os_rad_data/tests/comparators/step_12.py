"""Step 12 — MAF >= 0.1 filter."""
from pathlib import Path


def comparator(project_root: Path) -> dict:
    # Look for files matching the post-MAF pattern
    candidates = list(project_root.glob("*maf*.vcf")) + list(project_root.glob("*maf01*.vcf"))
    candidates = [c for c in candidates if c.is_file()]
    if not candidates:
        return {"maf_vcf_exists": False}
    target = max(candidates, key=lambda p: p.stat().st_mtime)
    snp_count = 0
    with target.open() as f:
        for line in f:
            if not line.startswith("#"):
                snp_count += 1
    return {"maf_vcf_exists": True, "snp_count": snp_count, "vcf_name": target.name}
