"""Authoritative per-step on-disk output verification.

Used by SkillTool to override subagent FAILURE reports when the bioinformatics
work actually succeeded. Each step's check is a function that returns
(is_valid: bool, detail: str). `detail` is shown in the runtime override message.

This is the runtime equivalent of the orchestrator SKILL's section 3c-bis —
moved here because the Phi-4-driven orchestrator was ignoring the SKILL.md
instruction. The runtime check always runs.
"""
from __future__ import annotations
import os
from pathlib import Path
from typing import Callable


def project_root_from(session_dir: str | Path) -> Path:
    """Recover project root from a session_dir path (.rad/transcripts/<id>/)."""
    p = Path(session_dir).resolve()
    # session_dir = <root>/.rad/transcripts/<id>
    # walk up to <root>
    for ancestor in [p, *p.parents]:
        if (ancestor / ".claude" / "skills").is_dir():
            return ancestor
    # Fallback to env / cwd
    env = os.environ.get("RAD_PROJECT_ROOT")
    if env:
        return Path(env).resolve()
    return Path.cwd().resolve()


def _expected_lanes(root: Path) -> int:
    lf = root / "01-info_files" / "lane_info.txt"
    if not lf.is_file():
        return 0
    return sum(1 for _ in lf.open())


def _file_nonempty(p: Path) -> bool:
    try:
        return p.stat().st_size > 0
    except (FileNotFoundError, OSError):
        return False


def _count_glob(root: Path, pattern: str) -> int:
    return len(list(root.glob(pattern)))


def _no_empty(root: Path, pattern: str) -> bool:
    for p in root.glob(pattern):
        if p.stat().st_size == 0:
            return False
    return True


def _vcf_has_variants(p: Path) -> bool:
    if not _file_nonempty(p):
        return False
    try:
        with p.open() as f:
            for line in f:
                if not line.startswith("#"):
                    return True
        return False
    except OSError:
        return False


def _check_step_0(root: Path) -> tuple[bool, str]:
    p = root / "01-info_files" / "lane_info.txt"
    if not _file_nonempty(p):
        return False, "lane_info.txt missing or empty"
    el = _expected_lanes(root)
    return True, f"lane_info.txt has {el} lanes"


def _check_step_1(root: Path) -> tuple[bool, str]:
    el = _expected_lanes(root)
    if el == 0:
        return False, "EXPECTED_LANES unknown (step 0 output missing)"
    need = el * 2
    n = _count_glob(root, "02-raw/trimmed/*.fastq.gz")
    if n < need:
        return False, f"02-raw/trimmed/*.fastq.gz: {n}/{need}"
    if not _no_empty(root, "02-raw/trimmed/*.fastq.gz"):
        return False, "some trimmed FASTQ files are empty"
    return True, f"02-raw/trimmed/*.fastq.gz: {n}/{need}, all non-empty"


def _check_step_2(root: Path) -> tuple[bool, str]:
    el = _expected_lanes(root)
    if el == 0:
        return False, "EXPECTED_LANES unknown"
    samples_dir = root / "03-samples"
    if not samples_dir.is_dir():
        return False, "03-samples/ missing"
    lane_dirs = [d for d in samples_dir.iterdir() if d.is_dir()]
    if len(lane_dirs) < el:
        return False, f"03-samples/*/: {len(lane_dirs)}/{el}"
    if not _no_empty(root, "03-samples/*/*.fq.gz"):
        return False, "some lane .fq.gz files are empty"
    return True, f"03-samples/*/: {len(lane_dirs)} lane dirs, all .fq.gz non-empty"


def _check_step_3(root: Path) -> tuple[bool, str]:
    el = _expected_lanes(root)
    if el == 0:
        return False, "EXPECTED_LANES unknown"
    need = el * 2
    n = _count_glob(root, "04-all_samples/*.fq.gz")
    if n < need:
        return False, f"04-all_samples/*.fq.gz: {n}/{need}"
    return True, f"04-all_samples/*.fq.gz: {n}/{need}"


def _check_step_4(root: Path) -> tuple[bool, str]:
    p = root / "01-info_files" / "population_map.txt"
    if not _file_nonempty(p):
        return False, "population_map.txt missing or empty"
    return True, "population_map.txt present and non-empty"


def _check_step_5(root: Path) -> tuple[bool, str]:
    el = _expected_lanes(root)
    if el == 0:
        return False, "EXPECTED_LANES unknown"
    n = _count_glob(root, "04-all_samples/*.sorted.bam")
    if n < el:
        return False, f"04-all_samples/*.sorted.bam: {n}/{el}"
    if not _no_empty(root, "04-all_samples/*.sorted.bam"):
        return False, "some sorted BAMs are empty"
    n_bai = _count_glob(root, "04-all_samples/*.sorted.bam.bai")
    if n_bai < el:
        return False, f"only {n_bai}/{el} BAM indexes present (.bai missing)"
    return True, f"{n} sorted BAMs + {n_bai} indexes, all non-empty"


