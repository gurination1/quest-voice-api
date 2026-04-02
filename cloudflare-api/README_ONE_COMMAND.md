# One Command Setup

This folder can be reduced to one command after a one-time secret setup.

## One-time setup

1. Copy `.env.example` to `.env`
2. Fill:
   - `CLOUDFLARE_API_TOKEN`
   - `CF_TUNNEL_TOKEN` if you later automate named tunnel startup
   - `TUNNEL_PUBLIC_URL`
3. Keep your named Cloudflare Tunnel running to the local proxy
4. Ensure `llama-server` is installed and usable

## Daily command

```bash
cd /home/nyx/subtitle-vr-demo/cloudflare-api
./up.sh
```

## What `up.sh` does

- verifies local `llama-server`
- ensures `team-demo-key` exists in `keys.txt`
- ensures `proxy.py` is running
- verifies the public tunnel URL
- rewrites Worker upstream config
- deploys the Worker
- writes the remote app key to KV
- runs smoke tests

## Result

Use these in the Quest app:

- Base URL: value of `WORKER_URL`
- API key: value of `APP_API_KEY`
