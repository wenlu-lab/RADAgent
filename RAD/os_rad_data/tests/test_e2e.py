"""End-to-end test: clean everything, run the full orchestrator, validate final output."""
import csv
import datetime
import subprocess
import sys

import pytest

from tests.comparators._base import assert_matches_reference, load_reference
from tests.comparators import step_15


def _human_time(secs: float) -> str:
    secs = int(secs)
    if secs < 60:
        return f"{secs}s"
    if secs < 3600:
        return f"{secs // 60}m {secs % 60}s"
    return f"{secs // 3600}h {(secs % 3600) // 60}m"


@pytest.mark.timeout(7 * 3600)  # cap at 7h
def test_full_pipeline_end_to_end(project_root, gpu_available, reference_dir):
    """Clean everything, run ./rad orchestrator, validate final_snp_panel.vcf."""
    # 1. Clean
    subprocess.run(["bash", "clean_pipeline.sh", "all"], cwd=project_root, check=True)

    # 2. Run orchestrator
    start = datetime.datetime.now()
    proc = subprocess.run(
        ["./rad", "orchestrator"],
        cwd=project_root,
        capture_output=True, text=True,
    )
    elapsed = (datetime.datetime.now() - start).total_seconds()

    # 3. Build a report regardless of pass/fail
    report_dir = project_root / "tests" / "_e2e_reports"
    report_dir.mkdir(exist_ok=True)
    report_file = report_dir / f"{start.strftime('%Y-%m-%d-%H%M%S')}.md"

    timing_csv = project_root / "rad-pipeline-timing.csv"
    timing_rows = []
    if timing_csv.is_file():
        with timing_csv.open() as f:
            timing_rows = list(csv.DictReader(f))

    with report_file.open("w") as f:
        f.write(f"# E2E Run — {start.isoformat()}\n\n")
        f.write(f"- Wall-clock: **{_human_time(elapsed)}**\n")
        f.write(f"- Exit code: {proc.returncode}\n\n")
        f.write("## Per-step timing\n\n| Step | Title | Status | Duration | Tokens |\n|---|---|---|---|---|\n")
        for r in timing_rows:
            try:
                dur = _human_time(int(r.get("DURATION_SEC", 0)))
                tok = r.get("TOKENS_TOTAL", "0")
                f.write(f"| {r['STEP']} | {r['TITLE']} | {r['STATUS']} | {dur} | {tok} |\n")
            except (KeyError, ValueError) as e:
                f.write(f"| ? | malformed row ({e}) | ? | ? | ? |\n")

    print(f"E2E report: {report_file}", file=sys.stderr)

    # 4. Assert success
    assert proc.returncode == 0, f"Orchestrator returned {proc.returncode}.\nSTDOUT tail:\n{proc.stdout[-3000:]}\nSTDERR tail:\n{proc.stderr[-2000:]}"

    # 5. Step-15 comparator against reference
    actual = step_15.comparator(project_root)
    reference = load_reference(reference_dir, 15)
    assert_matches_reference(actual, reference, step=15)