def _check_step_6(root: Path) -> tuple[bool, str]:
    cat_fa = root / "05-stacks" / "catalog.fa.gz"
    cat_calls = root / "05-stacks" / "catalog.calls"
    log = root / "10-log_files" / "gstacks_run.log"
    if not _file_nonempty(cat_fa):
        return False, "05-stacks/catalog.fa.gz missing or empty"
    if not _file_nonempty(cat_calls):
        return False, "05-stacks/catalog.calls missing or empty"
    if log.is_file():
        try:
            if "gstacks is done" not in log.read_text():
                return False, "gstacks_run.log does not contain 'gstacks is done'"
        except OSError:
            pass
    return True, f"catalog.fa.gz ({cat_fa.stat().st_size}B), catalog.calls ({cat_calls.stat().st_size}B), log shows gstacks done"


def _check_step_7(root: Path) -> tuple[bool, str]:
    p = root / "05-stacks" / "populations.snps.vcf"
    if not _vcf_has_variants(p):
        return False, "populations.snps.vcf missing, empty, or no variant lines"
    return True, f"populations.snps.vcf present with variant data ({p.stat().st_size}B)"


def _check_step_8(root: Path) -> tuple[bool, str]:
    p = root / "filtered_m4_p80_x0_S1_chr.recode.vcf"
    if not _vcf_has_variants(p):
        return False, "filtered_m4_p80_x0_S1_chr.recode.vcf missing or no variants"
    return True, f"step-8 chr-filtered VCF present"


def _check_step_9(root: Path) -> tuple[bool, str]:
    p = root / "filtered_m4_p80_x0_S1_chr.singleton.hwe.recode.vcf"
    if not _vcf_has_variants(p):
        return False, "filtered_m4_p80_x0_S1_chr.singleton.hwe.recode.vcf missing or no variants"
    return True, "step-9 singleton+HWE VCF present"


def _check_step_10(root: Path) -> tuple[bool, str]:
    p = root / "filtered_m4_p80_x0_S1_chr.singleton.hwe.maf01.LD.recode.vcf"
    if not _vcf_has_variants(p):
        return False, "step-10 LD-clumped VCF missing or no variants"
    return True, "step-10 LD-clumped VCF present"


def _check_step_11(root: Path) -> tuple[bool, str]:
    for name in [
        "filtered_m4_p80_x0_S1_chr.singleton.hwe.maf01.LD.no_AT_CG.vcf",
        "filtered_m4_p80_x0_S1_chr.singleton.hwe.maf01.LD.no_AT_CG.recode.vcf",
    ]:
        p = root / name
        if _vcf_has_variants(p):
            return True, f"{name} present with variants"
    return False, "step-11 no_AT_CG VCF missing or empty"


def _check_step_12(root: Path) -> tuple[bool, str]:
    p = root / "filtered_m4_p80_x0_S1_chr.singleton.hwe.maf10.LD.no_AT_CG.recode.vcf"
    if not _vcf_has_variants(p):
        return False, "step-12 MAF-filtered VCF missing or no variants"
    return True, "step-12 MAF-filtered VCF present"


def _check_step_13(root: Path) -> tuple[bool, str]:
    p = root / "filtered_flanking.vcf"
    if not _vcf_has_variants(p):
        return False, "filtered_flanking.vcf missing or no variants"
    return True, "filtered_flanking.vcf present with variants"


def _check_step_14(root: Path) -> tuple[bool, str]:
    p = root / "blast_output.txt"
    if not _file_nonempty(p):
        return False, "blast_output.txt missing or empty"
    return True, "blast_output.txt present and non-empty"


def _check_step_15(root: Path) -> tuple[bool, str]:
    p = root / "final_snp_panel.vcf"
    if not _vcf_has_variants(p):
        return False, "final_snp_panel.vcf missing or no variants"
    n = sum(1 for line in p.open() if not line.startswith("#"))
    return True, f"final_snp_panel.vcf present with {n} SNPs"


_CHECKS: dict[str, Callable[[Path], tuple[bool, str]]] = {
    "rad-0-lane-info":     _check_step_0,
    "rad-1-cutadapt":      _check_step_1,
    "rad-2-radtags":       _check_step_2,
    "rad-3-rename":        _check_step_3,
    "rad-4-popmap":        _check_step_4,
    "rad-5-bwa":           _check_step_5,
    "rad-6-gstacks":       _check_step_6,
    "rad-7-populations":   _check_step_7,
    "rad-8-vcf-filter":    _check_step_8,
    "rad-9-snp-dup-hwe":   _check_step_9,
    "rad-10-ld-clump":     _check_step_10,
    "rad-11-remove-atgc":  _check_step_11,
    "rad-12-maf-filter":   _check_step_12,
    "rad-13-flanking":     _check_step_13,
    "rad-14-blast-map":    _check_step_14,
    "rad-15-even-dist":    _check_step_15,
}


def outputs_valid(skill_name: str, root: Path) -> tuple[bool, str]:
    """Return (True, detail) if the named step's outputs are present and valid
    on disk. (False, reason) otherwise. For non-pipeline skills (debugger,
    orchestrator, etc.), returns (False, 'no check defined')."""
    fn = _CHECKS.get(skill_name)
    if fn is None:
        return False, f"no on-disk check defined for {skill_name}"
    try:
        return fn(root)
    except Exception as e:
        return False, f"check raised {type(e).__name__}: {e}"
