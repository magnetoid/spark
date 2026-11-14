# Data sources and APIs for social listening, competitor benchmarking, trends, creator discovery and attribution (state as of 13 Nov 2026)

Reading guide: every source is tagged **[official API]**, **[licensed reseller / SaaS]** or **[scraping]**. Prices are as seen on the cited page in Nov 2026 unless a date is given. "Unverified" means the figure comes only from third-party blogs (many of which sell competing APIs), not from the vendor's own page.

## 1. Social listening / mention monitoring APIs: which have self-serve API access and at what price?

### Takeaway
Self-serve listening APIs exist only at the low end: Brand24 (API from the Business plan, $599-699/mo + $99/mo add-on, plus a hosted MCP server) and Awario ($29-399/mo, API gating unclear). Enterprise suites (Brandwatch, Talkwalker, Meltwater, Sprinklr, YouScan) are quote-only annual contracts. The cheap "build it yourself" route is free and legally clean only for Bluesky, Mastodon, Hacker News, GDELT news and (within 100 searches/day) YouTube; X is pay-per-use at $0.005 per post read with no free tier, and Reddit has required pre-approval for every new API client since Nov 2025 with commercial use by contract only.

### Cited Findings

**Listening SaaS with an API [licensed reseller / SaaS]**
- Brand24 plans (monthly / annual-per-month): Individual $249/$199 (3 keywords, 2,000 mentions/mo, 12-hourly refresh, no API); Team $349/$299 (7 keywords, 10,000 mentions); Pro $499/$399 (12 keywords, 40,000 mentions, realtime); Business $699/$599 (25 keywords, 100,000 mentions); Enterprise from $1,499/mo annual-only. API access is **not available** on Individual/Team/Pro, is a **$99/mo add-on on Business**, and is included on Enterprise. — [Brand24 pricing.md](https://brand24.com/pricing.md)
- Brand24 source coverage by plan: Individual covers Facebook, Instagram, X, News, Blogs, Other Socials, Reddit; Team adds LinkedIn, Medium, Quora, YouTube, TikTok; Pro adds Reviews, Twitch, Newsletters; Business adds Podcasts. — [Brand24 pricing.md](https://brand24.com/pricing.md)
- Brand24 runs a hosted MCP server at `https://mcp.brand24.com/mcp` with OAuth; the AI "only sees the projects you authorize"; capabilities described are summaries of events/anomalies, topics, mentions per topic with tone, influencers/news sources and cross-brand sentiment comparison. The page does not name which plans include MCP, nor whether it is read-only. — [Brand24 MCP](https://brand24.com/mcp/)
- Awario plans: Starter $49/mo ($29 annual), 3 topics, 30,000 new mentions/mo; Pro $149/mo ($89 annual), 15 topics, 300,000 mentions; Enterprise $399/mo ($249 annual), 100 topics, 1,000,000 mentions. — [Awario plans](https://awario.com/plans)
- Awario API gating is contradictory: the plans page as fetched showed API access on all three plans — [Awario plans](https://awario.com/plans); contradicted by Awario's own API page, which (per search excerpt) says a personal API key needs "Awario Enterprise or a larger custom solution" — [Awario social listening API](https://awario.com/social-listening-api)
- Mention: reportedly no longer sold as a standalone product from 1 July 2026 (existing customers keep their plan); API and historical data were moved to paid add-ons on the Company plan. — [Mention plans explained](https://support.mention.com/en/articles/13354178-mention-plans-explained); [PricingSaaS diff 2026W23](https://pricingsaas.com/companies/mention/diffs/2026W23) (both via search excerpt, not fetched)
- YouScan: entry about $499/mo billed annually; API is either part of custom "Unlimited" plans or a paid add-on (sources disagree). — [Toolradar YouScan](https://toolradar.com/tools/youscan/pricing); [Syncly](https://syncly.app/blog/social-listening-api-access-what-s-actually-free-before-enterprise)
- Brandwatch, Talkwalker, Meltwater, Sprinklr: no published API pricing; all quote-based annual contracts; Brandwatch API is "entirely enterprise-negotiated, with no self-serve option". — [Toolradar Brandwatch](https://toolradar.com/tools/brandwatch/pricing); [Syncly](https://syncly.app/blog/social-listening-api-access-what-s-actually-free-before-enterprise)
- Meltwater contract benchmarks (third-party analysis of Vendr data, unverified): starter ~$10,000/yr, median ~$25,800/yr, mid-market $40-80k, enterprise $130k+ "where API and MCP access lives". — [Octolens Meltwater pricing](https://octolens.com/blog/meltwater-pricing)
- Sprinklr: third-party estimates of $60k-$200k+/yr for enterprise listening (unverified). — [Toolradar Brandwatch calculator](https://toolradar.com/tools/brandwatch/calculator)
- Data365 (social data API, not a listening product) [scraping-based data vendor]: credit tiers of 500,000 credits/mo (Basic) and 1,000,000 credits/mo (Standard) — [Data365 pricing](https://data365.co/pricing); third-party listing puts Basic at EUR 300/mo for one network and Standard at EUR 850/mo for two networks, 14-day trial — [FitGap](https://us.fitgap.com/products/data365-social-media-api); Data365's own guide cites "around $0.60 per 1,000 records (EUR 300/month)" — [Data365 guide](https://data365.co/guides/twitter-api-limitations-and-pricing). Networks: Instagram, Facebook, X, TikTok, Reddit, Threads.

**X API [official API] — prices as on docs.x.com, fetched 13 Nov 2026**
- Pay-per-use reads (per resource returned): Posts $0.005; Users / followers / following $0.010; Likes $0.001. "Owned reads" of your own data $0.001 per resource. Counts: Recent $0.005, Counts: All $0.010, Trends $0.010 per request. — [X API pricing](https://docs.x.com/x-api/getting-started/pricing)
- Writes: Post create $0.015; **Post create containing a URL $0.200**. — [X API pricing](https://docs.x.com/x-api/getting-started/pricing)
- Pay-per-use is capped at 3 million post reads per monthly billing cycle; above that requires Enterprise (interest form only, no price). No free tier is listed; new payers can earn $20 in credits. — [X API pricing](https://docs.x.com/x-api/getting-started/pricing)
- Timeline per third-party blogs (unverified against X): pay-per-use became default 6 Feb 2026; legacy Basic ($200/mo) subscribers migrated after 1 June 2026; legacy Pro ($5,000/mo) deprecated by a 14 Aug 2026 forum notice with migration after 1 Sept 2026; Enterprise quoted "around $42,000/month" by one blog. — [bundle.social](https://bundle.social/blog/x-api-pricing-2026-costs-limits); [postproxy](https://www.postproxy.dev/blog/x-api-pricing-2026/); [Gigazine](https://gigazine.net/gsc_news/en/20260209-x-api-pay-per-use)

**Reddit Data API [official API]**
- Since 11 Nov 2025 ("Responsible Builder Policy") Reddit requires approval for any new OAuth token; staff said developers, researchers and moderators all "need to request approval before gaining access". Some developers report repeated immediate denials. — [r/redditdev announcement (mirror)](https://r.datuan.dev/r/redditdev/comments/1oug31u/introducing_the_responsible_builder_policy_new/noc31sg)
- Free tier: 100 queries per minute per OAuth client ID averaged over 10 minutes, non-commercial only; commercial use requires a separate written agreement; Data API Terms last revised 20 July 2026 (per third-party summary). — [Data365 Reddit pricing](https://data365.co/blog/reddit-api-pricing); [Techloy](https://www.techloy.com/reddit-api-pricing-in-2026-complete-guide-for-developers-and-businesses/)
- Commercial price: no rate card. The widely repeated $0.24 per 1,000 calls dates from Reddit's June 2023 announcement and is not on a current pricing page; third-party claims of a ~$12,000/yr floor are unconfirmed. — [Data365 Reddit pricing](https://data365.co/blog/reddit-api-pricing)

**Free / open sources [official API]**
- Bluesky: `public.api.bsky.app` AppView endpoints need no authentication; docs describe "generous rate-limits" without numbers. — [Bluesky rate limits docs](https://docs.bsky.app/docs/advanced-guides/rate-limits)
- Bluesky Jetstream: free JSON WebSocket stream of the whole network; no server-side keyword filter (filter client-side); default max subscription rate ~5k events/sec. — [Jetstream announcement, jazco.dev](https://jazco.dev/2024/09/24/jetstream/)
- Mastodon: `GET /api/v1/timelines/tag/:hashtag` per instance; whether unauthenticated access works depends on each server's settings. — [Mastodon timelines API](https://docs-p.joinmastodon.org/methods/timelines/); [Mastodon.py docs](https://mastodonpy.readthedocs.io/en/1.8.1/07_timelines.html)
- YouTube Data API v3: default quota is 10,000 units/day for all other endpoints **plus a separate allocation of 100 `search.list` calls/day**; videos.list, channels.list and commentThreads.list cost 1 unit. — [YouTube quota cost page](https://developers.google.com/youtube/v3/determine_quota_cost). Third-party blogs date the separate search bucket to 1 June 2026 (before: 100 units per search from the shared pool). — [SociaVault](https://sociavault.com/blog/youtube-data-api-quota-2026)
- Hacker News: Algolia HN Search API (`search`, `search_by_date`), no key. — [HN Search API](https://hn.algolia.com/api). Community wrappers cite 10,000 requests/hour per IP and a 1,000-hit cap per query (not officially documented). — [hn-mcp-server docs](https://glama.ai/mcp/servers/@wei/hn-mcp-server/blob/440ec53a158c7e0166f61170ee47d43979719dfa/docs/API.md)
- GDELT DOC 2.0 API (`api.gdeltproject.org/api/v2/doc/doc`): free, no key, 65 languages; third-party docs cite a limit of 1 request per 5 seconds. — [gdelt-doc-api](https://github.com/kepler471/gdelt-doc-api); [GDELT MCP server](https://lobehub.com/mcp/cyanheads-gdelt-mcp-server)

### Inferences
- For a small agency product the only listening SaaS that is both self-serve and API-capable at a known price is Brand24 Business + API (about $698-798/mo) — expensive relative to Spark's scale but it is the one path that legally covers Instagram/Facebook/TikTok/LinkedIn mentions without Spark scraping anything itself. Its MCP server could be attached per customer ("bring your own Brand24") at zero cost to Spark.
- A "free tier" listening feature is feasible from Bluesky (Jetstream or searchPosts), Mastodon hashtag timelines, HN, GDELT and YouTube (100 searches/day per Google project — i.e. roughly 4 keywords polled hourly). That covers news + the open networks, not Instagram/TikTok/Facebook/LinkedIn.
- X listening cost is linear: 10,000 matched posts/month is about $50; 100,000 about $500. A per-brand monthly cap in Spark is needed. Note the $0.20 surcharge on posts containing a URL affects Spark's publishing side if X posts ever go direct rather than through Zernio.
- Reddit is practically closed to a new commercial self-hosted app: each self-hosting agency would need its own approved client, and commercial use needs a contract.

### Gaps
- Reddit's official Data API wiki returned HTTP 403, so limits and commercial terms are from secondary sources only. — [Reddit Data API Wiki](https://support.reddithelp.com/hc/en-us/articles/16160319875092-Reddit-Data-API-Wiki)
- Awario API gating (all plans vs Enterprise only) is unresolved; Brand24 API docs URL, rate limits and whether MCP needs the API add-on were not found.
- X: whether search endpoints carry any surcharge beyond the $0.005 per returned post, and the exact legacy-tier sunset dates, were not confirmed on X's own pages.
- Google Alerts (RSS only, no API) and commercial news APIs (NewsAPI, GNews) were not researched; Bluesky's terms on commercial use of the firehose were not found.
- Talkwalker (Hootsuite), Sprinklr and Meltwater API docs/pricing: nothing public found.

## 2. Public-profile / competitor data: official APIs vs scraping providers, costs and legal risk

### Takeaway
Official APIs make competitor benchmarking feasible for Instagram (Business Discovery: followers, media count, per-post likes/comments/views of any professional account), Facebook Pages (only after App Review for Page Public Content Access plus business verification), YouTube (fully) and X (paid per read). TikTok and LinkedIn offer no commercial route to other accounts' data, so those need scraping vendors at roughly $1-5 per 1,000 records. In the US, logged-out scraping of public data has repeatedly survived ToS claims, but logged-in/fake-account scraping has ended in shutdowns; in the EU the real exposure is GDPR, where regulators hold that "public" does not mean free to reuse.

### Cited Findings

**Official APIs [official API]**
- Instagram Business Discovery: an IG Business/Creator account can read another professional account by username — `followers_count`, `media_count`, and per-media `like_count`, `comments_count`, `view_count`, `media_url`. Requires a Facebook-login token with `instagram_basic`, `instagram_manage_insights`, `pages_read_engagement`. Age-gated accounts are not returned; no stories; read-only. — [Meta Business Discovery reference](https://developers.facebook.com/docs/instagram-platform/instagram-graph-api/reference/ig-user/business_discovery)
- Instagram Hashtag Search: max 30 unique hashtags per IG account per rolling 7 days; `recent_media` and `top_media` count against it; 50 results/page; needs the Instagram Public Content Access feature (App Review). — [Meta Hashtag Search](https://developers.facebook.com/docs/instagram-platform/instagram-api-with-facebook-login/hashtag-search)
- Facebook Page Public Content Access: required to read public content of Pages the app user does not administer; needs App Review, business verification, and "you may also need to sign additional contracts"; docs updated 1 July 2026. — [Meta PPCA](https://developers.facebook.com/docs/features-reference/page-public-content-access)
- Meta Content Library/API is for researchers at not-for-profit/academic institutions, reviewed by CASD — not available to a commercial agency tool. — [Meta Content Library](https://transparency.meta.com/en-gb/researchtools/meta-content-library/)
- TikTok Research API: only academic institutions (US, EEA, UK, Canada, Switzerland), EU not-for-profit research bodies and certain Brazilian organisations; applicants must be "independent of commercial interests". — [TikTok Research API](https://developers.tiktok.com/products/research-api/)
- TikTok Display API returns only the authorising user's own profile and videos; Commercial Content API covers EU ads/commercial content only (vendor guide, not TikTok docs). — [Datashake TikTok coverage 2026](https://www.datashake.com/blog/tiktok-data-coverage-in-2026-what-social-intelligence-teams-need-to-know)
- LinkedIn: company-page data and post analytics for organisations you do not administer are partner-only (vendor guides); in LinkedIn's own UI, free pages can track only one competitor (down from nine) since 15 Oct 2025. — [Phyllo LinkedIn 2026](https://www.getphyllo.com/post/linkedin-api-access-in-2026-partner-program-approval-timeline-alternatives); [Social Samosa](https://www.socialsamosa.com/news-2/linkedin-competitor-analytics-premium-10543786)
- YouTube: any channel's public stats and videos at 1 unit per call within 10,000 units/day. — [YouTube quota cost page](https://developers.google.com/youtube/v3/determine_quota_cost)
- X: any public profile ($0.010 per user) and posts ($0.005 each). — [X API pricing](https://docs.x.com/x-api/getting-started/pricing)

**Scraping providers [scraping]**
- ScrapeCreators: $47 for 25,000 credits (~$1.88 per 1k requests), $497 for 500,000 (~$0.99 per 1k), 100 free credits, credits do not expire, mostly 1 credit per request; `x-api-key` header, no OAuth; no account-level rate cap (advises under 500 concurrent); covers TikTok, Instagram, YouTube, Facebook, X, LinkedIn, Reddit, Pinterest, Threads, Bluesky, Twitch, Spotify plus ad libraries; hosted MCP at `https://api.scrapecreators.com/mcp`. — [ScrapeCreators](https://scrapecreators.com/)
- EnsembleData: free 50 units/day; $100/mo for 1,500 units/day; $200 for 5,000; $400 for 11,000; $800 for 25,000; $1,400 for 50,000. Typical costs: user info 1-4 units, 10 posts 1 unit, keyword search 1 unit per ~20 posts. Covers TikTok, Instagram, YouTube, Threads, Reddit, Twitch, X, Snapchat. — [EnsembleData pricing](https://ensembledata.com/pricing)
- Apify: platform plans Free ($5 monthly credit), Starter (reported cut from $29 to $19/mo on 11 Sept 2026; other trackers still show $29-39), Scale $199, Business $999. — [UsagePricing](https://www.usagepricing.com/blueprint/activity/apify-2026-09-11-starter-plan-price-cut); [CostBench](https://costbench.com/software/web-scraping/apify/). Apify's Instagram Scraper is reported at $2.70 per 1,000 results on Free, $2.30 Starter, $1.90 Scale, $1.50 Business (as of 9 Sept 2026); community actors range ~$0.30-$5.00 per 1,000. — [use-apify guide](https://use-apify.com/docs/best-apify-actors/best-instagram-scrapers)
- Apify hosted MCP server: `https://mcp.apify.com`, OAuth or Bearer API token; tools to search, inspect and run Actors; usage billed to the Apify plan. — [Apify MCP docs](https://docs.apify.com/platform/integrations/mcp)
- Bright Data Web Scraper API: commonly cited $1.50 per 1,000 records pay-as-you-go, promos from $0.75; ~5,000 records/month free; datasets from $250 per 100k records (third-party figures). — [Firecrawl on Bright Data pricing](https://www.firecrawl.dev/blog/bright-data-pricing); [use-apify Bright Data guide](https://use-apify.com/blog/bright-data-pricing-guide-2026). Bright Data MCP: 5,000 free requests/month in "Rapid" mode; social tools sit in the paid Pro mode. — [mcpservers.org Bright Data](https://mcpservers.org/servers/brightdata/brightdata-mcp)
- SociaVault: 50 free credits; $29 for 6,000 credits (~$4.83 per 1k), $79 for 20,000, $199 for 75,000; credits never expire. — [SociaVault pricing](https://sociavault.com/pricing); [SociaVault blog](https://sociavault.com/blog/sociavault-vs-phantombuster-comparison)
- PhantomBuster: about $69 / $159 / $439 per month (Start/Grow/Scale), metered by execution time; it automates via the user's own logged-in session. — [PhantomBuster pricing explained](https://phantombuster.com/blog/ai-automation/phantombuster-pricing-explained)

**US case law and platform enforcement**
- Meta v. Bright Data (N.D. Cal., 23 Jan 2024): summary judgment for Bright Data — logged-off scraping of public Facebook/Instagram data did not breach Meta's terms; the ruling is limited to Meta's ToS and does not address scraping behind a login. — [Farella Braun + Martel](https://www.fbm.com/data-analytics/publications/major-decision-affects-law-of-scraping-and-online-data-collection-meta-platforms-v-bright-data/); Meta then dropped the case — [TechCrunch, 26 Feb 2024](https://techcrunch.com/2024/02/26/meta-drops-lawsuit-against-web-scraping-firm-bright-data-that-sold-millions-of-instagram-records)
- X Corp. v. Bright Data: N.D. Cal. dismissed X's ToS-based claims as preempted by the Copyright Act. — [ZwillGen](https://www.zwillgen.com/alternative-data/how-artificial-intelligence-shaping-web-scraping-litigation/)
- hiQ v. LinkedIn ended Dec 2022 with LinkedIn winning summary judgment on breach of contract, a $500,000 consent judgment and a permanent injunction; no binding CFAA precedent resulted. — [Proskauer](https://newmedialaw.proskauer.com/2022/12/08/hiq-and-linkedin-reach-proposed-settlement-in-landmark-scraping-case/); [ZwillGen](https://www.zwillgen.com/alternative-data/hiq-v-linkedin-wrapped-up-web-scraping-lessons-learned/)
- LinkedIn v. Proxycurl (2025): Proxycurl shut down and must permanently delete LinkedIn data; the complaint alleged fake accounts simulating logged-in use. — [LinkedIn newsroom](https://news.linkedin.com/2025/LinkedInWinsLegalBattleToProtectMemberData)
- LinkedIn removed the company pages of data vendors such as Apollo.io and Amplemarket. — [LeadGenius](https://www.leadgenius.com/resources/linkedins-b2b-data-crackdown-what-changed-by-2026)
- Reddit v. SerpApi, Oxylabs, AWMProxy and Perplexity (S.D.N.Y., filed 22 Oct 2025) uses DMCA anti-circumvention claims; pending. — [Proxyway](https://proxyway.com/news/reddit-sues-perplexity-oxylabs-two-more-web-data-providers); [ZwillGen](https://www.zwillgen.com/alternative-data/how-artificial-intelligence-shaping-web-scraping-litigation/)
- Google v. SerpApi (N.D. Cal., filed 19 Dec 2025, DMCA s.1201) — [IPWatchdog](https://ipwatchdog.com/2025/12/26/google-sues-serpapi-parasitic-scraping-circumvention-protection-measures/); SerpApi says the court has dismissed Google's complaint twice (defendant's own account) — [SerpApi blog](https://serpapi.com/blog/court-dismisses-googles-amended-complaint-against-serpapi/)
- Meta sued Voyager Labs over fake-account scraping and disabled 60,000+ accounts — [GovInfoSecurity](https://www.govinfosecurity.com/meta-sues-scraping-for-hire-provider-closes-60000-accounts-a-20932); BrandTotal/Unimania settled with a permanent scraping ban in 2022 — [TechCrunch](https://techcrunch.com/2022/10/03/meta-settles-lawsuit-for-significant-sum-against-businesses-scraping-facebook-and-instagram-data/amp)

**EU / GDPR**
- CNIL fined KASPR EUR 240,000 (5 Dec 2024) for scraping LinkedIn contact details; public accessibility alone does not justify reuse; also transparency, retention and access-right breaches. — [CNIL](https://www.cnil.fr/en/data-scraping-kaspr-fined-eu240000)
- Dutch AP guidance (May 2024): scraping almost always involves personal data, and purely commercial interests cannot ground legitimate interest (a position reported as under review). — [Pinsent Masons](https://www.pinsentmasons.com/de-de/out-law/nachrichten/dutch-web-scraping-guidance-warn-businesses-gdpr-breach-risk)
- Dutch AP fined Clearview AI EUR 30.5 million and warned that using Clearview's services is also illegal. — [EDPB](https://www.edpb.europa.eu/news/national-news/2024/dutch-supervisory-authority-imposes-fine-clearview-because-illegal-data_en)
- EDPB Guidelines 03/2026 on web scraping in the context of generative AI: adopted 7 July 2026 as a consultation draft (comments to 30 Oct 2026); legitimate interest (Art. 6(1)(f)) is the reference basis with the three-step test; robots.txt, CAPTCHAs and login walls count as signals of data subjects' reasonable expectations. — [EDPB guidelines PDF](https://www.edpb.europa.eu/system/files/2026-07/edpb_guidelines_2020603_webscraping_v1_en_0.pdf); [Reed Smith](https://www.reedsmith.com/our-insights/blogs/technology-law-dispatch/102nbqu/edpb-web-scraping-guidelines-for-ai-making-the-impossible-possible/)

### Inferences
- Instagram and Facebook competitor benchmarking no longer needs scraping: Business Discovery works with the token of any connected IG professional account. The catch for Spark is architectural — Spark connects accounts through Zernio, so it either needs Zernio to expose Business Discovery or its own Meta app (App Review, business verification) per self-hosted install.
- For TikTok and LinkedIn there is no official commercial route, so the choice is a scraping vendor or leaving them out. Cost is trivial (benchmarking 10 competitors daily on one network is ~300-600 requests/month, i.e. well under $5 on ScrapeCreators or within EnsembleData's free 50 units/day); the cost is legal/operational risk, not money.
- Risk ranking by enforcement history: LinkedIn (highest — Proxycurl, hiQ, KASPR, page removals) > Meta when logged-in or fake accounts are involved > logged-out public data of business/brand accounts (lowest). Benchmarking brand/company accounts' aggregate counts involves little or no personal data; scraping individual creators' profiles, comments or follower lists is personal-data processing requiring a legitimate-interest assessment, Art. 14 transparency and retention limits.
- Using a vendor does not move GDPR liability: the agency remains controller for what it requests and stores (the Dutch AP's Clearview warning to customers illustrates the regulator view). Offering scraping as an opt-in, bring-your-own-key connector keeps the decision and the contract with the agency rather than with Spark's author.

### Gaps
- Business Discovery rate limits: Meta's page gives none; vendor guides conflict (about 200 calls/hour per account vs the "4800 x impressions per 24h" formula).
- LinkedIn's current Community Management API rules were not confirmed on learn.microsoft.com; TikTok Display/Commercial Content API facts come from a vendor guide.
- No EU court ruling specifically on scraping public brand-account metrics was found; the EDPB 03/2026 guidelines are a draft and target AI training, not benchmarking.
- Bright Data and Apify prices are from third-party trackers that disagree; RapidAPI marketplace scrapers were not researched.
- None of the scraping vendors' DPAs, EU hosting or sub-processor terms were checked.

## 3. Trend detection: what is programmatically accessible?

### Takeaway
There is no good official trends API for a small commercial product in late 2026: Google Trends API is still an application-gated alpha, Pinterest's Trends API is aimed at agencies/enterprise partners, TikTok Creative Center has no API, and Spotify has tightened access. What works today is YouTube's `chart=mostPopular`, X Trends at $0.01 per request, Bluesky/Mastodon/HN/GDELT (free), Exploding Topics (from $1,000/month on top of a $249 plan, commercial use by quote), and scrapers of Creative Center and Google Trends.

### Cited Findings
- Google Trends API [official API]: alpha, "not yet open" to everyone; application form for testers; rolling five years of data, daily/weekly/monthly/yearly aggregation, region and sub-region comparison, consistently scaled values (not 0-100); no published endpoints, quotas or pricing. — [Google Trends API](https://developers.google.com/search/apis/trends). Announced 24 July 2025; third-party trackers still report invite-only status in mid/late 2026. — [Search Engine Roundtable](https://www.seroundtable.com/google-trends-api-applications-approvals-39978.html); [Konabayev landscape 2026](https://konabayev.com/blog/google-trends-api-landscape-2026/)
- Pinterest Trends API [official API]: `GET /v5/trends/keywords/{region}/top/{trend_type}`, filters by interests, genders, ages; max 50 results per request; today's data only (no history); positioned for "agencies, Enterprise clients, and partner platforms". — [Pinterest Trends docs](https://developers.pinterest.com/docs/analytics-and-reports/trends/). A community thread reports the endpoint is accessible only to selected developers (undated). — [Pinterest community](https://community.pinterest.biz/t/list-trending-keywords-access/2617)
- TikTok Creative Center [no API]: trends (hashtags, songs, creators, videos) are a web-only view; no official public API; third-party Apify actors scrape it. — [TikTok Creative Center help](https://ads.tiktok.com/help/article/creative-center); [Apify TikTok Trends Scraper](https://apify.com/automation-lab/tiktok-trends-scraper) [scraping]
- X Trends [official API]: billed at $0.010 per request. — [X API pricing](https://docs.x.com/x-api/getting-started/pricing)
- YouTube [official API]: `videos.list` costs 1 unit (the page lists no separate cost for `chart=mostPopular`). — [YouTube quota cost page](https://developers.google.com/youtube/v3/determine_quota_cost)
- Exploding Topics API [licensed data]: add-on to Pro Business ($249/mo); API packages $1,000/mo for 1,000 requests, $2,000 for 5,000, $4,000 for 25,000; 60 requests/min; 1.1M+ trends with growth, forecasts, seasonality; **commercial use (building it into your own product) requires custom pricing**; no custom keyword or geo lookups. — [Exploding Topics API](https://explodingtopics.com/feature/et-api)
- Glimpse: listed at $49/mo as a browser overlay with no API (competitor-run comparison site, unverified). — [TrendsMCP comparison](https://trendsmcp.ai/trends-api-pricing-comparison)
- Spotify Web API [official API]: Feb/Mar 2026 changes restricted development-mode apps; extended quota is organisations-only, with 2025 criteria including a registered business and 250,000 monthly active users. — [Spotify Feb 2026 migration guide](https://developer.spotify.com/documentation/web-api/tutorials/february-2026-migration-guide); [Spotify extended access criteria](https://developer.spotify.com/blog/2025-04-15-updating-the-criteria-for-web-api-extended-access)
- Sound/music data via scraping: EnsembleData exposes TikTok "Music Information" (2 units) and "Music Posts" (1 unit per 10 posts). — [EnsembleData pricing](https://ensembledata.com/pricing) [scraping]

### Inferences
- A realistic v1 "trends" feature for Spark is a composite of free, official signals (YouTube mostPopular per region/category, Bluesky and Mastodon trending tags, GDELT news volume, HN) plus the brand's own Zernio analytics, with TikTok Creative Center and Google Trends only via an optional scraping connector.
- Applying for the Google Trends alpha costs nothing and is the only route to legally clean search-trend data; it cannot be a dependency for a self-hosted product because access is per approved developer.
- Exploding Topics is priced out for this use case (minimum ~$1,249/mo and resale needs a custom deal).

### Gaps
- Pinterest: the supported-region list, required scopes and how access is granted were not on the page fetched.
- No official TikTok source on a trending-sounds API was found; Reddit as a trend source is constrained by the access rules in section 1.
- YouTube trending per-category behaviour in 2026 and Mastodon `/api/v1/trends` availability were not verified.

## 4. Influencer / creator discovery and vetting APIs

### Takeaway
Creator-discovery APIs are priced for platforms, not small agencies: Modash starts at $16,200/yr (Discovery) or $10,000/yr (Raw), annual only. The self-serve exception is influencers.club (from $208/mo, monthly billing, per-result credits); HypeAuditor, Phyllo and CreatorDB publish no firm API prices.

### Cited Findings
- Modash Discovery API: from $16,200/yr; search 0.01 credit per result, AI search 0.025, influencer report 1 credit, audience report 1 credit; 380M+ profiles across Instagram, YouTube, TikTok; annual contracts only, bank transfer only; testing credits via a sales call. — [Modash API pricing](https://www.modash.io/influencer-marketing-api/pricing) [licensed data vendor; data is collected from public profiles]
- Modash Raw API: from $10,000/yr, billed per request (about 40,000 requests/month at entry per search excerpt), live on-demand data. — [Modash API pricing](https://www.modash.io/influencer-marketing-api/pricing); [Modash Raw API](https://www.modash.io/influencer-marketing-api/raw)
- influencers.club API: from $208/mo (Pro), credits "as low as $0.23", 10 free credits without a card, self-serve, monthly billing, charged per successful result; discovery 0.01 credit per profile, full enrichment 1 credit, audience analytics 0.8, raw profile 0.03, campaign monitoring 0.3 credit per creator per day; discovery on Instagram, TikTok, YouTube, X, Twitch, OnlyFans. — [influencers.club comparison page](https://influencers.club/compare/modash-api-vs-influencers-club-api) (vendor's own, promotional)
- HypeAuditor API: estimated ~$30k-36k/yr by a competitor's blog; other third parties cite $299-399/mo base plans with API as a custom add-on (all unverified). — [influencers.club API roundup](https://influencers.club/blog/influencer-marketing-apis/)
- CreatorDB: third-party listings put API in a $79/mo Pro plan and $249 Premium, while a competitor notes CreatorDB documents per-call credit costs but no plan prices and that API v3 is in closed beta. — [CreatorDB pricing](https://www.creatordb.app/pricing); [influencers.club vs CreatorDB](https://influencers.club/compare/creatordb-api-vs-influencers-club-api/)
- Phyllo: no public price list; reported entry around $199/mo scaling with call volume (third-party). — [Influencer Hero on Phyllo](https://www.influencer-hero.com/it/blogs/phyllo-pricing-and-review); [G2 Phyllo pricing](https://g2.com/products/phyllo/pricing)

### Inferences
- Creator discovery is not economical as a built-in Spark feature; the workable pattern is an optional connector where the agency supplies its own influencers.club (or Modash) key, with Spark only storing shortlisted creators.
- Lightweight vetting of a known handle can be done without these vendors: Instagram Business Discovery (followers, recent post engagement) and YouTube Data API are official and free; TikTok needs a scraper call.
- These databases are large-scale profiles of natural persons (including audience demographics); under GDPR the agency is a controller for creators it stores, so Art. 14 notice and retention limits apply even when the vendor claims compliance.

### Gaps
- Upfluence API availability and price were not researched; HypeAuditor's, Phyllo's and CreatorDB's own pricing pages were not successfully read.
- No vendor's GDPR position (legal basis, EU hosting, DPA) was verified.

## 5. Attribution of posts to traffic and revenue

### Takeaway
Attribution is the easiest of the five areas to do with official, free, GDPR-manageable APIs: Spark's short links already carry UTMs, and GA4 Data API, Plausible, Matomo and Umami all expose sessions/conversions/revenue by `utm_campaign`/`utm_content`; Shopify (GraphQL `customerJourneySummary`) and WooCommerce (order-attribution meta) store UTMs on each order. Commercial schedulers do essentially this — auto-UTM plus a GA4 or shop connection — rather than anything proprietary.

### Cited Findings
- GA4 Data API quotas (standard property): 200,000 tokens/day, 40,000/hour, 14,000 per project per property per hour, 10 concurrent requests (360: 10x). — [GA4 Data API quotas](https://developers.google.com/analytics/devguides/reporting/data/v1/quotas) [official API, free, OAuth or service account]
- Plausible Stats API v2: `POST https://plausible.io/api/v2/query`, Bearer key, 600 requests/hour; dimensions `visit:utm_source|medium|campaign|content|term`; metrics include `conversion_rate`, `total_revenue`, `average_revenue` (need revenue goals); on Plausible Cloud the "Stats API is a Business plan feature". — [Plausible Stats API](https://plausible.io/docs/stats-api) [official API]
- Matomo: Cloud rate-limits the Reporting API by IP (HTTP 429); the Tracking API is not rate-limited. — [Matomo Cloud API limits](https://matomo.org/faq/troubleshooting/matomo-cloud-api-usage-limits/) [official API]
- Umami (self-hosted): API keys as Bearer token or `POST /api/auth/login`; base `http://<instance>/api`. — [Umami API authentication](https://docs.umami.is/docs/api/authentication) [official API]
- Shopify Admin GraphQL `CustomerJourneySummary`: first and last visit before an order, 30-day window, each visit carrying `utmParameters` (source, medium, campaign, term, content). — [Shopify CustomerJourneySummary](https://shopify.dev/docs/api/admin-graphql/latest/objects/customerjourneysummary). Developers report attribution can take up to 48 hours to populate, orders cannot be filtered by UTM, and click IDs/custom parameters are not exposed. — [Shopify dev community](https://community.shopify.dev/t/how-to-get-attribution-data-for-orders/26017) [official API]
- WooCommerce Order Attribution stores `_wc_order_attribution_utm_source`, `_utm_medium`, `_utm_campaign`, `_source_type`, `_referrer` as order meta. — [WooCommerce order attribution docs](https://woocommerce.com/document/order-attribution-tracking/); [Metorik](https://help.metorik.com/woocommerce-source-tracking-p8143) [official feature; REST exposure unverified]
- Meta Conversions API: server-to-server events authenticated with an access token generated in Events Manager; needs `event_id` deduplication with the Pixel. — [Meta CAPI implementation guide](https://developers.facebook.com/docs/marketing-api/conversions-api/guides/end-to-end-implementation). Server-side sending does not remove consent requirements: if the Pixel is blocked for a user, CAPI should not fire. — [Didomi](https://didomi.io/blog/meta-conversions-api-capi-tracking)
- How competitors do it: Dash Social applies default UTMs to scheduled posts and joins a connected Google Analytics property to show traffic and revenue per campaign. — [Dash Social](https://www.dashsocial.com/blog/google-analytics-for-social-media). Metricool uses its own JavaScript tracking snippet/pixel on the site and markets a Shopify connection showing how posts affect sales. — [Metricool integrations](https://metricool.com/metricool-integrations/)
- GA4 and Shopify revenue differ by definition: GA4 reports the purchase event's value, Shopify gross sales including tax and shipping by default; GA4 cannot give the order number behind a campaign purchase (third-party guidance). — [SocialPilot attribution models](https://www.socialpilot.co/blog/social-media-attribution-models)
- Google's official Analytics MCP server (`analytics-mcp`, Apache-2.0, read-only by default, uses Admin + Data APIs with Application Default Credentials; labelled experimental). — [googleanalytics/google-analytics-mcp on Glama](https://glama.ai/mcp/servers/@googleanalytics/google-analytics-mcp/schema); [Fast.io guide](https://fast.io/resources/mcp-server-for-google-analytics/)

### Inferences
- The join key already exists: if Spark stamps each short link with `utm_source=<network>`, `utm_medium=social`, `utm_campaign=<campaign>` and `utm_content=<post id>`, then a per-post row is one GA4 `runReport` (dimension `sessionManualAdContent`/campaign, metrics sessions, key events, purchase revenue) or one Plausible query, and one Shopify/Woo order query grouped by last-visit `utm_content`. No tracking script from Spark is required.
- For an EU agency, Plausible/Matomo/Umami self-hosted are the low-friction options (first-party, no US transfer, cookieless modes); GA4 needs consent, so GA4-reported social revenue undercounts by the non-consent share — Spark's own click counts stay the unbiased top-of-funnel number.
- Order-level attribution from Shopify/Woo is last-click (or first/last visit) and misses dark social and in-app-browser sessions; it should be presented as "attributed orders", not total social impact. Meta CAPI is an ads-optimisation channel and out of scope for organic post attribution.
- Server-side redirect logging in Spark's shortener processes IP/user-agent: aggregate counts with truncated IPs keep it within a simple legitimate-interest footing.

### Gaps
- Later's Linkin.bio/Shopify attribution and Metricool's per-post revenue mechanics could not be confirmed from vendor documentation.
- Whether Plausible Community Edition exposes the Stats API (the docs only gate the Cloud Business plan), Matomo's `token_auth` details on developer.matomo.org, and whether Woo's `_wc_order_attribution_*` meta appears in the core REST order response were not verified.
- Shopify API scopes/plan requirements for `customerJourneySummary` were not checked.

## 6. Review and local data

### Takeaway
Reviews are available officially but only for businesses you manage: Google Business Profile API needs a manually approved project (quota is zero until then) and Trustpilot's API is a paid add-on to Premium/Enterprise business plans. Third-party aggregators (DataForSEO and similar) sell any business's reviews via scraping.

### Cited Findings
- Google Business Profile API [official API]: access is granted per Google Cloud project after an application showing legitimate business need; the Reviews API lets merchants read and reply to reviews for locations they manage. — [Google Business Profile API FAQ](https://developers.google.com/my-business/content/faq)
- Unapproved projects have 0 requests/minute (429 errors); one 2026 guide says approved projects get 300 QPM; review times reported from ~2 days to 60+ days. — [Google developer forum thread](https://discuss.google.dev/t/business-profile-api-allowlisting-quota-issue-for-automated-review-replies-across-31-gbp-locations/366695); [Slashpost GBP API 2026](https://slashpost.ai/blogs/google-business-profile/google-business-profile-api-documentation-2026)
- Trustpilot [official API]: Trustpilot for Business users sign up for an "API module add-on"; `GET /v1/business-units/{businessUnitId}/reviews` with API-key auth. — [Trustpilot API module overview](https://developers.trustpilot.com/api-module-overview/). The add-on is reported as available on Premium and Enterprise only (Oct 2026); plan prices conflict across sources (~$599-629/mo Premium). — [DataImpulse](https://dataimpulse.com/blog/trustpilot-api/)
- DataForSEO Business Data API sells Trustpilot (and Google) reviews for any business on pay-as-you-go pricing. — [DataForSEO Trustpilot reviews pricing](https://dataforseo.com/pricing/business-data/business-data-api-trustpilot-reviews-pricing) [scraping]

### Inferences
- Zernio already supplies own-account reviews, so the only gap is competitor reviews; that is scraping-only, and review text with reviewer names is personal data — storing aggregate rating and count per competitor is the low-risk form.

### Gaps
- DataForSEO unit prices, Outscraper, Datashake and Google Places API review limits were not researched; Trustpilot plan prices were not confirmed on its own pricing page.

## 7. Which sources have an MCP server or a simple REST API suited to read-only agent tools?

### Takeaway
Vendor-run MCP servers exist for Brand24, Apify, ScrapeCreators, Bright Data, Meltwater (Claude directory connector) and Google Analytics (official, local, read-only by default). Everything else worth using is a plain key-or-no-auth JSON API that wraps into a read-only tool in a few lines.

### Cited Findings
- Brand24: `https://mcp.brand24.com/mcp`, OAuth, scoped to authorised projects. — [Brand24 MCP](https://brand24.com/mcp/)
- Apify: `https://mcp.apify.com`, OAuth or Bearer token; exposes actor search/run plus web search/fetch; can run any store actor, so it is not inherently read-only or cost-bounded. — [Apify MCP docs](https://docs.apify.com/platform/integrations/mcp)
- ScrapeCreators: `https://api.scrapecreators.com/mcp`, plus REST with a single `x-api-key` header. — [ScrapeCreators](https://scrapecreators.com/)
- Bright Data MCP: 5,000 free requests/month in Rapid mode; social scrapers in paid Pro mode. — [mcpservers.org Bright Data](https://mcpservers.org/servers/brightdata/brightdata-mcp)
- Meltwater has a "Made by Meltwater" connector in Claude's directory; Meltwater and Brand24 are named as the listening tools with MCP servers in a Nov 2026 roundup. — [eSEOspace roundup](https://eseospace.com/blog/best-mcp-servers-for-social-media/)
- Google Analytics: official `analytics-mcp`, runs locally, read-only by default, experimental. — [Fast.io guide](https://fast.io/resources/mcp-server-for-google-analytics/)
- Community (unofficial) MCP servers exist for Umami, Matomo, Hacker News, GDELT and Reddit. — [Umami MCP](https://glama.ai/mcp/servers/lukasschmit/umami-mcp); [Matomo MCP](https://glama.ai/mcp/servers/cc8k3knksy); [GDELT MCP](https://lobehub.com/mcp/cyanheads-gdelt-mcp-server); [Reddit MCP on Apify](https://apify.com/memo23/reddit-mcp-server)
- Simple REST, no OAuth dance: Plausible (Bearer key, one POST endpoint) — [Plausible Stats API](https://plausible.io/docs/stats-api); Umami (Bearer key) — [Umami API](https://docs.umami.is/docs/api/authentication); HN Algolia (no key) — [HN Search API](https://hn.algolia.com/api); Bluesky public AppView (no auth) — [Bluesky rate limits docs](https://docs.bsky.app/docs/advanced-guides/rate-limits); EnsembleData (token, unit-metered) — [EnsembleData pricing](https://ensembledata.com/pricing); X (Bearer token, per-resource billing) — [X API pricing](https://docs.x.com/x-api/getting-started/pricing)

### Inferences
- Since Spark already ships its own MCP server and an agent service, the cheapest integration is to add native read-only tools over the simple REST sources (Plausible/Umami/GA4, Bluesky, HN, GDELT, YouTube, Business Discovery) and let agencies attach vendor MCP servers (Brand24, ScrapeCreators) themselves.
- Metered sources (X, ScrapeCreators, EnsembleData, Apify) need per-brand budgets and call caps enforced in Spark's tool layer, because an agent loop can spend money; Apify's MCP in particular should be restricted to an allow-list of actors.

### Gaps
- No vendor MCP was found for Shopify, WooCommerce, Plausible, Modash or influencers.club in this pass (a combined search returned only Google Analytics results); Shopify and Plausible may have official ones that were not surfaced.
- Read-only guarantees are stated only for Google's server; Brand24's page does not say.
