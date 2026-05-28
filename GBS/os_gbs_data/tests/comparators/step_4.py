"""Step 4 — Population map."""
from pathlib import Path


def comparator(project_root: Path) -> dict:
    f = project_root / "01-info_files" / "population_map.txt"
    if not f.is_file():
        return {"file_exists": False}
    lines = f.read_text().strip().splitlines()
    samples = set()
    pops = set()
    for line in lines:
        parts = line.split("\t")
        if len(parts) >= 2:
            samples.add(parts[0])
            pops.add(parts[1])
    return {
        "file_exists": True,
        "line_count": len(lines),
        "unique_samples": len(samples),
        "unique_populations": len(pops),
    }
