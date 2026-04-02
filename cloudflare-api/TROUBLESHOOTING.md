# Troubleshooting

## `./up.sh` says `llama-server is not reachable`

Start the model host first:

```bash
python3 -c "from assistant.genesis_llm import start_model; start_model('9B')"
```

## `./up.sh` says proxy is not reachable

Check whether `proxy.py` is already running on port `5050`.

## Worker `/reply` returns `500`

Check these in order:

1. local `llama-server`
2. local `proxy.py`
3. public tunnel URL
4. Worker deployment

## Public tunnel works once and then changes

You are likely using a quick `trycloudflare.com` tunnel.

Use a named Cloudflare Tunnel for a stable URL.

## `/config` or `/reply` returns `403`

Make sure the app key exists in remote KV and the request is sending:

```text
Authorization: Bearer YOUR_APP_KEY
```

## `curl` gets mangled in shell

Use one-line commands or save payloads to files.

## Android / Quest mic conflicts

Keep device STT and device TTS inside the Quest app.
Do not depend on arbitrary cross-app microphone sharing.
