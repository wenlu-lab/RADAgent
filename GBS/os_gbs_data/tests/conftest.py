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
def vllm_alive():
    """Ensure vLLM is reachable; skip the whole module if not."""
    from urllib.request import Request, urlopen
    from urllib.error import URLError
    try:
        with urlopen(Request("http://127.0.0.1:8000/v1/models"), timeout=3) as r:
            if r.status != 200:
                pytest.skip("vLLM not healthy")
    except URLError:
        pytest.skip("vLLM not reachable on localhost:8000 — start with ./gbs serve")


@pytest.fixture
def clean_step(project_root):
    """Returns a function that runs clean_pipeline.sh for a given step."""
    def _clean(n: int):
        subprocess.run(["bash", "clean_pipeline.sh", str(n)], cwd=project_root, check=True)
    return _clean


@pytest.fixture
def run_step(project_root, vllm_alive):
    """Returns a function that runs a single skill via ./gbs run."""
    def _run(skill_name: str, args: str = "") -> int:
        cmd = ["./gbs", "run", skill_name]
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
