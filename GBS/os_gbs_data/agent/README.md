# gbs-agent

Open-source agentic runtime that drives the GBS bioinformatics pipeline using an in-process Qwen3-Coder model loaded directly with Hugging Face `transformers` (no inference server).

## What this is

A thin Python orchestrator that reads `.claude/skills/SKILL.md` files (originally written for Claude Code) and executes them against a self-hosted LLM. The 18 skill files are the single source of truth — they describe pre-flight checks, the script to run, verification, and self-healing for each pipeline step.

## How it works

```
./gbs orchestrator
   │
   ▼
[orchestrator skill, one Python process, model loaded in-process]
   │
   ├── Bash, Read, Write, Edit, Glob, Grep tools
   │
   └── Skill("gbs-5-bwa") ── in-process run_skill() ──▶ [step subagent, fresh context]
                                                          │
                                                          ├── Bash, Read, Grep, Glob
                                                          ▼
                                                     bwa mem ... | samtools ...
```

Each `Skill` call runs `run_skill()` in-process with a brand-new `messages` list — that's how we get isolated context windows per subagent (mirroring Claude Code's behavior) while keeping the 30B model resident in VRAM. The model is a process-wide singleton, so loading it once serves every subagent.

Which tools a subagent may call is gated by the `allowed-tools` frontmatter in its `SKILL.md`. The orchestrator skill is the one granted `Skill`, which is how it spawns the per-step subagents — individual steps can't recurse into other steps. After a step subagent returns, `step_output_check.py` re-verifies the step's on-disk outputs and can override a spurious `FAILURE` when the files are actually valid.

## Install (dev)

```bash
cd /path/to/os_gbs_data        # repo root — where ./gbs and .claude/skills/ live
pip install -e ./agent
```

## Setup (one-time)

See the project root README's "Installation" section. The model loads in-process on the first agent call — there is no server to start.

## Layout

| Path | Purpose |
|---|---|
| `gbs/cli.py` | CLI entry point — `./gbs <subcommand>` |
| `gbs/runtime.py` | The `run_skill` tool-calling loop (context trimming + loop-break nudges) |
| `gbs/step_output_check.py` | Authoritative on-disk output check — overrides a subagent's `FAILURE` when the step's files are actually valid |
| `gbs/skill_loader.py` | Parses SKILL.md frontmatter + body |
| `gbs/llm_client.py` | In-process transformers backend (loads Qwen3-Coder, generates locally) |
| `gbs/model_backend.py` | Process-wide singleton model + tokenizer loader |
| `gbs/qwen3_coder_parser.py` | Parses Qwen3-Coder tool-call markup → structured calls |
| `gbs/llm_types.py` | Shared `TokenUsage` / `ToolCall` / `ChatMessage` dataclasses |
| `gbs/transcript.py` | JSONL transcript writer (Claude Code-shaped) |
| `gbs/config.py` | Centralized config (env-overridable) |
| `gbs/tools/` | Tool implementations (Bash, Read, Write, Edit, Glob, Grep, Skill) |
| `gbs/viewer/` | The `./gbs view` TUI — `model.py` parses `.gbs/` runs/steps/events, `app.py` is the Textual 3-pane UI |
| `tests/` | Unit tests (run with `pytest agent/tests/`) |

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `GBS_PROJECT_ROOT` | (auto-detect) | Project root containing `.claude/skills/` |
| `GBS_MODEL_ID` | `Qwen/Qwen3-Coder-30B-A3B-Instruct` | HF model id loaded in-process (bf16; `-FP8` needs compute ≥8.9) |
| `GBS_TORCH_DTYPE` | `auto` | dtype for `from_pretrained` (e.g. `bfloat16`) |
| `GBS_DEVICE_MAP` | `auto` | `device_map` for `from_pretrained` |
| `GBS_MAX_CONTEXT_TOKENS` | `32768` | Effective context window (drives message trimming) |
| `GBS_MODEL_LABEL` | `qwen3-coder` | Short label recorded in transcripts |
| `GBS_MAX_TOOL_CALLS` | `200` | Hard cap per skill invocation |
| `GBS_MAX_NUDGES` | `3` | Max "you're looping — summarize" nudges before a stuck subagent is forced to wrap up |
| `GBS_BASH_MAX_TIMEOUT_MS` | `3600000` | Max Bash timeout (1 hour) |
| `GBS_SUBAGENT_TIMEOUT_SEC` | `86400` | (unused since subagents run in-process) |

## Tests

```bash
# Unit tests (no model required — pure logic, e.g. the tool-call parser)
pytest agent/tests/

# Integration / parity tests (load the in-process model; needs the GPU)
pytest tests/test_step_parity.py

# End-to-end (clean run + validation, ~4h)
pytest tests/test_e2e.py
```

The parity tests compare each step's outputs against `tests/reference/step_N.json`.
Regenerate those fixtures from a known-good run with `./gbs test capture-reference`.
