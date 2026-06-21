# Infrastructure

The agent loads the model **in-process** via Hugging Face `transformers` — there is
no separate inference server to run. See the root `README.md` for setup.

GPU: the agent loads `Qwen/Qwen3-Coder-30B-A3B-Instruct` (bf16, ~60 GB) once per
process on an A100 80 GB. The first agent call triggers the load (a few minutes);
it then stays resident for the whole run. (The `-FP8` variant needs GPU compute
capability ≥ 8.9 — Ada/Hopper — so it does not load on the Ampere A100.)
