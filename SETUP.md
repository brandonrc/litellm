# Claude Code + Open WebUI via LiteLLM Proxy

## The Problem

Engineers use Claude Code, which speaks the Anthropic API format. The org's LLM
gateway is Open WebUI, which speaks the OpenAI API format and handles auth +
routing to AWS Bedrock. Without a translation layer, every engineer needs a
local proxy on their machine.

## Architecture

```
Claude Code (Anthropic format, x-api-key)
  |
  v
LiteLLM Proxy (centralized, translates Anthropic <-> OpenAI)
  |
  v
Open WebUI (OpenAI format, Authorization: Bearer)
  |
  v
AWS Bedrock (behind the scenes)
```

LiteLLM's `/v1/messages` endpoint accepts Anthropic-format requests, translates
them to OpenAI chat/completions format, and forwards to Open WebUI. Each
engineer's `x-api-key` token is forwarded as the `Authorization: Bearer` token
to Open WebUI for per-user authentication.

## Prerequisites

- Python 3.9+
- LiteLLM installed with proxy extras: `pip install 'litellm[proxy]'`
- Access to your org's Open WebUI instance
- Each engineer needs their own Open WebUI API token

## Step 1: Proxy Config

Create a `config.yaml` for the litellm proxy:

```yaml
model_list:
  # Wildcard: any model name starting with "claude-" gets routed to Open WebUI
  - model_name: claude-*
    litellm_params:
      model: openai/claude-*
      api_base: https://openwebui.your-company.com/api
      api_key: "placeholder"  # overridden per-request by the engineer's token

general_settings:
  forward_llm_provider_auth_headers: true
```

**Key settings explained:**

| Setting | What it does |
|---------|-------------|
| `model: openai/claude-*` | The `openai/` prefix tells LiteLLM to send OpenAI-format requests upstream |
| `api_base` | Points to your Open WebUI instance |
| `api_key: "placeholder"` | Required by LiteLLM but overridden per-request by the forwarded token |
| `forward_llm_provider_auth_headers: true` | Forwards the client's `x-api-key` as the upstream API key |

### Specific models (alternative to wildcard)

If you need to map specific model names:

```yaml
model_list:
  - model_name: claude-sonnet-4-20250514
    litellm_params:
      model: openai/claude-sonnet-4-20250514
      api_base: https://openwebui.your-company.com/api
      api_key: "placeholder"
  - model_name: claude-opus-4-20250514
    litellm_params:
      model: openai/claude-opus-4-20250514
      api_base: https://openwebui.your-company.com/api
      api_key: "placeholder"

general_settings:
  forward_llm_provider_auth_headers: true
```

## Step 2: Start the Proxy

```bash
litellm --config config.yaml --host 0.0.0.0 --port 4000
```

For production, run behind a reverse proxy (nginx, caddy, etc.) with TLS.

### Docker

```bash
docker run \
  -v $(pwd)/config.yaml:/app/config.yaml \
  -p 4000:4000 \
  ghcr.io/berriai/litellm:main-latest \
  --config /app/config.yaml --host 0.0.0.0 --port 4000
```

## Step 3: Engineer Setup (Claude Code)

Each engineer adds two environment variables:

```bash
export ANTHROPIC_BASE_URL=https://litellm-proxy.your-company.com
export ANTHROPIC_API_KEY=<your-open-webui-token>
```

Add these to `~/.zshrc`, `~/.bashrc`, or your shell profile to persist them.

That's it. Claude Code will now:
1. Send Anthropic-format requests to the litellm proxy
2. The proxy translates to OpenAI format
3. The proxy forwards your Open WebUI token as `Authorization: Bearer`
4. Open WebUI authenticates you and routes to Bedrock

## Verifying It Works

### Quick test from the command line

```bash
curl -s https://litellm-proxy.your-company.com/v1/messages \
  -H "Content-Type: application/json" \
  -H "x-api-key: <your-open-webui-token>" \
  -H "anthropic-version: 2023-06-01" \
  -d '{
    "model": "claude-sonnet-4-20250514",
    "max_tokens": 50,
    "messages": [{"role": "user", "content": "Say hello"}]
  }'
```

### Check proxy health

```bash
curl https://litellm-proxy.your-company.com/health
```

## Proxy Auth (Optional)

By default this config has no proxy-level auth -- any request with a valid
Open WebUI token will work. If the proxy is on a private network, this is
fine since Open WebUI handles authentication.

If you want proxy-level auth too, add a master key:

```yaml
general_settings:
  master_key: sk-your-proxy-master-key
  forward_llm_provider_auth_headers: true
```

Engineers would then need to generate virtual keys via the litellm admin API,
and Claude Code would use the virtual key for proxy auth while the Open WebUI
token would need to be sent separately. For most setups, relying on network
security + Open WebUI auth is simpler.

## Troubleshooting

**"Model not found" errors**: Make sure the model name Claude Code sends
matches a `model_name` in your config. The wildcard `claude-*` should catch
most cases.

**Auth failures at Open WebUI**: Verify your Open WebUI token works directly:
```bash
curl https://openwebui.your-company.com/api/v1/chat/completions \
  -H "Authorization: Bearer <your-open-webui-token>" \
  -H "Content-Type: application/json" \
  -d '{"model": "claude-sonnet-4-20250514", "messages": [{"role": "user", "content": "hi"}]}'
```

**Connection refused**: Check the proxy is running and the `ANTHROPIC_BASE_URL`
is reachable from the engineer's machine.

**Streaming issues**: Streaming is supported out of the box. If you see
truncated responses, check for reverse proxy timeout settings (nginx
`proxy_read_timeout`, etc.).
