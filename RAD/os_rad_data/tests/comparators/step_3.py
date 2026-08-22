"""Step 3 — Rename samples to per-sample names."""
from pathlib import Path


def comparator(project_root: Path) -> dict:
    out_dir = project_root / "04-all_samples"
    if not out_dir.is_dir():
        return {"output_dir_exists": False}
    fq1 = sorted(out_dir.glob("*.1.fq.gz"))
    fq2 = sorted(out_dir.glob("*.2.fq.gz"))
    return {
        "output_dir_exists": True,
        "r1_count": len(fq1),
        "r2_count": len(fq2),
        "pair_balance_ok": len(fq1) == len(fq2),
    }
