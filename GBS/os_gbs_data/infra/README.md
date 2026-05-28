# Infrastructure

## vLLM serving

For development:

```bash
./infra/vllm_serve.sh
```

For production (one-time setup):

```bash
sudo cp infra/systemd/vllm.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now vllm
sudo systemctl status vllm
```

Logs go to `.gbs/vllm.log`.
