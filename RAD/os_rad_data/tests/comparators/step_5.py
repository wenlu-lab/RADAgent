"""Step 5 — BWA alignment."""
import subprocess
from pathlib import Path


def comparator(project_root: Path) -> dict:
    out_dir = project_root / "04-all_samples"
    bams = sorted(out_dir.glob("*.sorted.bam"))
    bais = sorted(out_dir.glob("*.sorted.bam.bai"))
    empty_bams = sum(1 for b in bams if b.stat().st_size == 0)
    leftover = [p for p in out_dir.glob("*.bam") if not p.name.endswith(".sorted.bam")]
    # Sample 5 BAMs with deterministic ordering for spot-check stats
    sample = bams[:5] if len(bams) >= 5 else bams
    flagstats = []
    for bam in sample:
        try:
            out = subprocess.run(
                ["samtools", "flagstat", str(bam)],
                capture_output=True, text=True, timeout=60, check=True,
            )
            # Parse "X mapped (Y%)"
            for line in out.stdout.splitlines():
                if "mapped (" in line and "primary" not in line:
                    pct = line.split("(")[1].split("%")[0].strip()
                    flagstats.append(float(pct))
                    break
        except (FileNotFoundError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pass
    return {
        "bam_count": len(bams),
        "bai_count": len(bais),
        "empty_bams": empty_bams,
        "no_unsorted_leftover": len(leftover) == 0,
        "min_mapped_pct_in_sample": min(flagstats) if flagstats else None,
    }
