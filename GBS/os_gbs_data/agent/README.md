# gbs-agent

Open-source agentic runtime that drives the GBS bioinformatics pipeline using a locally-served Qwen3-Coder model on vLLM.

## What this is

A thin Python orchestrator that reads `.claude/skills/SKILL.md` files (originally written for Claude Code) and executes them against a self-hosted LLM. The 18 skill files are the single source of truth — they describe pre-flight checks, the script to run, verification, and self-healing for each pipeline step.

## How it works

```
./gbs orchestrator
   │
   ▼
[orchestrator skill, in a Python process, talking to vLLM]
   │
   ├── Bash, Read, Write, Edit, Glob, Grep tools
   │
   └── Skill("gbs-5-bwa") ── spawns a subprocess ──▶ [step subagent, fresh context]
                                                          │
                                                          ├── Bash, Read, Grep, Glob
                                                          ▼
                                                     bwa mem ... | samtools ...
```

Each `Skill` call is a fresh subprocess — that's how we get isolated context windows per subagent (mirroring Claude Code's behavior).

## Install (dev)

```bash
cd /home/mreddy1/os_gbs_data
pip install -e ./agent
```

## Setup (one-time)

See the project root README's "Open-source pipeline (vLLM)" section.

## Layout

| Path | Purpose |
|---|---|
| `gbs/cli.py` | CLI entry point — `./gbs <subcommand>` |
| `gbs/runtime.py` | The `run_skill` tool-calling loop |
| `gbs/skill_loader.py` | Parses SKILL.md frontmatter + body |
| `gbs/llm_client.py` | Hugging Face InferenceClient wrapper pointed at vLLM |
| `gbs/transcript.py` | JSONL transcript writer (Claude Code-shaped) |
| `gbs/config.py` | Centralized config (env-overridable) |
| `gbs/tools/` | Tool implementations (Bash, Read, Write, Edit, Glob, Grep, Skill) |
| `tests/` | Unit tests (run with `pytest agent/tests/`) |

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `GBS_PROJECT_ROOT` | (auto-detect) | Project root containing `.claude/skills/` |
| `GBS_VLLM_URL` | `http://127.0.0.1:8000/v1` | vLLM endpoint |
| `GBS_MODEL_NAME` | `qwen3-coder` | `--served-model-name` from vLLM |
| `GBS_MAX_TOOL_CALLS` | `200` | Hard cap per skill invocation |
| `GBS_BASH_MAX_TIMEOUT_MS` | `3600000` | Max Bash timeout (1 hour) |
| `GBS_SUBAGENT_TIMEOUT_SEC` | `86400` | Max subprocess timeout for Skill tool |

## Tests

```bash
# Unit tests (no vLLM required)
pytest agent/tests/

# Integration / parity tests (vLLM must be running)
pytest tests/test_step_parity.py

# End-to-end (clean run + validation, ~4h)
pytest tests/test_e2e.py
```
