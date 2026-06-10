"""Parse .claude/skills/<name>/SKILL.md files into Skill objects."""
from __future__ import annotations
import re
from dataclasses import dataclass, field
from pathlib import Path
import yaml
from gbs.config import Config


class SkillNotFound(Exception):
    pass


@dataclass
class Skill:
    name: str
    description: str
    body: str
    allowed_tools: list[str] = field(default_factory=list)
    model_label: str = "sonnet"            # legacy frontmatter — kept for telemetry
    model_alias: str = "qwen3-coder"       # the actual served model on vLLM
    context: str = ""                       # "fork" or empty
    argument_hint: str = ""
    source_path: Path | None = None


_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n(.*)", re.DOTALL)
# Simple key: value line (value may contain colons — take everything after first ": ")
_KV_LINE_RE = re.compile(r"^([A-Za-z][A-Za-z0-9_-]*):\s*(.*)")


def _parse_frontmatter(fm_raw: str) -> dict:
    """Parse SKILL.md frontmatter line-by-line.

    Each line must be `key: value`. Empty lines and `#` comments are skipped.
    Anything else raises ValueError (fail loudly, do not silently drop content).

    Values that start with a YAML structural character ([, {, ', ") are parsed
    by yaml.safe_load (so lists and quoted strings work). All other values are
    kept as raw strings — this preserves descriptions containing bare colons,
    which YAML would otherwise misinterpret as nested maps.

    Block scalars (| and >) are not supported and raise ValueError, because
    handling them correctly would require continuation-line tracking that we
    don't need for current SKILL.md formats.
    """
    result: dict = {}
    for raw_line in fm_raw.splitlines():
        line = raw_line.rstrip()
        if not line or line.lstrip().startswith("#"):
            continue
        m = _KV_LINE_RE.match(line)
        if not m:
            raise ValueError(f"Cannot parse SKILL.md frontmatter line: {line!r}")
        key, value = m.group(1), m.group(2)
        v = value.strip()
        if not v:
            result[key] = ""
            continue
        if v in ("|", ">"):
            raise ValueError(
                f"Block scalar ({v!r}) not supported in SKILL.md frontmatter for key {key!r}; "
                f"use single-line key:value or a quoted string."
            )
        if v[0] in "[{'\"":
            try:
                result[key] = yaml.safe_load(v)
            except yaml.YAMLError:
                # If structural-looking value fails to parse, keep raw
                result[key] = value
        else:
            # Plain string value — keep as-is to preserve colons, etc.
            result[key] = value
    return result


def load_skill(name: str, config: Config | None = None) -> Skill:
    """Load a skill by name from `<project_root>/.claude/skills/<name>/SKILL.md`."""
    cfg = config or Config.load()
    skill_path = cfg.skills_dir / name / "SKILL.md"
    if not skill_path.is_file():
        raise SkillNotFound(f"No SKILL.md at {skill_path}")
    text = skill_path.read_text(encoding="utf-8")
    m = _FRONTMATTER_RE.match(text)
    if not m:
        raise ValueError(f"{skill_path} missing YAML frontmatter (--- ... ---)")
    fm_raw, body = m.group(1), m.group(2)
    fm = _parse_frontmatter(fm_raw)
    allowed = fm.get("allowed-tools")
    if allowed is None or allowed == "":
        allowed_list: list[str] = []
    elif isinstance(allowed, str):
        allowed_list = [t.strip() for t in allowed.split(",") if t.strip()]
    elif isinstance(allowed, list):
        allowed_list = [str(t).strip() for t in allowed if str(t).strip()]
    else:
        raise ValueError(f"allowed-tools must be string or list, got {type(allowed).__name__}")
    return Skill(
        name=fm.get("name", name),
        description=fm.get("description", ""),
        body=body.strip(),
        allowed_tools=allowed_list,
        model_label=fm.get("model", "sonnet"),
        model_alias=cfg.model_label,
        context=fm.get("context", ""),
        argument_hint=fm.get("argument-hint", ""),
        source_path=skill_path,
    )


def list_skills(config: Config | None = None) -> list[str]:
    """Return all skill names available under .claude/skills/."""
    cfg = config or Config.load()
    return sorted(p.parent.name for p in cfg.skills_dir.glob("*/SKILL.md"))


