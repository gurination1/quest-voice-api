# Named Tunnel Setup

Use a named Cloudflare Tunnel instead of a quick `trycloudflare.com` tunnel for a stable production URL.

## 1. Authenticate cloudflared

```bash
cloudflared tunnel login
```

## 2. Create a tunnel

```bash
cloudflared tunnel create neo-quest-api
```

This creates a tunnel id and a credentials file in `~/.cloudflared/`.

## 3. Copy the template

```bash
cp cloudflared-config.example.yml ~/.cloudflared/config.yml
```

Fill:

- tunnel id
- credentials file path
- hostname

## 4. Route a DNS hostname

```bash
cloudflared tunnel route dns neo-quest-api voice.yourdomain.com
```

## 5. Start the tunnel

```bash
cloudflared tunnel run neo-quest-api
```

## 6. Update `.env`

Set:

```bash
TUNNEL_PUBLIC_URL=https://voice.yourdomain.com
```

Then run:

```bash
./up.sh
```
