# Troubleshooting

Start with the health check. It answers without signing in:

```bash
curl -s https://spark.example.com/healthz
```

| Field | Means |
|---|---|
| `db` | The database answers. When it does not, the whole answer is a 503. |
| `redis` | The queue answers. Without it nothing is published. |
| `worker_seen_s` | Seconds since the worker last checked in. `null` or more than a few minutes: the worker is not running. |
| `version` | The version running, with the commit when known. |

Owners also see a setup checklist on **Today** with the same checks, and each item links to
the place to fix it.

## Posts stay scheduled and never go out

The worker publishes posts; the web app does not. Check that it runs:

```bash
docker compose -f docker-compose.example.yml ps worker
docker compose -f docker-compose.example.yml logs --tail 100 worker
```

The worker needs Redis (`SPARK_REDIS_URL`). It also takes back posts that were stuck halfway
for more than a few minutes and tries them again with the same idempotency key, so a post never
goes out twice.

## A post failed

**Publishing → Failed** shows each failure with the network's own message, and the publishing
health card groups failures by channel and reason. Common causes:

- **The channel needs reconnecting.** Its badge on **Channels** says so; press **Reconnect**.
- **The network could not fetch the media.** Networks download images and videos from
  `SPARK_BASE_URL`. It must be a public HTTPS address, not `localhost` or a private network.
- **A network rule.** Too long, wrong aspect ratio, a missing Pinterest board or Reddit
  subreddit. Fix the post or the channel's settings and press **Retry**.

## Emails do not arrive

With `SPARK_EMAIL_BACKEND=console` (the default), emails are only written to the web and worker
logs. Set up SMTP or Resend under **Settings → Connectors → Email** and send a test from there.

## Comments and messages arrive late

Without Zernio webhooks Spark picks up new inbox items on its regular checks. Press
**Enable webhooks** on the Zernio card under **Settings → Connectors** so they arrive within
seconds. The address Spark registers is `{SPARK_BASE_URL}/webhooks/zernio`, so it has to be
reachable from the internet.

## Someone is locked out by two-factor

They can sign in with one of their recovery codes. If those are gone, an owner can turn
two-factor off for them under **Settings → Brand & team**. If the owner is the one locked out,
run this on the server:

```bash
docker compose -f docker-compose.example.yml exec web spark reset-two-factor owner@example.com
```

## The setup page asks for a token

The install was started with `SPARK_SETUP_TOKEN`. Enter that value. If nobody knows it, set a
new one in the environment and restart the web container; the token is only asked for until
the owner account exists.

## Everyone was signed out and saved keys stopped working

`SPARK_SECRET_KEY` changed. Sessions, saved connector values and channel tokens are tied to
it. Put the old value back; if it is lost, save the connector values again and reconnect the
channels.

## Reporting a bug

Open an issue with what you did, what you expected, what happened, the `version` from
`/healthz` and the relevant log lines. Remove keys, tokens and email addresses from logs first.
Security problems go privately, as described in [SECURITY.md](../SECURITY.md).
