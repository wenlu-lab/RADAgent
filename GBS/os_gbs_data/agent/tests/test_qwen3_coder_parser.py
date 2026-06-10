from gbs.qwen3_coder_parser import parse

TOOLS = [{
    "type": "function",
    "function": {
        "name": "Bash",
        "description": "Run a bash command",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "timeout_ms": {"type": "integer"},
            },
        },
    },
}]


def test_parses_function_and_coerces_types():
    text = (
        "I'll list the files.\n"
        "<tool_call>\n"
        "<function=Bash>\n"
        "<parameter=command>\n"
        "ls -la\n"
        "</parameter>\n"
        "<parameter=timeout_ms>\n"
        "5000\n"
        "</parameter>\n"
        "</function>\n"
        "</tool_call>"
    )
    content, calls = parse(text, TOOLS)
    assert content == "I'll list the files."
    assert len(calls) == 1
    assert calls[0].name == "Bash"
    assert calls[0].arguments == {"command": "ls -la", "timeout_ms": 5000}
    assert calls[0].id.startswith("call_")


def test_no_tool_call_returns_plain_content():
    content, calls = parse("**Status**: SUCCESS\nAll done.", TOOLS)
    assert calls == []
    assert "SUCCESS" in content


def test_malformed_value_falls_back_to_string():
    # timeout_ms is declared integer but value isn't numeric → keep raw string, no crash
    text = (
        "<tool_call>\n<function=Bash>\n"
        "<parameter=timeout_ms>\nnot-a-number\n</parameter>\n"
        "</function>\n</tool_call>"
    )
    content, calls = parse(text, TOOLS)
    assert len(calls) == 1
    assert calls[0].arguments["timeout_ms"] == "not-a-number"
