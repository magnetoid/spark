# Install

Spark runs as five containers: the web app, a background worker, the Janus agent, PostgreSQL
and Redis. Any machine with Docker and Compose and 2 GB of memory is enough for a small team.

## With Docker Compose

```bash
git clone https://github.com/magnetoid/spark.git && cd spark
cp .env.example .env
```

Edit `.env`. Three values matter on the first day:

- `SPARK_BASE_URL`: the address people will open, for example `https://spark.example.com`.
  Networks download your images and videos from this address, so it has to be reachable from
  the internet once you publish for real. For a first look on your own computer,
  `http://localhost:8000` is fine.
- `SPARK_SECRET_KEY`: a long random value, for example from `openssl rand -hex 32`. Keep it:
  saved keys and channel tokens are encrypted with it.
- `SPARK_SETUP_TOKEN`: any value you choose. The first person to create the owner account has to
  enter it, so nobody else can claim a fresh install.

Also set `POSTGRES_PASSWORD` and `SPARK_JANUS_API_KEY` to random values. Then start it:

```bash
docker compose -f docker-compose.example.yml up -d
```

The web container applies database migrations before it starts serving. Open
`SPARK_BASE_URL`, enter the setup token, and create the owner account. The checklist on
**Today** lists what is left: the Zernio key, channels, posting times, email and two-factor.

Check that everything is running:

```bash
curl -s http://localhost:8000/healthz
```

```json
{"ok": true, "db": true, "redis": true, "worker_seen_s": 12, "version": "0.1.0"}
```

`worker_seen_s` is how many seconds ago the worker last checked in. If it is `null` or keeps
growing past a few minutes, posts are not being published: see
[Troubleshooting](troubleshooting.md).

## Behind a reverse proxy

The example Compose file publishes the web app on port 8000 over plain HTTP. Put a reverse
proxy in front of it for HTTPS. With [Caddy](https://caddyserver.com):

```
spark.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

With nginx, pass the host and scheme on and allow large uploads:

```nginx
server {
    server_name spark.example.com;
    client_max_body_size 60m;
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
    # listen 443 ssl; plus your certificate lines
}
```

Keep `client_max_body_size` above `SPARK_MAX_UPLOAD_MB`. When Spark is served over HTTPS, set
`SPARK_ENV=production` so session cookies are only sent over HTTPS.

## With Coolify

`docker-compose.yml` in the repository is written for [Coolify](https://coolify.io). Coolify fills
the `SERVICE_*` variables in it: the domain, the secret key and the database password. Create a
Docker Compose resource from the repository, set a domain on the `web` service, and add any
`SPARK_*` values you want in Coolify's environment panel, `SPARK_SETUP_TOKEN` first. Every push
to the branch you chose then deploys.

## Backups

Two things hold your data: the PostgreSQL database and the media volume.

```bash
docker compose -f docker-compose.example.yml exec -T db pg_dump -U spark spark | gzip > spark-$(date +%F).sql.gz
docker run --rm -v spark_media:/m -v "$PWD":/b alpine tar czf /b/media-$(date +%F).tgz -C /m .
```

The volume name starts with the Compose project name, which is the folder name by default;
`docker volume ls` shows it. Keep `.env` (and above all `SPARK_SECRET_KEY`) with the backups:
without the same key, saved connector values and channel tokens cannot be read.

To restore, start only the database, load the dump, unpack the media and start the rest:

```bash
docker compose -f docker-compose.example.yml up -d db
gunzip -c spark-2026-11-14.sql.gz | docker compose -f docker-compose.example.yml exec -T db psql -U spark spark
docker run --rm -v spark_media:/m -v "$PWD":/b alpine tar xzf /b/media-2026-11-14.tgz -C /m
docker compose -f docker-compose.example.yml up -d
```

## Without Docker

Spark is a Python 3.12 package. With [uv](https://docs.astral.sh/uv/), PostgreSQL and Redis:

```bash
uv sync --no-dev
(cd frontend && npm ci && npm run build)
uv run alembic upgrade head
uv run spark serve --port 8000     # the web app
uv run spark worker                # in a second process: publishing and background jobs
```

Run both processes under your service manager (systemd or similar) and restart them after an
upgrade.
