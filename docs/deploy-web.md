# RadSpeed Web Server — Deployment Guide

Deploy VoxRad as a single-container web service — on Fly.io (recommended, always-on free tier) or on any Linux host using Docker Compose.

---

## TLS / HTTPS — required for network access

RadSpeed's web mode authenticates with HTTP Basic Auth (or session cookies in
OAuth mode). Over plain HTTP both are readable by anyone on the network path —
as is every dictation and report (PHI). The launcher therefore **refuses to
bind a non-loopback address over plain HTTP** and exits with an error unless
one of the following applies:

| Situation | What to do |
|---|---|
| Bare-metal / VM, no proxy | Terminate TLS in-app: `--ssl-certfile` + `--ssl-keyfile` (or `RADSPEED_SSL_CERTFILE` / `RADSPEED_SSL_KEYFILE` env vars) |
| Behind a TLS reverse proxy (nginx, Caddy, Fly.io, Render, …) | Set `RADSPEED_BEHIND_PROXY=1` — already set in `fly.toml`, `render.yaml`, and `docker-compose.yml` |
| Local use only | Bind loopback: `--host 127.0.0.1` (always allowed) |
| Trusted network, accepted risk | `--insecure` (or `RADSPEED_ALLOW_INSECURE_HTTP=1`) — starts with a loud warning |

When TLS is active (in-app or `RADSPEED_BEHIND_PROXY=1`), session cookies are
additionally marked `Secure` so browsers never send them over plain HTTP.

### In-app TLS (bare-metal self-hosting, no reverse proxy)

```bash
# Obtain certificates (Let's Encrypt shown; any CA or self-signed works):
certbot certonly --standalone -d your.domain.com

python RadSpeed.py --web --port 8765 \
    --ssl-certfile /etc/letsencrypt/live/your.domain.com/fullchain.pem \
    --ssl-keyfile  /etc/letsencrypt/live/your.domain.com/privkey.pem
# → https://your.domain.com:8765
```

Certificate renewal: certbot renews in place, but uvicorn loads the files once
at startup — restart RadSpeed after each renewal (e.g. a `--deploy-hook` that
restarts the service).

For Docker/Compose deployments prefer the nginx profile below; it handles
port 80 → 443 redirect and HSTS as well.

---

## Option A — Fly.io (recommended, always-on free tier)

Fly.io keeps your container running permanently — no cold-start delays. The free allowance
(one shared-cpu-1x VM + 3 GB storage) covers a single VoxRad instance indefinitely.

### 1. Install flyctl

```bash
curl -L https://fly.io/install.sh | sh   # Linux / macOS
# or: brew install flyctl               # macOS with Homebrew
flyctl auth login
```

### 2. Create the app and volumes

```bash
# Pick a unique app name (e.g. voxrad-yourname) and your nearest region:
# Regions: https://fly.io/docs/reference/regions/  (e.g. syd, lax, iad, lhr, sin)
flyctl apps create voxrad-yourname

# Persistent storage — created once, survives redeploys
flyctl volumes create voxrad_config --size 1 --region syd
flyctl volumes create voxrad_data   --size 1 --region syd
```

Update the `app` and `primary_region` fields in `fly.toml` to match.

### 3. Set secrets

```bash
flyctl secrets set \
  VOXRAD_WEB_PASSWORD=changeme \
  VOXRAD_TRANSCRIPTION_API_KEY=gsk_... \
  VOXRAD_TEXT_API_KEY=sk-...

# Optional — streaming STT (Deepgram / AssemblyAI):
flyctl secrets set DEEPGRAM_API_KEY=...
flyctl secrets set VOXRAD_STREAMING_STT_PROVIDER=deepgram
```

### 4. Deploy

```bash
flyctl deploy
# App URL is printed at the end, e.g. https://voxrad-yourname.fly.dev
```

### Updating

```bash
git pull
flyctl deploy
```

### Logs & status

```bash
flyctl logs          # tail live logs
flyctl status        # machine health
flyctl ssh console   # SSH into the container
```

---

## Option B — On-Premises (Docker Compose)

### Prerequisites

| Requirement | Notes |
|---|---|
| Docker ≥ 24 + Compose v2 | `docker compose version` |
| A domain name (optional) | Required for HTTPS |
| TLS certificates (optional) | Let's Encrypt / your CA |
| Transcription API key | OpenAI Whisper or compatible (e.g. local faster-whisper) |
| Text model API key | OpenAI or compatible (e.g. local Ollama) |

---

### Quick start (localhost only)

```bash
# 1. Clone the repo
git clone https://github.com/markbekhit/voxrad.git
cd voxrad

# 2. Create your .env file
cp .env.example .env
$EDITOR .env          # set VOXRAD_WEB_PASSWORD and your API keys

# 3. Build and start
docker compose up -d

# 4. Open http://localhost:8765 in your browser
```

The first `docker compose up` builds the image (~5 min). Subsequent starts are instant.

The container's port is published on **127.0.0.1 only** by default, so the
plain-HTTP app is not reachable from the network. To serve other machines,
use the nginx TLS profile below (recommended). Setting `VOXRAD_BIND=0.0.0.0`
in `.env` exposes plain HTTP to the network — credentials and PHI in
cleartext — and should only be used behind your own TLS proxy.

