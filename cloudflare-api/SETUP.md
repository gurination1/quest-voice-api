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

## Recommended stable setup

- use a named tunnel, not a quick tunnel
- use per-user app keys for real teams
- keep device STT and device TTS as defaults
