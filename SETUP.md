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
- Each engineer needs their own Open WebUI API token (JWT from Open WebUI settings)

## Step 1: Proxy Config

Create a `config.yaml` for the litellm proxy:

```yaml
model_list:
  # Wildcard: Claude Code sends "claude-*", Open WebUI expects "anthropic.claude-*"
  - model_name: claude-*
    litellm_params:
      model: openai/anthropic.claude-*
      api_base: https://openwebui.your-company.com/api/v1
      api_key: "placeholder"  # overridden per-request by the engineer's token

general_settings:
  forward_llm_provider_auth_headers: true

litellm_settings:
  use_chat_completions_url_for_anthropic_messages: true
```

**Key settings explained:**

| Setting | Why it's needed |
|---------|-----------------|
| `model_name: claude-*` | Matches what Claude Code sends (e.g. `claude-sonnet-4-20250514`) |
| `model: openai/anthropic.claude-*` | The `openai/` prefix tells LiteLLM to use OpenAI format. The `anthropic.` prefix maps to how Open WebUI names models. The `*` is substituted from the match (e.g. `sonnet-4-20250514`) |
| `api_base: .../api/v1` | Open WebUI's OpenAI-compatible endpoint. The SDK appends `/chat/completions` to this, so it must end with `/api/v1` (not `/api`) |
| `api_key: "placeholder"` | Required by LiteLLM schema but overridden per-request by the forwarded token |
| `forward_llm_provider_auth_headers: true` | Forwards the client's `x-api-key` as the upstream API key (`Authorization: Bearer`) |
| `use_chat_completions_url_for_anthropic_messages: true` | **Critical.** Without this, LiteLLM routes `openai` provider requests to the Responses API (`/v1/responses`) which Open WebUI does not support. This forces routing through `/v1/chat/completions` instead |

### Getting `api_base` right

The OpenAI SDK appends `/chat/completions` to whatever you set as `api_base`.
You need the final URL to match Open WebUI's endpoint:

| Your Open WebUI endpoint | Set `api_base` to |
|--------------------------|-------------------|
| `https://owui.co/api/v1/chat/completions` | `https://owui.co/api/v1` |
| `https://owui.co/v1/chat/completions` | `https://owui.co/v1` |
| `https://owui.co/chat/completions` | `https://owui.co` |

To find your Open WebUI's actual endpoint, check its admin settings or try:
```bash
curl https://openwebui.your-company.com/api/v1/models \
  -H "Authorization: Bearer <your-token>"
```

### Discovering your Open WebUI model names

The model names in `model: openai/...` must match what Open WebUI exposes.
Run this to find them:

```bash
curl -s https://openwebui.your-company.com/api/v1/models \
  -H "Authorization: Bearer <your-token>" \
  | python3 -c "import sys,json; [print(m['id']) for m in json.load(sys.stdin).get('data',[])]"
```

Common patterns:
- `anthropic.claude-sonnet-4-20250514` -- use `model: openai/anthropic.claude-*`
- `claude-sonnet-4-20250514` -- use `model: openai/claude-*`
- `bedrock/claude-sonnet-4-20250514` -- use `model: openai/bedrock/claude-*`

### Specific models (alternative to wildcard)

If you need to map specific model names:

```yaml
model_list:
  - model_name: claude-sonnet-4-20250514
    litellm_params:
      model: openai/anthropic.claude-sonnet-4-20250514
      api_base: https://openwebui.your-company.com/api/v1
      api_key: "placeholder"
  - model_name: claude-opus-4-20250514
    litellm_params:
      model: openai/anthropic.claude-opus-4-20250514
      api_base: https://openwebui.your-company.com/api/v1
      api_key: "placeholder"

general_settings:
  forward_llm_provider_auth_headers: true

litellm_settings:
  use_chat_completions_url_for_anthropic_messages: true
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

**Where to get your Open WebUI token:** Log into Open WebUI, go to
Settings > Account > API Keys, and generate a key.

That's it. Claude Code will now:
1. Send Anthropic-format requests to the litellm proxy
2. The proxy translates to OpenAI chat/completions format
3. The proxy forwards your Open WebUI token as `Authorization: Bearer`
4. Open WebUI authenticates you and routes to Bedrock

## Verifying It Works

### 1. Verify Open WebUI works directly

First confirm your token and endpoint work without the proxy in the middle:

```bash
curl -s https://openwebui.your-company.com/api/v1/chat/completions \
  -H "Authorization: Bearer <your-open-webui-token>" \
  -H "Content-Type: application/json" \
  -d '{"model": "claude-sonnet-4-20250514", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 50}'
```

### 2. Check proxy health

```bash
curl https://litellm-proxy.your-company.com/health
```

### 3. Test through the proxy

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

## Proxy Auth (Optional)

By default this config has no proxy-level auth -- any request with a valid
Open WebUI token will work. When `master_key` is not set, the proxy accepts
all requests and relies on Open WebUI for authentication. If the proxy is on a
private network, this is fine.

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

**"Model not found" errors**: The model name Claude Code sends must match a
`model_name` in your config. The wildcard `claude-*` catches most cases. Run
`curl https://litellm-proxy.your-company.com/v1/models` to see what's available.

**Auth failures at Open WebUI**: Test your token directly (see "Verify Open
WebUI works directly" above). If that works but the proxy doesn't, check that
`forward_llm_provider_auth_headers: true` is set.

**404 or "Not Found" from Open WebUI**: Your `api_base` is wrong. The SDK
appends `/chat/completions` to it. See the "Getting `api_base` right" table.

**Responses API errors / unexpected endpoint**: You forgot to set
`use_chat_completions_url_for_anthropic_messages: true`. Without this, litellm
sends requests to `/v1/responses` instead of `/v1/chat/completions`.

**Connection refused**: Check the proxy is running and the `ANTHROPIC_BASE_URL`
is reachable from the engineer's machine.

**Streaming issues**: Streaming is supported out of the box. If you see
truncated responses, check for reverse proxy timeout settings (nginx
`proxy_read_timeout`, etc.).

## Known Limitations

- **Tool use translation**: Claude Code uses tools heavily (bash, file editing).
  The Anthropic-to-OpenAI tool format translation works for standard cases but
  complex tool schemas with very long names (>64 chars) get truncated and
  mapped back. If you see tool-related errors, this may be the cause.

- **Extended thinking**: Anthropic's thinking blocks are translated but the
  fidelity depends on what the upstream OpenAI-compatible endpoint returns.
  Open WebUI may not surface thinking content from Bedrock.

- **No proxy-level rate limiting without master key**: Without a master key,
  all rate limiting happens at the Open WebUI / Bedrock layer.
