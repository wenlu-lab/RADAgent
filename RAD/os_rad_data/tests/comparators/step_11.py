"""Step 11 — Remove A/T and G/C strand-ambiguous SNPs."""
from pathlib import Path


def comparator(project_root: Path) -> dict:
    vcf = project_root / "filtered_m4_p80_x0_S1_chr.singleton.hwe.maf01.LD.no_AT_CG.vcf"
    if not vcf.is_file():
        return {"vcf_exists": False}
    snp_count = 0
    at_cg_count = 0
    with vcf.open() as f:
        for line in f:
            if line.startswith("#"):
                continue
            snp_count += 1
            parts = line.split("\t")
            if len(parts) >= 5:
                ref, alt = parts[3], parts[4]
                if {ref, alt} in ({"A", "T"}, {"G", "C"}):
                    at_cg_count += 1
    return {
        "vcf_exists": True,
        "snp_count": snp_count,
        "at_cg_remaining": at_cg_count,  # MUST be 0
    }
