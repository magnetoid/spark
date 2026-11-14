# Integration ecosystem around social media management tools (state as of 13 November 2026)

Research notes for the Spark integration decision. Sources were read on 13 Nov 2026 unless dated otherwise. "Primary" = vendor's own page or docs. Where a page could not be fetched this is stated rather than filled in.

Pages that could NOT be fetched (so nothing below relies on them): `publer.com/integrations` (redirect loop), `later.com/integrations` (404), `hootsuite.com/integrations` (404), `hootsuite.com/app-directory` (404), `mixpost.app/integrations` (404), `docs.zernio.com/changelog` (page is rendered by client components; no entries in the fetched text).

---

## 1. Which integrations do Buffer, Hootsuite, Later, Sprout Social, Metricool, Publer, Planable, Agorapulse, Postiz and Mixpost list in 2026? Which appear in almost all?

### Takeaway
Canva is the one near-universal third-party integration (confirmed for 7 of 10; the two open-source tools substitute an embedded editor instead). The next tier is an AI-assistant/MCP connector (7 of 10, all added in 2025-26), Google Drive, Zapier, Dropbox, Bitly, Slack and Adobe Express; CRM, BI and e-commerce integrations are concentrated in the enterprise-priced tools (Sprout, Agorapulse, Hootsuite).

### Cited Findings