def build_system_prompt(skill: Skill, tool_descriptions: dict[str, str]) -> str:
    """Build the system prompt for the LLM from a Skill and tool descriptions."""
    parts = [f"You are {skill.name}. {skill.description}", "", skill.body]
    allowed_with_desc = [
        (t, tool_descriptions[t]) for t in skill.allowed_tools if t in tool_descriptions
    ]
    if allowed_with_desc:
        parts.extend(["", "---", "You have access to the following tools (call them via the standard tool-call mechanism):"])
        for tool_name, desc in allowed_with_desc:
            parts.append(f"- {tool_name}: {desc}")
        parts.extend([
            "",
            "---",
            "BASH BLOCKS IN THE SKILL BODY ARE ATOMIC (mandatory):",
            "- When the skill body shows a fenced ```bash``` code block, you MUST run that whole block as ONE single Bash tool call. Pass the entire block (including its `for`/`while`/`xargs` loops) as the `command` argument verbatim.",
            "- Do NOT translate a bash for-loop into N separate Grep/Read tool calls. Do NOT iterate over samples by calling Grep/Read once per file. The bash interpreter does the loop; your job is to invoke bash once.",
            "- Specifically: a verification step that says \"spot-check 5 random lanes\" with a `for d in $(... | head -5); do grep ...; done` block is ONE Bash call returning 5 grep results — not 5 Grep tool calls, and definitely not one Grep per lane in the project.",
            "",
            "---",
            "DATA FILES (mandatory) — the Read tool is for SOURCE CODE only:",
            "- NEVER use the Read tool on bioinformatics data files: `.vcf`, `.bam`, `.sam`, `.fastq`, `.fastq.gz`, `.fasta`, `.fa`, `.fa.gz`, `.tsv`, `.bed`, `.bcf`, `.gff`, `.log` >5 MB. These can be hundreds of MB to multi-GB.",
            "- To inspect or verify these files, use Bash with: `wc -l`, `grep -c`, `grep -cv '^#'`, `head -20`, `tail -20`, `awk`, `zcat … | head`. Each is a SINGLE Bash tool call that returns the answer immediately.",
            "- NEVER `Read` a file in chunks at increasing offsets to 'verify content'. If the skill body's verification block uses `grep -cv '^#' file.vcf` to count variant lines, run THAT bash command; do not Read the VCF.",
            "- The Read tool is only appropriate for skill files, scripts, small text outputs (< 5000 lines AND < 5 MB). Everything else: Bash.",
            "",
            "---",
            "WORKING DIRECTORY (mandatory):",
            "- Your current working directory IS the project root. Use the relative paths the skill body uses (e.g. `04-all_samples/`, `00-scripts/foo.sh`).",
            "- NEVER prepend an absolute path or `cd` to a different directory. If the skill body mentions `gbs_data/` as the project name, that is the historical project name — your cwd is already the right project root, so `gbs_data/foo` means just `foo` for you.",
            "- Use `pwd` once at the start if you need to confirm; do not run it repeatedly.",
            "",
            "---",
            "TERMINATION RULE (mandatory):",
            "- The skill body above tells you to report SUCCESS / FAILURE / FIX_APPLIED / UNFIXABLE when done, and specifies the exact completion criteria for THIS step (e.g. a log marker like 'gstacks is done.', an output line count, a non-empty VCF, etc.). Follow those criteria literally.",
            "- For long-running scripts that write output files progressively (gstacks, BWA, populations, etc.): file existence alone is NOT proof of completion. Wait for the explicit completion signal the skill body names — typically a log marker AND a successful exit code from the launching script. Only after BOTH are confirmed should you count records or report metrics.",
            "- When you have satisfied the skill body's completion criteria (or determined the work cannot proceed), STOP calling tools and emit a final assistant message. The first non-empty line must be:",
            "  **Status**: SUCCESS",
            "  (or FAILURE / FIX_APPLIED / UNFIXABLE)",
            "- Do NOT downgrade to FAILURE based on a secondary probe (e.g. a directory listing returning empty) that contradicts a primary check that already confirmed completion. If two checks disagree, prefer the one named in the skill body and re-read the earlier tool results before concluding failure.",
            "- Do not re-run a verification command you have already run. One check of each thing is enough; two is the absolute maximum.",
            "- Tool output is finite. Avoid recursive `Grep` over the whole project (e.g. `path: \".\"`); always pass a specific subdirectory or `glob:` filter.",
            "- Once you emit the structured summary you are done. Do not call any more tools after the summary.",
        ])
    return "\n".join(parts)
