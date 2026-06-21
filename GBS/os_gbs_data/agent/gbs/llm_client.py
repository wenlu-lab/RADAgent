"""In-process LLM client: loads Qwen3-Coder via transformers and generates
locally. No server. Public types (TokenUsage/ToolCall/ChatMessage) are
re-exported here because transcript.py imports them from this module.

Tool calling: apply_chat_template injects the tool schemas; the model emits
Qwen3-Coder tool-call markup; qwen3_coder_parser turns it back into structured
calls. A `</tool_call>` stop string enforces one tool call per turn (the loop in
runtime.py handles multi-turn), preventing the model from hallucinating tool
output after a call."""
from __future__ import annotations
import torch
from gbs.llm_types import TokenUsage, ToolCall, ChatMessage  # re-exported
from gbs.model_backend import get_model
from gbs.qwen3_coder_parser import parse

__all__ = ["TokenUsage", "ToolCall", "ChatMessage", "LLMClient"]


class LLMClient:
    """Loads the model in-process and generates tool-calling completions."""

    def __init__(
        self,
        model_id: str,
        torch_dtype: str = "auto",
        device_map: str = "auto",
        max_context_tokens: int = 32768,
    ):
        self._model, self._tokenizer = get_model(model_id, torch_dtype, device_map)
        self._max_context_tokens = max_context_tokens

    def chat(
        self,
        messages: list[dict],
        tools: list[dict],
        max_tokens: int = 8192,
        temperature: float = 0.0,
    ) -> ChatMessage:
        tok = self._tokenizer
        enc = tok.apply_chat_template(
            messages,
            tools=tools or None,
            add_generation_prompt=True,
            return_tensors="pt",
            return_dict=True,
        )
        enc = {k: v.to(self._model.device) for k, v in enc.items()}
        prompt_len = int(enc["input_ids"].shape[1])

        gen_kwargs = dict(
            max_new_tokens=max_tokens,
            do_sample=temperature > 0,
            pad_token_id=tok.eos_token_id,
            stop_strings=["</tool_call>"],
            tokenizer=tok,
        )
        if temperature > 0:
            gen_kwargs["temperature"] = temperature
        else:
            # Greedy decoding: explicitly unset the model's sampling defaults so
            # transformers doesn't warn (once per turn) that temperature/top_p/top_k
            # are ignored.
            gen_kwargs.update(temperature=None, top_p=None, top_k=None)

        with torch.no_grad():
            out = self._model.generate(**enc, **gen_kwargs)

        gen_ids = out[0][prompt_len:]
        text = tok.decode(gen_ids, skip_special_tokens=True)
        content, tool_calls = parse(text, tools or [])
        usage = TokenUsage(input_tokens=prompt_len, output_tokens=int(gen_ids.shape[0]))
        return ChatMessage(content=content, tool_calls=tool_calls, usage=usage)
