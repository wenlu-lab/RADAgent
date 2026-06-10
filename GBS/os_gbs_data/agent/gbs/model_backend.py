"""Process-wide singleton loader for the in-process model.

The 30B weights (~60 GB bf16 on an A100) are loaded exactly once per process and
shared by every LLMClient — this is what makes the single-process architecture
viable (one resident copy, in-process subagents)."""
from __future__ import annotations
import sys
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

_CACHE: dict[str, tuple] = {}


def _resolve_dtype(name: str):
    if name == "auto":
        return "auto"
    return getattr(torch, name)


def get_model(model_id: str, torch_dtype: str = "auto", device_map: str = "auto"):
    """Return (model, tokenizer), loading once and caching by (id, dtype, device_map)."""
    key = f"{model_id}|{torch_dtype}|{device_map}"
    if key not in _CACHE:
        print(f"Loading {model_id} into VRAM (first call; can take a few minutes)…", file=sys.stderr)
        tokenizer = AutoTokenizer.from_pretrained(model_id)
        model = AutoModelForCausalLM.from_pretrained(
            model_id,
            torch_dtype=_resolve_dtype(torch_dtype),
            device_map=device_map,
        )
        model.eval()
        _CACHE[key] = (model, tokenizer)
    return _CACHE[key]
