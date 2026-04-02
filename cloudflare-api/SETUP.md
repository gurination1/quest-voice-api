# Setup

## One-time setup

1. Copy `.env.example` to `.env`
2. Fill the required values
3. Start a named Cloudflare Tunnel or use a temporary tunnel for testing
4. Ensure the local model host is available on `127.0.0.1:8080`

## Daily startup

```bash
cd /home/nyx/subtitle-vr-demo/cloudflare-api
./up.sh
```

## Required secrets

- `CLOUDFLARE_API_TOKEN`
- `TUNNEL_PUBLIC_URL`

## Files to look at

- `.env.example`
- `wrangler.jsonc`
- `up.sh`
- `cloudflared-config.example.yml`

## Recommended stable setup

- use a named tunnel, not a quick tunnel
- use per-user app keys for real teams
- keep device STT and device TTS as defaults

## Suggested rollout order

1. get `/health` working
2. get `/reply` working
3. integrate with Quest app
4. add per-user keys
5. replace quick tunnel with named tunnel
