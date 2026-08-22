"""Step 6 — gstacks genotyping."""
from pathlib import Path


def comparator(project_root: Path) -> dict:
    stacks = project_root / "05-stacks"
    if not stacks.is_dir():
        return {"stacks_dir_exists": False}
    catalog_files = list(stacks.glob("catalog.*"))
    gstacks_logs = list(stacks.glob("gstacks.*"))
    return {
        "stacks_dir_exists": True,
        "catalog_file_count": len(catalog_files),
        "gstacks_log_present": any("log" in f.name for f in gstacks_logs),
    }
