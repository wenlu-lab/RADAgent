"""Comparator framework: each step has a comparator(out_dir) -> dict + a reference fixture."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
from typing import Any


def md5_sorted(items) -> str:
    h = hashlib.md5()
    for x in sorted(items):
        h.update(x.encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def md5_file(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def assert_matches_reference(actual: dict[str, Any], reference: dict[str, Any], *, step: int) -> None:
    """Compare actual comparator output against the reference fixture.

    Reference values can be:
      - scalar: must match exactly
      - {"min": X, "max": Y}: actual must fall in range
      - {"expected": V}: must equal V (same as scalar; explicit form)
      - {"per_chrom_min": M, "per_chrom_max": N}: applies to a dict-of-counts; every value must be in range
    """
    errors = []
    for key, ref in reference.items():
        if key not in actual:
            errors.append(f"missing key in actual: {key}")
            continue
        a = actual[key]
        if isinstance(ref, dict) and "min" in ref and "max" in ref:
            if not (ref["min"] <= a <= ref["max"]):
                errors.append(f"{key}: {a} not in [{ref['min']}, {ref['max']}]")
        elif isinstance(ref, dict) and "expected" in ref:
            if a != ref["expected"]:
                errors.append(f"{key}: {a!r} != expected {ref['expected']!r}")
        elif isinstance(ref, dict) and "per_chrom_min" in ref:
            assert isinstance(a, dict), f"{key}: expected dict for per_chrom comparison, got {type(a)}"
            for chrom, count in a.items():
                if not (ref["per_chrom_min"] <= count <= ref["per_chrom_max"]):
                    errors.append(f"{key}[{chrom}]: {count} not in [{ref['per_chrom_min']}, {ref['per_chrom_max']}]")
        else:
            if a != ref:
                errors.append(f"{key}: {a!r} != {ref!r}")
    if errors:
        msg = f"Step {step} parity check failed:\n  " + "\n  ".join(errors)
        raise AssertionError(msg)


def load_reference(reference_dir: Path, step: int) -> dict:
    p = reference_dir / f"step_{step}.json"
    if not p.is_file():
        raise FileNotFoundError(f"No reference fixture: {p}. Run `./rad test capture-reference` first.")
    return json.loads(p.read_text())
