"""Shared fixtures for project-level integration/parity tests."""
import os
import shutil
import subprocess
from pathlib import Path
import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def project_root() -> Path:
    return PROJECT_ROOT


@pytest.fixture(scope="session")
def gpu_available():
    """Skip the module unless a CUDA GPU with enough free VRAM is present.
    These tests run ./rad run, which loads the ~28 GB model in-process."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pytest.skip("nvidia-smi unavailable — no GPU to load the in-process model")
    if out.returncode != 0:
        pytest.skip("nvidia-smi failed — cannot verify GPU for the in-process model")
    free_mb = int(out.stdout.strip().splitlines()[0])
    if free_mb < 60000:
        pytest.skip(f"GPU has only {free_mb}MB free; need ~60GB to load the model in-process")


@pytest.fixture
def clean_step(project_root):
    """Returns a function that runs clean_pipeline.sh for a given step."""
    def _clean(n: int):
        subprocess.run(["bash", "clean_pipeline.sh", str(n)], cwd=project_root, check=True)
    return _clean


@pytest.fixture
def run_step(project_root, gpu_available):
    """Returns a function that runs a single skill via ./rad run."""
    def _run(skill_name: str, args: str = "") -> int:
        cmd = ["./rad", "run", skill_name]
        if args:
            cmd.append(args)
        result = subprocess.run(cmd, cwd=project_root)
        return result.returncode
    return _run


@pytest.fixture(scope="session")
def reference_dir(project_root) -> Path:
    return project_root / "tests" / "reference"


@pytest.fixture(scope="session")
def snapshots_dir(project_root) -> Path:
    d = project_root / "tests" / "_snapshots"
    d.mkdir(exist_ok=True)
    return d
