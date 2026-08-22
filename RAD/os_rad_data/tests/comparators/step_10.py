"""Step 10 — LD clumping."""
from pathlib import Path


def comparator(project_root: Path) -> dict:
    ld_vcf = project_root / "filtered_m4_p80_x0_S1_chr.singleton.hwe.maf01.LD.recode.vcf"
    snp_list = project_root / "filtered_m4_p80_x0_S1_chr.singleton.hwe.maf01_LDclump_SNP.txt"
    plink_files = list(project_root.glob("filtered_m4_p80_x0_S1_chr.singleton.hwe.maf01.{bed,bim,fam}"))
    return {
        "ld_pruned_vcf_exists": ld_vcf.is_file(),
        "snp_list_exists": snp_list.is_file(),
        "snp_list_count": len(snp_list.read_text().strip().splitlines()) if snp_list.is_file() else 0,
        "plink_triple_present": len(plink_files) >= 3,
    }
