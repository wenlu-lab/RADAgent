"""Step 8 — VCF filtering + chromosome selection."""
from pathlib import Path


def comparator(project_root: Path) -> dict:
    vcf = project_root / "filtered_m4_p80_x0_S1_chr.recode.vcf"
    if not vcf.is_file():
        return {"chr_vcf_exists": False}
    chroms = set()
    with vcf.open() as f:
        for line in f:
            if line.startswith("#"):
                continue
            chroms.add(line.split("\t", 1)[0])
            if len(chroms) > 200:
                break
    return {
        "chr_vcf_exists": True,
        "unique_chromosomes": len(chroms),
        "all_chroms_start_with_NC": all(c.startswith("NC_") for c in chroms),
    }
