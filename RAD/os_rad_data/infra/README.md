# Infrastructure

The agent loads the model **in-process** via Hugging Face `transformers` — there is
no separate inference server to run. See the root `README.md` for setup.

GPU: the agent loads `microsoft/Phi-4` (bf16, ~28 GB) once per
process on an A100 80 GB. The first agent call triggers the load (a few minutes);
it then stays resident for the whole run. (The `-FP8` variant needs GPU compute
capability ≥ 8.9 — Ada/Hopper — so it does not load on the Ampere A100.)