---

### Configuration

All configuration is done via environment variables in `.env`.

### Required

| Variable | Description |
|---|---|
| `VOXRAD_WEB_PASSWORD` | UI login password. **Change before any network-accessible deployment.** |
| `VOXRAD_TRANSCRIPTION_API_KEY` | Whisper-compatible transcription API key |
| `VOXRAD_TEXT_API_KEY` | LLM API key for report formatting |

### Optional

| Variable | Default | Description |
|---|---|---|
| `VOXRAD_PORT` | `8765` | Host port to bind |
| `VOXRAD_BIND` | `127.0.0.1` | Host interface to publish the port on. `0.0.0.0` exposes plain HTTP to the network — use the nginx profile instead |
| `RADSPEED_BEHIND_PROXY` | _(empty)_ | Set to `1` when a TLS reverse proxy (nginx profile, or your own) fronts the app — marks session cookies `Secure` |
| `VOXRAD_WORKING_DIR` | `/data/working` | Path inside container for templates, guidelines, reports |
| `VOXRAD_MM_API_KEY` | _(empty)_ | Gemini API key (only if multimodal mode is used) |

### Using local models

Point the API URLs at your local inference servers via settings.ini in the `voxrad-config` volume,
or configure them in the web UI's Settings tab on first use:

```
VOXRAD_TRANSCRIPTION_BASE_URL=http://host.docker.internal:8000/v1
VOXRAD_TEXT_BASE_URL=http://host.docker.internal:11434/v1
```

See [local-whisper-setup.md](local-whisper-setup.md) for running a local Whisper server.

---

### Volumes

| Volume | Mount point in container | Contents |
|---|---|---|
| `voxrad-config` | `/root/.voxrad` | `settings.ini`, encrypted API key files |
| `voxrad-data` | `/data/working` | `templates/`, `guidelines/`, `reports/` |

### Adding templates and guidelines

Copy files into the data volume while the container is running:

```bash
docker compose cp templates/. voxrad:/data/working/templates/
docker compose cp guidelines/. voxrad:/data/working/guidelines/
```

Or place them in a local directory and use a bind mount instead of the named volume:

```yaml
# docker-compose.yml override
volumes:
  - ./my-templates:/data/working/templates:ro
  - ./my-guidelines:/data/working/guidelines:ro
```

---

### HTTPS with nginx (recommended for production)

HTTP Basic Auth sends credentials in cleartext. Always run behind HTTPS for any deployment accessible outside localhost. When running the nginx profile, set `RADSPEED_BEHIND_PROXY=1` in `.env` so session cookies are marked `Secure`.

### 1. Obtain TLS certificates

```bash
# Using certbot (Let's Encrypt):
certbot certonly --standalone -d your.domain.com

# Copy into the deploy/certs directory:
mkdir -p deploy/certs
cp /etc/letsencrypt/live/your.domain.com/fullchain.pem deploy/certs/
cp /etc/letsencrypt/live/your.domain.com/privkey.pem   deploy/certs/
chmod 600 deploy/certs/privkey.pem
```

### 2. Update nginx.conf

Edit `deploy/nginx.conf` and replace `server_name _;` with your domain:

```nginx
server_name your.domain.com;
```

### 3. Start with the nginx profile

```bash
docker compose --profile nginx up -d
```

This starts both `voxrad` (on internal port 8765) and `nginx` (on ports 80/443).
Nginx proxies HTTPS → VoxRad and redirects HTTP → HTTPS automatically.

---

### Advanced: encrypted API keys

For higher security, use the encrypted-key workflow instead of plaintext env vars:

1. Run the desktop app on any machine and save/encrypt your API keys in Settings.
2. Copy the encrypted files to the server:
   ```bash
   # On the desktop machine, keys are at ~/.voxrad/
   scp ~/.voxrad/*.encrypted ~/.voxrad/.asr_salt ~/.voxrad/.text_salt \
       user@server:/var/lib/docker/volumes/voxrad_voxrad-config/_data/
   ```
3. In `.env`, set the passwords instead of the raw API keys:
   ```
   VOXRAD_TRANSCRIPTION_PASSWORD=yourpassword
   VOXRAD_TEXT_PASSWORD=yourpassword
   VOXRAD_TRANSCRIPTION_API_KEY=   # leave blank
   VOXRAD_TEXT_API_KEY=            # leave blank
   ```

Encrypted keys always take precedence over plaintext env vars.

---

### Updating

```bash
git pull
docker compose build --no-cache
docker compose up -d
```

---

### Troubleshooting

| Symptom | Fix |
|---|---|
| `503 Transcription API key not loaded` | Set `VOXRAD_TRANSCRIPTION_API_KEY` in `.env` and restart |
| `503 Text model API key not loaded` | Set `VOXRAD_TEXT_API_KEY` in `.env` and restart |
| `401 Incorrect password` | Check `VOXRAD_WEB_PASSWORD` in `.env` |
| Templates not showing | Copy templates into the `voxrad-data` volume (see above) |
| Container exits immediately | Run `docker compose logs voxrad` to see the error |
| Port already in use | Change `VOXRAD_PORT` in `.env` |
