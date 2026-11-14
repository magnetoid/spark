# Changelog

Changes that matter to people who run Spark. Dates are when the change reached `main`.

## Unreleased

**Before you upgrade:** nothing breaks. To get fresh numbers about an hour after Zernio syncs
them, open **Settings → Connectors → Zernio** and press **Refresh registration** once, so
Zernio also sends the `analytics.synced` event.

- Analytics keeps reach, views and saves apart, where the network reports them. Saves are no
  longer counted as shares; older posts are marked. The engagement rate divides by
  impressions, else views, else reach, the same way for every network.
- One reading per post per day, so the chart can show each day's gain, not only totals by
  publish day.
- Zernio analytics costs fewer calls: new posts are read hourly, older ones daily or every
  third day, with a cap per run (`SPARK_METRICS_MAX_CALLS_PER_RUN`). When Zernio says to slow
  down, Spark waits; when the plan has no Analytics add-on, Analytics says so.
- "What works" on Analytics: results by format, by content pillar and by hour and weekday per
  channel, each with how many posts it rests on.
- Short links in posts now show which post and channel each click came from, and add the
  channel and the post to the UTM tags.
- Link tracker: choose the back-half (`/l/autumn-sale`), fill in UTM source, medium,
  campaign, content and term with a preview, set an expiry date, download a QR code, and see
  clicks per day, channel, post and referrer. Link previews and bots are not counted, and no
  IP addresses are kept.
- Campaign results: posts, reach, engagement and link clicks per campaign, with a CSV export.

## 2026-11-14

- A setup checklist on **Today** for owners: Zernio key, webhooks, channels, posting times,
  first post, email, public address, secret key, worker and two-factor, each with a link to fix
  it.
- `SPARK_SETUP_TOKEN`: when set, creating the first owner asks for it.
- New guides in `docs/`: install, configuration, connectors, upgrading and troubleshooting;
  a complete `.env.example` and a `docker-compose.example.yml` for any server.
- Fix: creating the first brand on a new install showed "Something went wrong" instead of
  Channels.
- Channel health: Spark checks every channel each hour and tells the team once by email, chat
  and webhook when one needs reconnecting, or 7, 3 and 1 days before its access ends. New
  webhook events `channel.reconnect_needed`, `channel.expiring` and `channel.recovered`.
- Publishing health on the Sent and Failed views: success rate, failures by channel and
  reason, the next post per channel.
- A post retried after a timeout can no longer go out twice.
- Per-channel settings for Pinterest boards, Reddit subreddits, and TikTok and YouTube privacy.
- `/healthz` reports the database, Redis, when the worker last checked in, and the version.
- Fixes: inbox likes, discarding a prepared reply, PDF uploads, marking inbox items read at the
  network, drafts counted twice on Today, the link field not shortened, and the composer
  offering to resume the post being typed.
