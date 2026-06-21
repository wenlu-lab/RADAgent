"""Step 15 — Even distribution: produces final_snp_panel.vcf."""
import hashlib
from collections import Counter
from pathlib import Path


def md5_sorted(items):
    h = hashlib.md5()
    for x in sorted(items):
        h.update(x.encode("utf-8") + b"\n")
    return h.hexdigest()


def comparator(project_root: Path) -> dict:
    vcf = project_root / "final_snp_panel.vcf"
    summary = project_root / "final_snp_panel_summary.txt"
    if not vcf.is_file():
        return {"final_vcf_exists": False}
    positions = []
    chroms = []
    with vcf.open() as f:
        for line in f:
            if line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) >= 2:
                chroms.append(parts[0])
                positions.append(f"{parts[0]}:{parts[1]}")
    return {
        "final_vcf_exists": True,
        "snp_count": len(positions),
        "chromosomes_covered": len(set(chroms)),
        "snps_per_chrom": dict(Counter(chroms)),
        "position_set_md5": md5_sorted(positions),
        "summary_file_exists": summary.is_file(),
    }
