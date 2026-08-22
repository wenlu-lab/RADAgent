"""Step 7 — Stacks populations: produces filtered_m4_p80_x0_S1.vcf."""
from pathlib import Path


def comparator(project_root: Path) -> dict:
    vcf = project_root / "filtered_m4_p80_x0_S1_chr.recode.vcf"
    if not vcf.is_file():
        return {"vcf_exists": False}
    header_lines = data_lines = 0
    with vcf.open() as f:
        for line in f:
            if line.startswith("#"):
                header_lines += 1
            else:
                data_lines += 1
                if data_lines > 100_000:
                    break  # don't burn time counting millions of lines
    return {
        "vcf_exists": True,
        "header_line_count": header_lines,
        "first_100k_data_lines_at_least": min(data_lines, 100_000),
    }
