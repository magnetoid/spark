# Changelog

Changes that matter to people who run Spark. Dates are when the change reached `main`.

## Unreleased

### Posting goals
- **Weekly goals per channel** on Today: how many posts a channel should get each week (Monday
  to Sunday in the brand's timezone), this week's published and planned posts, how many are
  still needed, the weeks in a row the goal was met and the last eight weeks at a glance.
  "Plan" opens the composer for that channel. A changed goal starts its streak again.
- From Thursday morning, Today lists channels short of their goal and owners and editors get
  one email per brand that week (Preferences: "A channel is short of its weekly goal").

**Before you upgrade:** a migration adds three nullable columns; it runs when the container
starts.

### Client connect links and a wider CSV import
- **Connect links**: on **Channels**, an owner makes a link (for chosen networks or any, for 1 to
  30 days) that a client opens without a Spark account to connect or reconnect their own
  channels through Zernio. Channels land only in that brand; owners get an email, and the
  activity log says what happened. Links are shown once and can be revoked.
- When Zernio refuses a connect because of the plan (for example the free tier's account
  limit), Spark now shows Zernio's reason to the team instead of "plan limit reached".
- **CSV import** takes `media` (library file names or public links, downloaded into the
  library), `first_comment` and `post_type`. A row whose media can't be used stays a draft; a
  channel without the chosen post type gets a plain post. Each row says what was changed.

### Agency tools
- **All clients** (`/overview`): every brand you work on with failed posts, channels to reconnect, approvals waiting or past due, replies waiting and empty days in the next week, the most urgent first.
- **Approval deadlines**: a brand can ask for approval some hours before a post's time. Approvers get one reminder before it; after it the post keeps waiting or goes back to drafts and its author is told. A deadline never publishes a post.
- **Copy setup**: start a new brand from another brand's voice, pillars, posting times, guardrails, saved replies, templates and hashtag groups, or copy them later from Settings.
- Fixed a type error that failed the frontend CI check on the last release.

**Before you upgrade:** nothing to do. Scheduled reports go out through the email settings you
already have; check **Settings → Connectors → Email** sends real mail first.

- Scheduled reports: weekly (the last Monday to Sunday) or monthly (the last month), made at an
  hour of the brand's day and emailed to up to 20 addresses, with an optional AI summary. The
  people receiving them need no Spark account.
- Share a report: a link that opens the report without an account, for 7 to 365 days, listed
  on the report with when it was last opened, and revoked with one click. Deleting a report
  ends its links.
- Reports now show what was seen (impressions, views or reach), reach, views and saves, link
  clicks per post, follower change per channel, and the typical time to reply in the inbox.

## 2026-11-14: data foundations

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

## 2026-11-14: reliability and setup

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
