"""Per-step parity test. For each step:
  1. Snapshot current outputs (one-time, for safety/rollback).
  2. Clean the step.
  3. Run the step under our orchestrator-less single-skill mode (./rad run rad-N-...).
  4. Compute comparator on new outputs.
  5. Compare against tests/reference/step_N.json.
"""
import importlib
import pytest

from tests.comparators._base import assert_matches_reference, load_reference


# Step name registry (matches rad-orchestrator/SKILL.md table)
STEP_SKILLS = {
    0: "rad-0-lane-info",
    1: "rad-1-cutadapt",
    2: "rad-2-radtags",
    3: "rad-3-rename",
    4: "rad-4-popmap",
    5: "rad-5-bwa",
    6: "rad-6-gstacks",
    7: "rad-7-populations",
    8: "rad-8-vcf-filter",
    9: "rad-9-snp-dup-hwe",
    10: "rad-10-ld-clump",
    11: "rad-11-remove-atgc",
    12: "rad-12-maf-filter",
    13: "rad-13-flanking",
    14: "rad-14-blast-map",
    15: "rad-15-even-dist",
}


def _comparator(step: int):
    return importlib.import_module(f"tests.comparators.step_{step}").comparator


@pytest.mark.parametrize(
    "step",
    list(STEP_SKILLS.keys()),
    ids=[f"{n}-{s}" for n, s in STEP_SKILLS.items()],
)
def test_step_parity(step, project_root, gpu_available, clean_step, run_step, reference_dir):
    """Run step N under the OS orchestrator; compare outputs against reference."""
    skill_name = STEP_SKILLS[step]
    reference = load_reference(reference_dir, step)

    # Clean prior outputs for THIS step only (upstream outputs remain as inputs).
    clean_step(step)

    # Run via single-skill mode
    rc = run_step(skill_name)
    assert rc == 0, f"Skill {skill_name} returned non-zero exit code {rc}"

    # Compute comparator on the freshly produced outputs
    comparator_fn = _comparator(step)
    actual = comparator_fn(project_root)
    assert_matches_reference(actual, reference, step=step)
