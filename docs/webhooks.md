# Webhooks

Spark can call an address of yours when something happens: a post goes out, fails or waits
for approval, or something new lands in the inbox. Use it to drive n8n, Make, Zapier or your
own server.

Workspace owners add webhooks under **Settings → Webhooks**. Each webhook has an address, an
optional brand (one brand, or all of them) and a list of events (none ticked means every
event, including ones added later).

## The request

Spark sends a `POST` with a JSON body:

```
POST /hooks/spark HTTP/1.1
Content-Type: application/json
User-Agent: Spark-Webhooks/1.0
X-Spark-Event: post.published
X-Spark-Delivery: 42
X-Spark-Signature: t=1731500000,v1=5f2b…

{"id":"evt_17","event":"post.published","created_at":"2026-11-13T10:00:00Z","brand":{"id":1,"name":"Acme"},"data":{…}}
```

| Field | Meaning |
|---|---|
| `id` | The event. The same event sent to two webhooks has the same id. |
| `event` | The event name, also in `X-Spark-Event`. |
| `created_at` | When it happened, UTC. |
| `brand` | The brand it belongs to. `null` only in a test sent to an all-brands webhook. |
| `data` | Depends on the event, see below. |

Answer with any `2xx` status within 10 seconds. Spark does not read the answer's body and does
not follow redirects. Do slow work after you have answered.

## Checking the signature

When you add a webhook Spark shows its signing secret (`whsec_…`) once. Keep it; it cannot be
shown again. To get a new one, delete the webhook and add it again.

`X-Spark-Signature` has two parts: `t`, the time Spark sent the request (Unix seconds), and
`v1`, the hex HMAC-SHA256 of `<t>.<raw body>` keyed with the secret. Compute it over the bytes
you received, before any JSON parsing, and refuse requests older than a few minutes.

Python:

```python
import hashlib, hmac, time

def is_from_spark(secret: str, header: str, raw_body: bytes) -> bool:
    parts = dict(p.split("=", 1) for p in header.split(","))
    if abs(time.time() - int(parts["t"])) > 300:
        return False
    signed = parts["t"].encode() + b"." + raw_body
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, parts["v1"])
```

Node:

```js
import { createHmac, timingSafeEqual } from "node:crypto";

export function isFromSpark(secret, header, rawBody) {
  const parts = Object.fromEntries(header.split(",").map((p) => p.split(/=(.*)/s).slice(0, 2)));
  if (Math.abs(Date.now() / 1000 - Number(parts.t)) > 300) return false;
  const expected = createHmac("sha256", secret).update(`${parts.t}.`).update(rawBody).digest("hex");
  const a = Buffer.from(expected), b = Buffer.from(parts.v1 ?? "");
  return a.length === b.length && timingSafeEqual(a, b);
}
```

## Retries

A delivery that does not get a `2xx` in time is tried again after 1 minute, 5 minutes,
30 minutes, 2 hours and 6 hours: six tries in all, then it is marked failed.

- `X-Spark-Delivery` stays the same on every retry of one delivery. A delivery can arrive more
  than once (your answer may get lost on the way back), so remember the ids you have handled
  and skip repeats.
- The signature is made fresh for each try, so `t` is always recent.
- After 20 failed tries in a row Spark switches the webhook off and says why in Settings.
  Switch it back on there once your address works.
- A webhook that is off receives nothing: events that happen meanwhile are not kept for it,
  and deliveries that were still waiting for a retry are marked failed when their time comes.
- The log in Settings shows the last 50 deliveries. Finished deliveries are removed after
  30 days.

## Sending a test

**Send test** in Settings sends one `webhook.test` event right away and shows the result. It is
never retried and does not count toward switching the webhook off.

```json
{"id":"evt_test","event":"webhook.test","created_at":"2026-11-13T10:00:00Z","brand":null,
 "data":{"message":"This is a test from Spark. Real events look the same, with their own data."}}
```

`brand` is the webhook's brand when it is set to one, otherwise `null`.

## Events

| Event | When |
|---|---|
| `post.approval_needed` | A post waits for approval |
| `post.published` | A post went out on every channel it was meant for |
| `post.failed` | A post could not be published after retrying |
| `inbox.comment` | A new comment arrived |
| `inbox.message` | A new direct message arrived |
| `inbox.review` | A new review arrived |
| `inbox.mention` | The brand was mentioned |

### Post events

```json
{
  "post": {
    "id": 123,
    "content": "First 280 characters of the post",
    "status": "published",
    "scheduled_at": "2026-11-13T09:00:00Z",
    "url": "https://spark.example.com/posts/123/edit"
  },
  "targets": [
    {"platform": "linkedin", "handle": "acme", "status": "published",
     "url": "https://www.linkedin.com/feed/update/…", "error": null}
  ]
}
```

`post.failed` lists only the channels that failed, each with its `error`. `scheduled_at` and a
target's `url` can be `null`.

### Inbox events

```json
{
  "item": {
    "id": 55,
    "kind": "comment",
    "platform": "instagram",
    "handle": "acme",
    "author": "Jane Doe",
    "text": "First 1000 characters",
    "rating": null,
    "received_at": "2026-11-13T09:58:00Z",
    "permalink": "https://www.instagram.com/p/…",
    "url": "https://spark.example.com/inbox"
  }
}
```

`rating` is set for reviews (1 to 5). `permalink` can be `null`.

## Addresses Spark refuses

The address must be `http` or `https` and resolve to a public IP address. Spark refuses
loopback, private and link-local addresses, both when you save the webhook and before every
try. The name is looked up before sending and not pinned for the connection itself, so treat
webhook setup as an owner-only power (it is) and do not rely on this check as the only wall
between Spark and services on its private network.

## Managing webhooks over the API

All routes need a workspace owner (session or `Bearer spk_…` token) under `/api/v1`:

| Route | Does |
|---|---|
| `GET /webhooks` | Webhooks and the list of events |
| `POST /webhooks` | Adds one; the answer carries `secret` once |
| `PATCH /webhooks/{id}` | Changes address, note, brand, events or `enabled` |
| `DELETE /webhooks/{id}` | Deletes it and its delivery log |
| `POST /webhooks/{id}/test` | Sends the test event and returns the delivery |
| `GET /webhooks/{id}/deliveries` | The last 50 deliveries |
