"""Step 2 — process_radtags enzyme filtering."""
from pathlib import Path


def comparator(project_root: Path) -> dict:
    out_dir = project_root / "03-samples"
    if not out_dir.is_dir():
        return {"output_dir_exists": False}
    fq_files = list(out_dir.rglob("*.fq.gz"))
    return {
        "output_dir_exists": True,
        "fq_file_count": len(fq_files),
        "lane_subdirs": len([d for d in out_dir.iterdir() if d.is_dir()]),
    }
