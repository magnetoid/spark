# Upgrading

1. Read [CHANGELOG.md](../CHANGELOG.md) for anything marked **Before you upgrade**.
2. Back up the database and media as described in [Install](install.md#backups).
3. Pull and rebuild:

   ```bash
   git pull
   docker compose -f docker-compose.example.yml up -d --build
   ```

The web container applies database migrations on start, before it serves requests; the worker
waits until the web app answers. Migrations only add tables and columns, so an older version
keeps running against a newer database while the new one starts.

Check the result with `curl -s http://localhost:8000/healthz`: `version` shows the version (and
the commit, when the build knows it) that is running.

## Going back

If an upgrade goes wrong, check out the previous version and rebuild. To undo the database
changes of the newer version, run the downgrade before switching back:

```bash
docker compose -f docker-compose.example.yml exec web alembic downgrade -1
```

Repeat once per migration added since the version you return to (`alembic history` lists
them). Restoring the backup you made in step 2 always works too.

## Without Docker

```bash
git pull
uv sync --no-dev
(cd frontend && npm ci && npm run build)
uv run alembic upgrade head
```

Then restart `spark serve` and `spark worker`.
