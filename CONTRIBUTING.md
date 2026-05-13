# Contributing

## Dev environment

The gateway requires **glibc** (not musl/Alpine) because `sentence-transformers`
and PyTorch have no Alpine wheels. The devcontainer is based on
`mcr.microsoft.com/devcontainers/python:3.11-bookworm` (Debian 12).

### Rebuilding the Codespace

After any change to `.devcontainer/devcontainer.json`:

1. Open the Command Palette (`Ctrl+Shift+P` / `Cmd+Shift+P`)
2. Run **"Codespaces: Rebuild Container"**

Or from the GitHub UI: **Code → Codespaces → ··· → Rebuild**.

---

## Running the gateway

### Docker mode (preferred)

Requires Docker to be available (works automatically after Codespace rebuild):

```bash
cd gateway
docker compose up --build
```

Wait ~60 s on first run (downloads bge-small model + Redis Stack image). Then:

```bash
pip install openai
python tests/smoke.py
```

### Native mode (fallback — no Docker needed)

Use this when DinD is unavailable (e.g. a Codespace that hasn't been rebuilt yet):

```bash
# 1. Start Redis Stack in the background
redis-stack-server --daemonize yes

# 2. Start the gateway
cd gateway
REDIS_URL=redis://localhost:6379 \
LITELLM_CONFIG=$(pwd)/litellm_config.yaml \
SHADOW_LOG_PATH=/tmp/shadow_log.jsonl \
uvicorn router.main:app --port 8000

# 3. Smoke test (separate terminal)
pip install openai
python tests/smoke.py
```

> **Note:** `redis-stack-server` is installed by `postCreateCommand` as a
> fallback. It includes the RediSearch module needed for vector-cache lookups.

---

## Verifying a fresh Codespace

After a rebuild, confirm the three key tools are all present:

```bash
docker --version
python -c "from sentence_transformers import SentenceTransformer; print('ok')"
redis-stack-server --version
```

All three should succeed with no errors.

---

## litellm_config.yaml — model metadata split

LiteLLM's `ModelInfo` schema only accepts `tier: "free" | "paid"`. Our
routing logic uses a richer `tier` value (`cheap` / `balanced` / `frontier`).

**Rule:** put LiteLLM-standard cost fields in `model_info`; put gateway-only
metadata (tier, etc.) in `gateway_info`. `router/main.py` merges both dicts
into its internal lookup table and strips `gateway_info` before handing the
model list to the LiteLLM `Router`.

```yaml
# Correct
- model_name: tier-cheap
  litellm_params: { ... }
  model_info:
    input_cost_per_token: 0.0000008
    output_cost_per_token: 0.000004
  gateway_info:
    tier: cheap          # ← gateway-only, NOT passed to LiteLLM

# Wrong — LiteLLM will raise a ValidationError
- model_name: tier-cheap
  litellm_params: { ... }
  model_info:
    tier: cheap          # ← rejected by LiteLLM ModelInfo schema
```
