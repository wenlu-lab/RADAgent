"""Step 1 — Cutadapt trimming."""
from pathlib import Path


def comparator(project_root: Path) -> dict:
    out_dir = project_root / "02-raw" / "trimmed"
    if not out_dir.is_dir():
        return {"output_dir_exists": False}
    files = sorted(out_dir.glob("*.fastq.gz"))
    r1 = [f for f in files if f.name.endswith("_R1.fastq.gz")]
    r2 = [f for f in files if f.name.endswith("_R2.fastq.gz")]
    empties = [f for f in files if f.stat().st_size == 0]
    return {
        "output_dir_exists": True,
        "trimmed_count": len(files),
        "r1_count": len(r1),
        "r2_count": len(r2),
        "empty_files": len(empties),
        "naming_pattern_ok": all("_R" in f.name for f in files),
    }
