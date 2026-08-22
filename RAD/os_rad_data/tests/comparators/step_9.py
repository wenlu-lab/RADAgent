"""Step 9 — SNP duplication detection + HWE filter."""
from pathlib import Path


def comparator(project_root: Path) -> dict:
    singleton_vcf = project_root / "filtered_m4_p80_x0_S1_chr.recode.singleton.vcf"
    hwe_vcf = list(project_root.glob("filtered_m4_p80_x0_S1_chr.singleton.hwe*.vcf"))
    snp_dup_info = project_root / "snp_duplication_info.txt"
    return {
        "singleton_vcf_exists": singleton_vcf.is_file(),
        "singleton_vcf_size_kb": singleton_vcf.stat().st_size // 1024 if singleton_vcf.is_file() else 0,
        "hwe_filtered_vcf_exists": len(hwe_vcf) > 0,
        "snp_duplication_info_exists": snp_dup_info.is_file(),
    }