**Per-vendor directories (primary)**
- Buffer lists 25 integrations in five groups: AI & Agents (ChatGPT, Claude, Cursor, Grok, Perplexity Web); Automation (IFTTT, Make, Microsoft Power Automate, n8n, Raycast, Zapier); Content Creation (Canva, OpenAI, Unsplash); Media & Storage (Dropbox, Google Drive, Google Photos, OneDrive); Publishing (Bitly, Evergreen Content Poster, Feedly, Nelio Content, Quuu, WordPress, WriteStack) — [Buffer integrations](https://buffer.com/integrations)
- Metricool lists: ad platforms (Facebook Ads, Google Ads, TikTok Ads); files/design (Google Drive, Canva, Adobe Express incl. Adobe Stock); automation (Zapier, Make); reporting (Looker Studio); websites/e-commerce (WordPress, Shopify, Squarespace); AI (Claude connector, ChatGPT connector, Metricool MCP); Chrome extension — [Metricool integrations](https://metricool.com/integrations/)
- Planable lists: Planable MCP (Claude, ChatGPT, Gemini custom connector) giving assistants access to workspaces, drafts, comments and approvals; a public REST API with bearer token (Pro and Enterprise only); Zapier; viaSocket; Canva (two-way: send designs to and pull assets from the Media Library); Slack (receives notifications including approval requests); Asana and Salesforce are cited only as examples of what the API can do — [Planable integrations](https://planable.io/integrations/)
- Agorapulse lists: Google Analytics, Looker Studio; Salesforce, HubSpot; Slack, Google Drive, Canva, Bitly, Tenor, Microsoft Teams, Zapier; "ChatGPT, Claude & Copilot Studio" under "API & MCP"; a Reports Open API — [Agorapulse integrations](https://www.agorapulse.com/integrations/)
- Sprout Social lists: BI (Salesforce Marketing Intelligence Cloud, Tableau); help desk (HubSpot, Microsoft Dynamics 365, Salesforce Agentforce Service, Zendesk); CRM (Marketo, Dynamics 365, Salesforce Marketing/Sales); reviews (Apple App Store, Facebook Page Reviews, Glassdoor, Google Play, Trustpilot, Yelp); social commerce (Facebook Shops, Shopify, WooCommerce); link tracking (Bit.ly, Google Analytics); Workflow & DAM (Adobe Experience Manager, Adobe Express, Bynder, Canva Design Importer, Canva Draft Publisher, Dropbox, Google Drive, Microsoft Teams, Opal, Optimizely, Slack, Slate) — [Sprout Social integrations](https://sproutsocial.com/integrations/)
- Hootsuite's app directory front page shows Featured (Bynder, Plan with monday.com, Cloudinary, Wrike), Popular (Vidyard, Notion, WordPress.com, Lately AI, Brightcove, Dribbble, Figma, Miro, Shopview for Magento) and categories "Create & Find Content", "Analytics & Social Listening", "Review & Reputation Management", "Customer Support & Engagement", "Campaigns & Ads", "Influencer Marketing"; no total count is shown on that page — [Hootsuite app directory](https://apps.hootsuite.com/)
- Later's partners page lists product integrations with Google, Dropbox, Adobe, Mailchimp, Canva, Bazaarvoice, Yotpo, PowerReviews and Everflow, without describing what each does — [Later partners](https://later.com/partners)
- Publer has a Zapier app with 22 triggers, 12 actions and 4 searches (see section 4) — [Zapier: Publer](https://zapier.com/apps/publer-k20/integrations); Publer is also listed inside the Canva Apps Marketplace — [Canva: Publer app](https://www.canva.com/your-apps/AAF6ayd-yRo/publer). Search-level evidence (Publer help centre snippets, not opened page by page) says Publer imports media from Google Drive, Dropbox and Unsplash, offers Canva and VistaCreate as design tools, and exposes an API, an MCP server and webhooks — [Publer help](https://publer.com/help)
- Postiz documents 34 posting providers (X, LinkedIn, LinkedIn Page, Facebook, Instagram, Instagram Standalone, Threads, Bluesky, Mastodon, Google My Business, MeWe, Farcaster/Warpcast, YouTube, TikTok, Reddit, Pinterest, Discord, Slack, Telegram, Dribbble, Skool, Whop, Tumblr, Nostr, VK, Lemmy, Medium, Dev.to, Hashnode, WordPress, Listmonk, Kick, Twitch, Moltbook), a public API with OpenAPI spec, MCP, CLI, webhooks, "plugs", RSS auto-posting, an OAuth2-for-apps flow, an in-app Polotno design editor, Cloudflare R2 storage and short links. Its docs index has no page for n8n, Make, Zapier or Canva — [Postiz docs index](https://docs.postiz.com/llms.txt)
- Postiz's only named "third-party integration" is HeyGen (AI video): the user enters their own API key under Integrations and imports generated assets in the composer; the service bills the user directly — [Postiz third-party integrations](https://docs.postiz.com/general/automations/third-party)
- Mixpost's services docs list: social (Facebook & Instagram, Instagram standalone, Threads, Bluesky, Google, Pinterest, LinkedIn, TikTok, X); AI providers (Anthropic, DeepSeek, Gemini, Groq, Mistral, Ollama, OpenAI, OpenRouter, xAI); media (Giphy, Tenor, Pexels, Adobe Express); URL shorteners (Bitly, YOURLS, Shlink); SSO (Keycloak, Authentik, Okta); payments (Stripe, Paddle, Paystack) — [Mixpost services](https://docs.mixpost.app/services/)
- Mixpost docs navigation also has API, Webhooks, MCP and CLI sections; n8n, Zapier and Make are not mentioned — [Mixpost docs](https://docs.mixpost.app/)

**Frequency tally across the 10 tools (counted only from the pages above)**
- Canva: Buffer, Metricool, Planable, Agorapulse, Sprout (two separate integrations), Later, Publer = 7 confirmed — sources as above
- AI assistant / MCP connector: Buffer, Metricool, Planable, Agorapulse, Publer, Postiz, Mixpost = 7 — sources as above
- Google Drive: Buffer, Metricool, Agorapulse, Sprout, Publer (+ Later lists "Google" without detail) = 5-6 — sources as above
- Zapier: Buffer, Metricool, Planable, Agorapulse, Publer = 5 — sources as above
- Dropbox: Buffer, Sprout, Later, Publer = 4 — sources as above
- Bitly: Buffer, Agorapulse, Sprout, Mixpost = 4 — sources as above
- Adobe Express: Metricool, Sprout, Mixpost (+ Later lists "Adobe") = 3-4 — sources as above
- Slack notifications: Planable, Agorapulse, Sprout = 3 (Postiz has Slack only as a posting channel) — sources as above
- Microsoft Teams: Agorapulse, Sprout = 2; Make: Buffer, Metricool = 2; n8n: Buffer only = 1; Unsplash: Buffer, Publer = 2; OneDrive: Buffer = 1 — sources as above
- Salesforce + HubSpot: Agorapulse, Sprout = 2; Shopify: Metricool, Sprout = 2; Looker Studio: Metricool, Agorapulse = 2; Google Analytics: Agorapulse, Sprout = 2; WordPress: Buffer, Metricool, Hootsuite (WordPress.com), Postiz (as channel) = 4 — sources as above

### Inferences
- For an agency-sized product the demand-ranked shortlist is: Canva, cloud-storage pickers (Drive first, then Dropbox/OneDrive), an MCP/AI connector (Spark already has one), Zapier (plus Make/n8n), Slack approval notifications, a stock-media picker, a link shortener (Spark already has one).
- CRM/BI integrations (Salesforce, Tableau, Dynamics, Zendesk) signal enterprise positioning and are not evidence of small-agency demand.
- Both open-source competitors avoided Canva and embedded an editor instead (Postiz: Polotno; Mixpost: Adobe Express), which suggests Canva's OAuth/review model is awkward for self-hosted software where every install has its own domain.
- Neither Postiz nor Mixpost documents a Zapier/Make/n8n app; they rely on API + webhooks + MCP. A verified n8n node would be a differentiator for a self-hosted tool, since n8n is itself self-hosted.

### Gaps
- Hootsuite: official integrations pages 404; the directory front page does not show Canva, Adobe Express, Drive, Slack, Teams, Salesforce or Zapier. Third-party aggregators surfaced in search claim those exist and quote "100+", "140+" or "150+" apps, but I did not open or verify them.
- Later: no description of what each integration does; its Zapier page (old) says Later has not built a Zapier integration, unverified for 2026 — [Zapier: Later.com](https://zapier.com/apps/later-com/integrations)
- Publer's own integrations page could not be fetched; whether Publer has n8n or Make apps is unconfirmed.
- A secondary listing claims Postiz has a native n8n node, Make app and Zapier integration; this is not in Postiz's docs index and was not verified on GitHub/npm.
- Postiz and Mixpost GitHub repos were not inspected directly.

---

## 2. Zernio in late 2026: what exists beyond posts/analytics/inbox, and how do alternatives compare?

### Takeaway
Zernio has grown from a posting API into a very broad platform: ads (including boosting existing posts on five networks), Drive/OneDrive files with a Google Picker flow, Shopify/WooCommerce commerce, blog publishing, GA4, calendar, email, Slack/Discord/Telegram/WhatsApp messaging, comment-to-DM automations, workflows, bulk CSV, validation, a hosted OAuth MCP server, CLI and eight SDKs, all without plan gating. Several integrations Spark lacks (cloud storage, product catalogues, boosting, chat notifications, GA4) could therefore be built on the Zernio key Spark already holds instead of on separate vendor OAuth apps.

### Cited Findings

**Identity and pricing**
- Capterra's listing for the product formerly called "Late" is now titled Zernio (URL path still `/Late/`) — [Capterra](https://www.capterra.com/p/10036198/Late/); a competitor page says Late (getlate.dev) renamed itself Zernio with identical routes and working keys — [Upload-Post: Zernio alternative](https://www.upload-post.com/zernio-alternative/). Sources disagree on the rename date ("2026" vs a redirect in September 2026); Zernio's own pricing page does not mention the former name — [Zernio pricing](https://zernio.com/pricing)
- Pricing is per connected account, graduated: accounts 1-2 free, 3-10 $6/mo each, 11-100 $3/mo each, 101+ $1/mo each (10 accounts = $48/mo, 20 = $78, 100 = $318). Slack counts as one account per workspace; ad accounts and blog sites (WordPress, Shopify, Wix, Webflow) also count — [Zernio pricing](https://zernio.com/pricing)
- "Every feature is available on every account" (scheduling, analytics, comments and reviews, webhooks, Blogs API, creator campaigns). Metered extras: messages (10,000 sent/month free, then $1 per 10,000), automations (2,000 runs/month free then $2 per 1,000; from 1 Dec 2026 automations without a card pause at 2,000 runs), X API passed through at X's rates ($0.005 read, $0.015 post, $0.20 post with URL), website tracking events (100,000/month free) — [Zernio pricing](https://zernio.com/pricing)

**Platforms**
- Social posting: X, Instagram, Facebook, LinkedIn, TikTok, YouTube, Pinterest, Reddit, Bluesky, Threads, Google Business Profile, Snapchat (closed beta). Messaging: WhatsApp, RCS, iMessage, Telegram, Discord, Slack, LINE, WeChat. Advertising: Meta, Google, LinkedIn, TikTok, Pinterest, X, OpenAI, Reddit, Microsoft. Blogs & commerce: Shopify, WordPress, Wix, Webflow. CRM: HubSpot. Analytics: Google Analytics. Payments: Stripe. Email & calendar: Google, Microsoft, IMAP — [Zernio platforms](https://docs.zernio.com/platforms.mdx)
- Reddit subreddit/flair/search endpoints currently return 503 `PLATFORM_DISABLED` because Reddit blocked third-party API access; Reddit Ads is unaffected — [Zernio docs index](https://docs.zernio.com/llms.txt)

**Endpoint groups beyond posts/analytics/inbox (all from the docs index)** — [Zernio docs index](https://docs.zernio.com/llms.txt)
- Ads: campaigns, ad sets, ads, boost posts, audiences, targeting search, reach estimates, creatives, ad library search (Meta and LinkedIn public ad libraries), ad rules/automations, lead forms and leads (Meta, Google, LinkedIn, TikTok), conversions API, tracking pixels, product catalogs, "List Instagram posts to boost".
- Files: Google Picker sessions, list/upload/download/rename/trash/share for Google Drive and OneDrive; Drive/OneDrive files usable as post media; `file.picked` webhook.
- Commerce: products, orders, customers, discounts, collections, inventory, Meta catalog sync; mostly Shopify with some WooCommerce. Blogs: CRUD for articles on Shopify, WordPress, Wix, Webflow.
- Analytics extras: GA4 metadata, report and realtime endpoints; follower stats; "authenticity scores"; Instagram story insights; inbox analytics (volume, response time, heatmap).
- Calendar (Google/Microsoft events, free/busy, RSVPs), Email (Gmail/Outlook/IMAP threads, drafts, scheduled sends, open/click tracking), Contacts with custom fields and bulk import (up to 1,000), Broadcasts, Sequences, Workflows (conversation graphs, API-triggered runs).
- Comment Automations: keyword-triggered comment-to-DM on Instagram and Facebook; public-reply-only automations on TikTok, Threads, LinkedIn, YouTube; Instagram story-reply and story-mention triggers.
- Posts: create/update/delete/unpublish/pin/retry/approve, bulk upload from CSV (5,000-row cap), idempotency; Queue schedules (slots, preview upcoming times); post recycling (`post.recycled`).
- Validate: media URL check, character counts, full post validation. Media: presigned uploads and per-platform media preparation (video re-encoding, image conversion).
- Platform specifics: Instagram audio search, business discovery, mentions, stories, live broadcasts, tagged media, collaborators, publishing quota; TikTok creator info and trending music; X polls via `platformSpecificData`; Twitter engagement (bookmark, follow, retweet, search); LinkedIn mention URN resolution; YouTube playlists and video transcripts; Pinterest boards; Stories publishing on Instagram, Facebook and Snapchat.
- Reviews: list and reply for Facebook and Google Business Profile; Google Business location details, media, attributes, menus.
- Slack (list members who can receive a DM), Discord (roles, threads, pins, scheduled events, DMs), Telegram bot commands, WhatsApp (templates, flows, groups, catalogs, calling), SMS/RCS/iMessage/voice.
- Platform apps (bring-your-own OAuth app), Content Retention (zero-retention switch), Logs (publishing/connection/webhook/messaging, 90 days), Usage, Users and roles, SSO/SCIM.
- Creator Campaigns (invites, submissions, payouts, launch approved posts as Meta or TikTok ads), HubSpot (inbox contact sync, closed-won deals as sales), Stripe (payments as sales).
- Official SDKs: .NET, Go, Java, Node.js, PHP, Python, Ruby, Rust; integrations for Make, n8n, Zapier and OpenClaw; a Chat SDK adapter; migration guides from Ayrshare, Kapso, Twilio.

**Webhooks (verbatim event names from the docs index)** — [Zernio docs index](https://docs.zernio.com/llms.txt)
- Social: `post.scheduled`, `post.published`, `post.failed`, `post.partial`, `post.cancelled`, `post.recycled`, `post.platform.published`, `post.platform.failed`, `post.platform.deleted`, `post.external.created|updated|deleted` (native posts detected), `post.tiktok.url_resolved`, `post.tracking_completed`, `post.authenticity_changed`, `analytics.synced`.
- Inbox: `comment.received`, `mention.received` (Instagram, Facebook, LinkedIn), `message.received|sent|delivered|read|failed|edited|deleted|played`, `reaction.received`, `review.new|updated|deleted|restored`, `conversation.started`, `contact.*`, `sequence.enrolled|exited`, `workflow.run.started|completed|failed`, `email.*`, `calendar.event.*`, `file.created|updated|deleted|picked`.
- Account: `account.connected`, `account.disconnected`, `account.permissions_changed`, `account.rate_limited`, `api.changelog.published`, `webhook.test`.
- Commerce: `commerce.order.created|updated|refunded`, `commerce.product.created|updated|deleted`.
- Ads: `ad.created`, `ad.review.approved|rejected`, `ad.status_changed`, `ad.delivery_issue`, `campaign.created|updated|status_changed`, `campaign.budget.depleted`, `lead.received`, `conversion.received`, `ad_rule.triggered`.
- Webhook management endpoints: create, update, delete, test, redeliver, delivery logs (30 days).

**MCP, CLI**
- Zernio's hosted MCP server is `https://mcp.zernio.com/mcp` (remote HTTP), sign-in via OAuth, with API-key config or a local bridge for clients that cannot sign in; covers posting, scheduling, DMs and comments, email, analytics and ads; listed in the MCP Registry as `com.zernio/zernio`; a Claude Code plugin with skills and slash commands exists; in ChatGPT it covers posts and analytics only — [Zernio MCP](https://docs.zernio.com/for-you/mcp.mdx)
- Zernio's integrations for n8n, Make, Zapier and OpenClaw are described as "create posts" integrations — [Zernio resources](https://docs.zernio.com/resources.mdx)

**Alternatives (mostly vendor-authored comparisons; treat as secondary)**
- A competitor's table (endpoints checked 23 Oct 2026): Upload-Post — 22 networks, remote MCP with OAuth 2.1 or API key, 50+ tools, FFmpeg video editing, comment-to-DM; Ayrshare — 14 networks, MCP at `api.ayrshare.com/mcp`, API key only, 33 tools incl. ads; Postiz — about 30 channels, 13 tools, no comments; Buffer — `mcp.buffer.com/mcp`, 13 networks incl. Substack; Metricool — `ai.metricool.com/mcp`; Mixpost — MCP on own instance, about 30 tools (Pro); Post for Me — local MCP only, 9 networks; bundle.social — local MCP, 15 networks. The same table credits Zernio with "9 networks", which contradicts Zernio's own list of 12 social platforms — [Upload-Post MCP comparison](https://www.upload-post.com/best-social-media-mcp-servers/); contradicted by [Zernio platforms](https://docs.zernio.com/platforms.mdx)
- Ayrshare's docs index shows 14 networks, auto-hashtags, a Translate Post endpoint, Unsplash image URLs as media, duplicate-post prevention, Node and Python SDKs — [Ayrshare docs index](https://www.ayrshare.com/docs/llms.txt); Ayrshare also publishes a Notion integration that posts from a Notion database — [Ayrshare Notion integration](https://www.ayrshare.com/integration/notion.md)
- Search-level price points (vendor blogs, not individually opened; sources disagree): Ayrshare from about $149/mo; Post for Me $10/mo for 1,000 posts with unlimited accounts; Upload-Post free tier of 2 profiles/10 uploads; bundle.social free tier of 20 posts/3 accounts and Pro about $100/mo; Outstand a low base fee plus about $0.01 per post — [Postgate pricing comparison](https://postgate.studio/blog/social-media-api-pricing-comparison), [PostPeer comparison](https://www.postpeer.dev/blog/best-social-media-posting-apis), [Blotato comparison](https://www.blotato.com/blog/best-social-media-api-tools)

### Inferences
- The cheapest integration path for Spark is "Zernio-first": Drive/OneDrive picker, Shopify/WooCommerce product feed, WordPress blog publishing, GA4 reports, boosting, Slack/Discord/Telegram delivery and comment-to-DM automations are all reachable through the existing connector, each costing one extra connected account ($1-6/month) rather than a vendor app review.
- Features Zernio appears not to cover, based on the index: Canva/design tools, stock media, Dropbox, Notion/Airtable/Sheets, link shortening, AI caption/hashtag generation, and fediverse/long-tail networks (Mastodon, Nostr, Lemmy, Medium, Dev.to, Tumblr, Twitch) that Postiz supports. Ayrshare's auto-hashtags and translate endpoints and Upload-Post's FFmpeg editing are the few posting-API features with no visible Zernio equivalent.
- Dependence on Zernio for chat notifications means a Slack message becomes a billable connected account per workspace; a plain incoming webhook (section 5) is free.
- Reddit is effectively unavailable through any third-party API in late 2026 if Zernio's note is accurate.

### Gaps
- Zernio changelog entries (dates of each addition) could not be read; an API feed exists at `GET /v1/changelog` and a `api.changelog.published` webhook, neither was called.
- No dedicated Threads/Bluesky feature page was read; per-network feature depth (e.g. Threads polls, Bluesky threads) is unconfirmed beyond "Bluesky settings" and X polls.
- No link-shortener, AI-generation or hashtag endpoints were seen in the index; absence is inferred from summaries of a 978 KB file, not from a full-text search.
- Outstand, bundle.social, Post for Me and Late-era docs were not read first-hand.

---

## 3. Design and assets: Canva Connect, Adobe Express, Figma, cloud pickers, stock media, Frame.io

### Takeaway
Canva is feasible but review-bound: a public Connect integration must be reviewed by Canva, and private (unreviewed) integrations require Canva Enterprise; autofill of brand templates works for users on Pro/Teams/Enterprise. Adobe Express Embed is effectively closed to small vendors since it now needs business approval. Cloud pickers are low-friction (Google `drive.file` is non-sensitive; Dropbox Chooser needs no approval), Pexels and Unsplash are free with attribution rules, and the Tenor GIF API was shut down on 30 June 2026.

### Cited Findings

**Canva**
- The Connect APIs are REST APIs for creating and syncing assets, designs and comments from an external platform (example flow: upload assets, create a design for the user to edit, export the finished design back); a starter kit and a public OpenAPI description are provided. Preview APIs may break without versioning and public apps using them will not pass review — [Canva Connect docs](https://www.canva.dev/docs/connect/)
- Autofill and brand templates require the user to be on Canva Pro (incl. Education/Nonprofits), Teams or Enterprise, with MFA enabled; scopes: `design:content` read/write, `design:meta` read, `brandtemplate:meta` read, `brandtemplate:content` read, `asset` read/write; "usage limits will be introduced in the future" — [Canva autofill guide](https://www.canva.dev/docs/connect/autofill-guide/)
- Public apps ("Anyone on Canva") are reviewed by Canva and then appear in the Apps Marketplace; private apps ("Restricted to your Canva team") are available only to teams on an Enterprise plan and are approved by team admins; the audience cannot be changed after creation — [Canva: creating integrations](https://www.canva.dev/docs/connect/creating-integrations/)
- Submission checklist: public-suitable app name, at least one non-local redirect URL, valid webhook URL if `collaboration:event` is enabled, valid return URL if Return navigation is enabled, Canva brand guidelines, production-grade hosting, a test account and documentation for reviewers; up to 5 submissions per day; no fixed review timeline — [Canva submission checklist](https://www.canva.dev/docs/connect/submission-checklist/)
- Canva describes the Apps SDK, Connect APIs and MCP as now unified in a "Canva Developers SDK" (search-level summary of Canva's developer blog; page not opened in full) — [Canva developer blog](https://www.canva.dev/blog/developers/canva-and-coding-agents-platforms/)
- Competitor patterns: Sprout lists two separate Canva integrations ("Design Importer" and "Draft Publisher") — [Sprout integrations](https://sproutsocial.com/integrations/); Planable's is two-way with its Media Library — [Planable integrations](https://planable.io/integrations/); Publer ships an app inside Canva's marketplace for scheduling and file import/export, free on any Canva plan — [Canva: Publer app](https://www.canva.com/your-apps/AAF6ayd-yRo/publer)

**Adobe Express Embed SDK**
- Offers the full editor, modules (Generate image, Edit image, Template Browser, Design Viewer) and quick actions (resize, crop, trim, remove background, compress) — [Adobe Express Embed SDK guides](https://developer.adobe.com/express/embed-sdk/docs/guides/)
- "Access to the Adobe Express Embed SDK now requires a business approval process" via a Sales form; priority goes to Adobe Express enterprise customers, paid strategic partnerships, or a user base of about 1 million or more; personal/experimental projects are not the focus; unapproved integrations show a red banner; already-approved integrations stay active until December 2027; one API key covers up to five domains; users need an Adobe ID to save; no price list — [Adobe Embed SDK FAQ](https://developer.adobe.com/express/embed-sdk/docs/guides/troubleshooting/faq/)
- Mixpost still documents Adobe Express as a media service — [Mixpost services](https://docs.mixpost.app/services/)

**Cloud storage pickers**
- Google: `drive.file` is the recommended, non-sensitive scope and is designed to be used with the Google Picker; it grants access only to files the user picks or the app creates — [Google Drive API scopes](https://developers.google.com/workspace/drive/api/guides/api-specific-auth)
- Dropbox Chooser: needs an app key and a list of hosting domains; handles authentication itself; preview links or direct links (direct links expire after four hours); multiselect and extension filters; "Using the Chooser doesn't require production approval" — [Dropbox Chooser](https://docs.dropboxapi.com/dropbox-api/docs/pre-built-components/chooser)
- Zernio's Files API offers Google Picker sessions and Drive/OneDrive file operations with a `file.picked` webhook — [Zernio docs index](https://docs.zernio.com/llms.txt)

**Stock media and GIFs**
- Unsplash API guidelines: hotlink the returned `photo.urls`; call `links.download_location` when a user picks a photo; credit photographer and Unsplash with UTM-tagged links; no Unsplash name/logo in the app name; no automated/bulk use; end users must not be required to register their own Unsplash developer account (use a proxy with a shared key) — [Unsplash API guidelines](https://help.unsplash.com/en/articles/2511245-unsplash-api-guidelines)
- Pexels API: free; key issued instantly; default 200 requests/hour and 20,000/month; higher limits free on request with proof of attribution; prominent link back to Pexels and photographer credit where possible; video endpoints under `/v1/videos/` — [Pexels API docs](https://www.pexels.com/api/documentation/)
- Google sunset the Tenor API on 30 June 2026 (announced 13 Jan 2026; new key registration disabled then) — [9to5Google](https://9to5google.com/2026/06/30/google-tenor-api-gif-updates/), [AlternativeTo news](https://alternativeto.net/news/2026/7/google-discontinues-tenor-gif-api-for-developers-impacting-discord-x-whatsapp-and-bluesky/)
- Klipy is the most-cited free Tenor/GIPHY replacement with a similar API and a built-in ad-revenue model (secondary source) — [Zuplo on Klipy](https://zuplo.com/learning-center/klipy-api.md)
- Tenor is still listed by Agorapulse and Mixpost — [Agorapulse integrations](https://www.agorapulse.com/integrations/), [Mixpost services](https://docs.mixpost.app/services/)

**Figma**
- Hootsuite's directory lists a Figma app among "Popular" — [Hootsuite app directory](https://apps.hootsuite.com/)

### Inferences
- For self-hosted Spark, Canva's model is the main obstacle: one public integration has fixed redirect URLs, but every Spark install has its own domain. Options are (a) each agency registers its own Canva integration (only unreviewed if "private", i.e. Enterprise), (b) a vendor-hosted OAuth relay with one reviewed public integration, or (c) a Canva app inside Canva that pushes exports to Spark's REST API (Publer's pattern). The Unsplash rule against requiring per-user developer accounts raises the same shared-key/proxy question.
- Pexels is the lowest-friction stock source (per-install API key fits Spark's "connector = API key" model and is explicitly permitted); Unsplash is a worse fit for bring-your-own-key.
- An embedded open editor (Polotno, as Postiz does) avoids all vendor approvals; Adobe Express Embed should be treated as unavailable.
- Any GIF picker should target Klipy or GIPHY; competitor directories still naming Tenor are stale.

### Gaps
- Frame.io: not researched; no competitor directory read here lists it.
- Figma API/plugin route: not researched beyond the Hootsuite listing.
- OneDrive File Picker requirements (Entra app registration): not fetched.
- GIPHY 2026 production-key pricing: no primary source found; secondary sources call it expensive.
- Unsplash demo vs production rate limits were not on the page read.
- Canva Connect rate limits, exact review duration, and whether a Canva MCP server can be used headlessly by an agent were not confirmed from Canva's docs.

---

## 4. Workflow automation: getting listed on Zapier, Make and n8n; typical triggers/actions

### Takeaway
All three are free to publish but reviewed: Zapier answers within about a week and adds a 90-day beta, Make's QA review has no stated timeline (months reported anecdotally), and n8n verified community nodes take up to four weeks and since 1 May 2026 must be published from GitHub Actions with provenance. The triggers users expect are post lifecycle events (created, scheduled, pending approval, approved, published, failed) and the actions are create/queue a post, upload media and create an idea.

### Cited Findings
- Zapier: submit via the Platform UI; a Zapier developer responds within one week; approved apps are listed with a Beta tag for 90 days, then become public and join the Partner Program; building and publishing are free; no minimum user count is stated in the guide — [Zapier: publish a public integration](https://docs.zapier.com/platform/publish/public-integration)
- Make: the app must connect to a service Make does not already integrate; Make's QA team reviews code against best practices and test scenarios; a published app cannot be unpublished; every later change needs Make's approval — [Make app review overview](https://developers.make.com/custom-apps-documentation/app-review/overview); a community thread reports an app pending review for several months — [Make community](https://community.make.com/t/whiteboard-app-review-pending-for-several-months-request-for-status-and-next-steps-2312107/115849)
- n8n: package name `n8n-nodes-*` (or scoped), keyword `n8n-community-node-package`; verified nodes may not use runtime dependencies, must follow technical/UX guidelines and include a README; submit through the Creator Portal (creators.n8n.io/nodes); review can take up to four weeks; from 1 May 2026 verified nodes must be published via a GitHub Actions workflow with a provenance statement; nodes competing with n8n's paid features may be rejected — [n8n: submit community nodes](https://docs.n8n.io/integrations/creating-nodes/deploy/submit-community-nodes/)
- Buffer on Zapier: 9 triggers (New Channel, New Contribution Item, New Draft Item, New Idea Item, New Queue Item, New Sent Item, New Tag, Tag Assigned to an Idea, Tag Assigned to a Post or Draft) and 3 actions (Create Idea, Pause Queue, Add to Queue) — [Zapier: Buffer](https://zapier.com/apps/buffer/integrations)
- Publer on Zapier: 22 triggers incl. Post Created, Post Scheduled, Post Pending Approval, Post Approved, Post Published, Post Failed, Post Status Updated, New Draft, New Idea, New Media Uploaded, Account Connected/Disconnected, Analytics Updated, Post Performance Threshold, Top Posts of Week; 12 actions incl. Create Post, Auto Schedule Post, Schedule Recurring Post, Schedule Recycling Post, Upload Media, Suggest Best Time, Export Analytics Report; 4 searches (Find Post, Find Media, Find Best Time to Post, Find Analytics by Date Range) — [Zapier: Publer](https://zapier.com/apps/publer-k20/integrations)
- Apps most often paired with Buffer on Zapier: Google Drive, Airtable, Notion, WordPress, Google Sheets, YouTube, Slack, Trello, Gmail, Dropbox, Google Calendar, monday.com, ClickUp, Feedly, Shopify, Telegram, Discord, Asana, HubSpot — [Zapier: Buffer](https://zapier.com/apps/buffer/integrations); with Publer: Google Drive, ClickUp, Telegram, Google Calendar, YouTube, ChatGPT, Trello, monday.com, Microsoft Teams, GA4, Cloudinary, HeyGen, Mailchimp, OneDrive — [Zapier: Publer](https://zapier.com/apps/publer-k20/integrations)
- Buffer lists six automation platforms (IFTTT, Make, Power Automate, n8n, Raycast, Zapier) — [Buffer integrations](https://buffer.com/integrations)

### Inferences
- The Zapier pairing lists are a proxy for long-tail demand: Sheets/Airtable/Notion (content calendars), Drive/Dropbox (assets), Slack/Teams/Telegram/Discord (notifications), Google Calendar, WordPress/Shopify/YouTube (content sources). One automation connector covers all of them indirectly.
- Spark already has the prerequisites (REST API; MCP). What is missing for listing is outbound webhooks or polling endpoints for triggers and stable API-key/OAuth auth. A generic signed outbound-webhook feature gives immediate n8n/Make/Zapier compatibility through their generic Webhook/HTTP modules without any review.
- For a self-hosted product, each user's base URL differs, so Zapier/Make apps need a "instance URL + API key" auth form; n8n credentials handle this natively, making an n8n node the most natural first listing.

### Gaps
- Zapier's detailed integration publishing requirements (linked from the guide) and Partner Program tiers were not read.
- n8n Cloud availability rules for verified community nodes were not on the page read.
- Sprout/Hootsuite/Agorapulse Zapier trigger lists were not checked.

---

## 5. Notifications and approvals in chat: Slack, Teams, Discord, Telegram, WhatsApp

### Takeaway
Slack is the only chat integration that recurs across competitors (Planable, Agorapulse, Sprout), with Teams second (Agorapulse, Sprout); posting needs only an incoming webhook, but in-chat Approve/Reject buttons need a real Slack app with an interactivity Request URL (and on Discord an application-owned webhook or bot). Teams' old Office 365 connector webhooks were disabled in May 2026, Telegram bots need no review, and WhatsApp notifications are paid templates.

### Cited Findings
- Planable's Slack integration "receives Planable notifications, including approval requests" — [Planable integrations](https://planable.io/integrations/); Agorapulse lists Slack and Microsoft Teams under Productivity — [Agorapulse integrations](https://www.agorapulse.com/integrations/); Sprout lists Slack and Microsoft Teams under Workflow & DAM — [Sprout integrations](https://sproutsocial.com/integrations/)
- Slack: apps may post no more than one message per second per channel (incoming webhooks and `chat.postMessage` alike), short bursts tolerated; 429 with `Retry-After` on excess — [Slack rate limits](https://docs.slack.dev/apis/web-api/rate-limits)
- Slack interactive messages: button clicks are sent as an HTTP POST with a `payload` field to the app's configured Request URL; the app must acknowledge on that request and should keep the `response_url` for follow-ups — [Slack: creating interactive messages](https://docs.slack.dev/messaging/creating-interactive-messages)
- Slack's own hosted MCP server went GA on 17 Feb 2026 at `https://mcp.slack.com/mcp` with user-token OAuth (secondary sources citing Slack's changelog) and is limited to Marketplace and internal apps — [mcpyet remote MCP guide](https://mcpyet.com/guides/remote-mcp-servers/), [Digital Applied](https://www.digitalapplied.com/blog/official-mcp-servers-for-marketing-teams)
- Microsoft Teams: Office 365 connectors (legacy incoming webhooks) were scheduled for final disablement 18-22 May 2026 per Message Center item MC1181996; replacement is webhooks created through Workflows (Power Automate) — [MC1181996 mirror](https://mc.merill.net/message/MC1181996), [Virto guide](https://www.virtosoftware.com/microsoft-365-guides/office-365-connectors/); some April 2026 Microsoft Q&A replies cited 30 April 2026 instead — [Microsoft Q&A](https://learn.microsoft.com/en-sg/answers/questions/5854971/will-teams-incoming-webhooks-stop-delivering-alert)
- Discord: webhooks need no bot user or authentication (id + token in the URL), accept up to 10 embeds; non-application-owned webhooks cannot send interactive components such as buttons (only non-interactive ones, with `with_components=true`); interactive components require an application-owned webhook — [Discord webhook resource](https://docs.discord.com/developers/resources/webhook)
- Telegram: bots are created with @BotFather, which issues a token; inline keyboards send `callback_query` updates answered with `answerCallbackQuery`, and messages can be edited in place; bots in groups run in privacy mode by default; no review process is described — [Telegram bot features](https://core.telegram.org/bots/features)
- WhatsApp: Meta's pricing page covers per-message charges for marketing, utility, authentication and service categories, with volume tiers for utility/authentication; utility templates inside an open customer-service window are free, outside it they are charged — [WhatsApp Business Platform pricing](https://developers.facebook.com/documentation/business-messaging/whatsapp/pricing); Zernio states WhatsApp service messages were free until 30 Sep 2026 and are then billed at Meta's utility rate after 1,000 free per number per month — [Zernio pricing](https://zernio.com/pricing)
- Zernio exposes Slack, Discord, Telegram and WhatsApp as messaging platforms on the same API Spark already uses; Slack counts as one connected account per workspace — [Zernio platforms](https://docs.zernio.com/platforms.mdx), [Zernio pricing](https://zernio.com/pricing)

### Inferences
- Tier 1 (hours of work, no review): "paste a webhook URL" connectors for Slack, Discord and Teams (Workflows URL) that post approval-needed / published / failed notifications with a deep link back to Spark. This matches Spark's existing connector model.
- Tier 2: interactive approve/reject. A self-hosted Spark needs a publicly reachable Request URL; each agency would create its own Slack app from a manifest (no Marketplace listing needed for a single-workspace internal app). Telegram is the cheapest interactive channel: token only, callback buttons, long-polling works behind NAT.
- WhatsApp is poor value for internal approvals (template approval, per-message cost) but relevant for client approvals in markets where clients live in WhatsApp; it could ride on Zernio's WhatsApp support.
- Client approval is already an established differentiator for Planable; Slack approval-request notifications are the minimum competitive bar.

### Gaps
- Whether any competitor supports approving from inside Slack/Teams (buttons) rather than just notifying could not be confirmed; searches returned nothing specific.
- Slack's 3-second acknowledgement window, Socket Mode option, and Marketplace vs non-Marketplace rate-limit rules were not confirmed on the pages read.
- Telegram's rule that a user must first start the bot, and exact flood limits, were not on the page read.
- WhatsApp business-verification requirements and 2026 rate card were not read; one secondary notice mentions a pricing change in October 2026 — [Twilio notice](https://support.twilio.com/hc/en-us/articles/53100480177819-Notice-Changes-to-WhatsApp-s-Pricing-October-2026) (not opened).
- Teams Workflows webhook payload format (Adaptive Cards) and private-channel support were not confirmed.

---

## 6. Content sources: Notion, Airtable, Google Sheets, WordPress/Shopify/WooCommerce, YouTube/podcast feeds, calendars

### Takeaway
Among competitors, native content-source integrations are mostly WordPress and Shopify (plus RSS-style feeds); Notion, Airtable, Sheets and Google Calendar are overwhelmingly served through Zapier/Make rather than natively. Zernio already exposes Shopify/WooCommerce products, blog CRUD, YouTube playlists/transcripts and Google/Microsoft calendars on Spark's existing key.

### Cited Findings
- Buffer's Publishing category: WordPress, Feedly, Quuu, Nelio Content, Evergreen Content Poster, WriteStack, Bitly — [Buffer integrations](https://buffer.com/integrations)
- Metricool lists WordPress, Shopify and Squarespace — [Metricool integrations](https://metricool.com/integrations/); Sprout lists Shopify, WooCommerce and Facebook Shops as "Social Commerce" — [Sprout integrations](https://sproutsocial.com/integrations/); Hootsuite's directory shows Notion, WordPress.com and Shopview for Magento among popular apps — [Hootsuite app directory](https://apps.hootsuite.com/)
- Postiz documents RSS auto-posting as an automation — [Postiz docs index](https://docs.postiz.com/llms.txt)
- The top Zapier pairings for Buffer include Airtable, Notion, Google Sheets, Google Calendar, WordPress, YouTube, Feedly and Shopify — [Zapier: Buffer](https://zapier.com/apps/buffer/integrations)
- Ayrshare offers a Notion integration (internal Notion integration connected to a database, posting via Ayrshare's API) — [Ayrshare Notion integration](https://www.ayrshare.com/integration/notion.md)
- Zernio Commerce API: products, collections, inventory, discounts, orders for Shopify (some WooCommerce), with `commerce.product.created|updated|deleted` webhooks; Blogs API: articles on Shopify, WordPress, Wix, Webflow; Connect group includes YouTube playlists and video transcripts; Calendar API covers Google and Microsoft events — [Zernio docs index](https://docs.zernio.com/llms.txt)
- Zernio bulk upload from CSV accepts up to 5,000 rows — [Zernio docs index](https://docs.zernio.com/llms.txt)

### Inferences
- A "new product / new blog post / new video becomes a draft" automation is the commonly marketed content-source use case; Spark's RSS import already covers WordPress, Shopify blog, YouTube channel and podcast feeds (all publish RSS/Atom), so the incremental gain is structured product data (price, images, URL), obtainable via Zernio Commerce or Shopify/WooCommerce keys.
- Notion/Airtable/Sheets are best served by (a) CSV/Sheets import and (b) the automation connectors in section 4 rather than bespoke two-way sync; no competitor directory read here lists a native Notion or Airtable sync except Hootsuite's Notion app.
- A read-only ICS feed of the content calendar is cheap to add and overlaps with the Google Calendar demand visible in Zapier pairings, but no direct competitor evidence was found for it.

### Gaps
- Notion, Airtable and Google Sheets API auth models and limits were not researched first-hand.
- No evidence gathered on which competitors offer ICS/Google Calendar export or podcast-specific feeds.
- Whether Publer offers Google Sheets/CSV bulk import was not confirmed; a vendor blog claims Buffer has no Sheets/CSV import (unverified).

---

## 7. Ads/boosting: Meta, LinkedIn, TikTok Spark Ads; approvals; unified API coverage

### Takeaway
Building boosting directly means three separate approval programmes (Meta App Review + business verification for advanced `ads_management`, LinkedIn Advertising API tier upgrade, TikTok Marketing API app review plus creator authorisation codes for Spark Ads). Zernio removes that burden: it boosts existing posts on Meta, LinkedIn, TikTok, Pinterest and X with the first 500 active ads free.

### Cited Findings
- Meta Marketing API has two tiers: Limited access (default, heavily rate-limited, "for development only") and Full access (after App Review). Upgrade criteria: at least 500 successful Marketing API calls in the last 15 days (reduced from 1,500) and an error rate below 15%. Managing other people's ad accounts requires advanced access to `ads_management`/`ads_read`, approved per permission through App Review — [Meta Marketing API authorization](https://developers.facebook.com/docs/marketing-api/get-started/authorization)
- Meta: business verification is required for apps requesting advanced access (search-level summary of Meta's permissions reference) — [Meta permissions reference](https://developers.facebook.com/docs/permissions)
- LinkedIn Marketing API has Development and Standard tiers; all apps start in Development; the tier determines how many ad accounts can be managed; applications go through the Advertising API product in the Developer Portal — [LinkedIn Marketing API access tiers](https://learn.microsoft.com/en-us/linkedin/marketing/integrations/marketing-tiers)
- TikTok Spark Ads use a creator-generated authorisation code (valid 7 to 365 days) rather than standard OAuth; production Marketing API use requires app review, and each customer's Business Center must grant the app access (secondary sources) — [Unified.to](https://unified.to/blog/how_to_get_your_tiktok_ads_api_key), [Leadsie](https://www.leadsie.com/blog/tiktok-spark-ads-allowlisting-whitelisting)
- Zernio ads matrix: "Boost an existing post" supported on Meta, LinkedIn, TikTok, Pinterest and X (not Google); pause/resume/budget on all six; spend and performance metrics on all six; audiences on all six; reach estimates on Meta, LinkedIn, Pinterest, X; lead forms and product catalogs Meta only. Pricing: $0.01 per active ad per month after the first 500 free; only running or in-review ads count — [Zernio ad platform support](https://docs.zernio.com/platforms/advertising.mdx)
- Zernio also lists OpenAI Ads, Reddit Ads and Microsoft Ads as ad platforms, exposes `ad.review.approved|rejected`, `ad.status_changed`, `campaign.budget.depleted` webhooks, and returns 409 `ads_connection_required` when the ads connection is missing — [Zernio docs index](https://docs.zernio.com/llms.txt)
- Competitors: Metricool lists Facebook Ads, Google Ads and TikTok Ads — [Metricool integrations](https://metricool.com/integrations/); Hootsuite has a "Campaigns & Ads" directory category — [Hootsuite app directory](https://apps.hootsuite.com/); Ayrshare's MCP server includes ads tools — [Upload-Post MCP comparison](https://www.upload-post.com/best-social-media-mcp-servers/)
- Meta runs its own Ads MCP server at `mcp.facebook.com/ads` (open beta since 29 Apr 2026; developer-app path added 16 Jul 2026), with read and write tools (secondary source) — [Digital Applied](https://www.digitalapplied.com/blog/official-mcp-servers-for-marketing-teams)

### Inferences
- A "Boost this post" button in Spark, with budget/duration/audience and spend reporting, is achievable through the existing Zernio integration with no vendor review by Spark; it adds one connected ad account per network to the bill.
- Going direct to Meta is impractical for a self-hosted tool: each install would need its own reviewed Meta app, or the vendor must run a shared app and relay.
- Among mid-market competitors only Metricool lists ad platforms in its directory, so boosting is a differentiator rather than table stakes for small agencies.

### Gaps
- Meta's `object_story_id` boost mechanics and current Page-permission requirements were not confirmed from Meta docs.
- LinkedIn Standard-tier approval criteria and TikTok's own app-review documentation were not read (TikTok findings are secondary).
- Whether Hootsuite/Sprout/Agorapulse/Publer offer in-product boosting in 2026 was not verified.
- Zernio's per-network boost prerequisites (e.g. TikTok Spark authorisation code handling) were not read on the per-platform pages.

---

## 8. AI agent ecosystem in 2026: MCP servers, skills and standards relevant to Spark and Janus

### Takeaway
MCP is now standard equipment: seven of the ten competitors ship an MCP server or assistant connector, and the main marketing SaaS vendors (Canva, Notion, Slack, HubSpot, Meta Ads, Stripe, Semrush, Ahrefs) run official remote MCP servers with OAuth that an agent gateway like Janus could load. For exposing Spark outward, the relevant pieces are remote Streamable-HTTP MCP with OAuth (required by ChatGPT custom apps), a listing in the still-preview official MCP Registry, and Agent Skills (SKILL.md), with A2A at v1.0 but not yet used by social tools.

### Cited Findings

**Competitors' MCP/agent surfaces**
- Buffer lists ChatGPT, Claude, Cursor, Grok and Perplexity under "AI & Agents" — [Buffer integrations](https://buffer.com/integrations); Metricool lists Claude and ChatGPT connectors plus Metricool MCP — [Metricool integrations](https://metricool.com/integrations/); Planable MCP gives assistants access to workspaces, drafts, comments and approvals — [Planable integrations](https://planable.io/integrations/); Agorapulse lists "ChatGPT, Claude & Copilot Studio" — [Agorapulse integrations](https://www.agorapulse.com/integrations/)
- Endpoint details (checked 23 Oct 2026 by a competitor): Buffer `mcp.buffer.com/mcp` (OAuth or API key, about 20 tools); Metricool `ai.metricool.com/mcp` (OAuth or API key); Postiz `mcp.postiz.com/mcp` or self-hosted (13 tools); Mixpost on own instance `/mcp` (OAuth or personal key, about 30 tools, not in Lite); Ayrshare `api.ayrshare.com/mcp` (API key only, 33 tools); Zernio `mcp.zernio.com/mcp` (OAuth 2.1 + PKCE or API key, about 50 tools); Post for Me and bundle.social local-only — [Upload-Post MCP comparison](https://www.upload-post.com/best-social-media-mcp-servers/)
- Postiz's self-hosted MCP is reachable at `/mcp` (Bearer), `/mcp/:apiKey` and `/mcp-oauth` (search-level summary of Postiz docs) — [Postiz MCP docs](https://docs.postiz.com/mcp/introduction)
- Zernio's MCP loads common tools immediately and rarer ones on request, and is installable in Claude, ChatGPT, Claude Code, Cursor, Codex and VS Code — [Zernio MCP](https://docs.zernio.com/for-you/mcp.mdx)

**Official vendor MCP servers an agent could load (mostly secondary directories; verify per vendor)**
- Canva `https://mcp.canva.com/mcp` (OAuth; create, edit, export designs; some features need Pro); Notion `https://mcp.notion.com/mcp` (OAuth); Slack `https://mcp.slack.com/mcp` (GA 17 Feb 2026); HubSpot `mcp.hubspot.com` (GA 13 Apr 2026 for all accounts, with write access); Shopify per-store endpoint `{shop}.myshopify.com/api/mcp` plus a local Dev MCP; Google Drive `https://drivemcp.googleapis.com/mcp/v1` (Workspace MCP in public developer preview since 1 May 2026) — [awesome-remote-mcp-servers](https://github.com/jaw9c/awesome-remote-mcp-servers/), [mcpyet remote MCP guide](https://mcpyet.com/guides/remote-mcp-servers/)
- As read on 5 Nov 2026: HubSpot remote server uses OAuth 2.1 + PKCE and respects user permissions; Slack's server uses confidential OAuth and is limited to Marketplace and internal apps; Google Analytics MCP is local stdio by default (read-only per guide, three write tools behind `--allow-write`); Google Ads MCP is local or self-hosted, hosted endpoint is an allowlisted pilot; Meta Ads MCP at `mcp.facebook.com/ads` is in open beta; Stripe, Semrush and Ahrefs run hosted servers with OAuth — [Digital Applied](https://www.digitalapplied.com/blog/official-mcp-servers-for-marketing-teams)
- Zapier exposes actions from its app catalogue as MCP tools, including Publer and Canva actions (search-level summary) — [Zapier: Publer](https://zapier.com/apps/publer-k20/integrations)

**Standards**
- MCP Registry: still in preview as of 20 Jul 2026 (v0.1 API freeze began 24 Oct 2025); listing does not imply security vetting — [Digital Thought Disruption](https://digitalthoughtdisruption.com/2026/07/20/mcp-registry-discover-verify-safely-connect-servers/); a weekly diff for 26 Oct-1 Nov 2026 reported 4,588 new servers and 197 deprecations, much of it bulk publishing — [DEV: MCP Registry Diff](https://dev.to/regbase/mcp-registry-diff-1-4588-new-servers-197-deprecated-week-of-oct-26-nov-1-2026-l6f); Zernio is listed there as `com.zernio/zernio` — [Zernio MCP](https://docs.zernio.com/for-you/mcp.mdx)
- Agent Skills: SKILL.md was released as an open standard on 18 Dec 2025, hosted at agentskills.io, which lists more than 40 adopting clients including ChatGPT/Codex and GitHub Copilot (secondary source) — [Atlan explainer](https://atlan.com/know/ai-agent/ai-agent-skills/what-are-agent-skills/); Zernio ships a Claude Code plugin with skills and slash commands — [Zernio MCP](https://docs.zernio.com/for-you/mcp.mdx)
- A2A: the Linux Foundation announced on 9 Apr 2026 that more than 150 organisations support it, with integration in Google, Microsoft and AWS platforms — [Linux Foundation press release](https://www.linuxfoundation.org/press/a2a-protocol-surpasses-150-organizations-lands-in-major-cloud-platforms-and-sees-enterprise-production-use-in-first-year); secondary sources date the v1.0 spec to March-April 2026 — [AIwire](https://www.hpcwire.com/aiwire/2026/04/09/linux-foundation-a2a-protocol-marks-one-year-with-broad-enterprise-and-cloud-adoption/)
- ChatGPT: custom MCP apps are added through Developer mode, enabled by workspace admins; OpenAI's help article "Developer mode and MCP apps in ChatGPT" is the reference; directory publication is a separate submission from testing (search-level summary) — [OpenAI Help Center](https://help.openai.com/ja-jp/articles/12584461-developer-mode-and-mcp-apps-in-chatgpt). Zernio notes its ChatGPT integration covers posts and analytics only, while DMs, comments and ads need Claude or another client — [Zernio MCP](https://docs.zernio.com/for-you/mcp.mdx)

### Inferences
- Janus can gain Canva, Notion, Slack, HubSpot, Drive and Zernio capabilities by loading remote MCP servers per brand without Spark building native integrations, but every one of them is OAuth-based: Janus needs an MCP OAuth client flow (per-user/per-brand token storage) and Spark needs a UI to connect them. This is the single piece of plumbing that unlocks the most integrations.
- GA4 and Google Ads MCP servers are local/stdio, which suits a docker-compose sidecar; alternatively GA4 reports are available through Zernio's API.
- To be usable from ChatGPT and Claude web connectors, Spark's own MCP server needs remote Streamable HTTP plus OAuth 2.1 (API-key-only servers such as Ayrshare's are the exception among competitors); a self-hosted instance must be publicly reachable over HTTPS.
- Publishing Spark's MCP in the official registry is cheap but, given bulk-publishing noise and no vetting, discovery value is limited; shipping a SKILL.md bundle alongside the MCP server (as Zernio does) is the emerging pattern for coding-agent users.
- No social-media tool in this research advertises A2A support; it is a watch item, not a 2026 requirement.

### Gaps
- Vendor MCP URLs and statuses for Canva, Notion, Slack, Shopify and Drive come from third-party directories, not the vendors' own docs; Figma, Airtable, Mailchimp and Klaviyo MCP servers were not researched.
- ChatGPT plan eligibility for custom MCP apps is disputed between sources (all paid plans vs Business/Enterprise/Edu for full write access); the 2026 app-directory submission requirements were not found.
- Whether Hermes-style gateways specifically support SKILL.md was not confirmed; the Gemini CLI adoption claim is secondary.
- Publer's and Hootsuite's MCP endpoints/auth were not covered by the comparison page; Sprout and Later MCP status unknown.
- MCP Registry GA date, and a reported 28 Jul 2026 MCP spec update changing auth/transport rules, are unconfirmed.
- A2A's reported move into the Agentic AI Foundation (Aug 2026) is from a single blog and unverified.
