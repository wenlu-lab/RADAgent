"""Step 0 — Prepare Lane Info."""
from pathlib import Path


def comparator(project_root: Path) -> dict:
    f = project_root / "01-info_files" / "lane_info.txt"
    if not f.is_file():
        return {"file_exists": False}
    lines = f.read_text().strip().splitlines()
    return {
        "file_exists": True,
        "line_count": len(lines),
        "all_lanes_have_extension": all(line.endswith(".fastq.gz") for line in lines if line),
    }
