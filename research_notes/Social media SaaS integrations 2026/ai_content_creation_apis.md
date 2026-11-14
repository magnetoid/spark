# AI content-creation tools and APIs for social media that a third-party app can integrate (state as of 13 November 2026)

Reading notes for the report writer:
- "Primary" = the vendor's own docs or pricing page, fetched in November 2026. "Secondary" = third-party tracker or blog; several are written by competitors and are flagged as such.
- Prices are USD list prices, pay-as-you-go, excluding tax, unless stated.
- A service is called "integrable" only where vendor API documentation was actually found.
- Spark-specific facts (from reading the repository on 2026-11-13) are marked "Spark repo".

## 1. Long video to short clips: which services expose an API, what they cost, what they return

### Takeaway
Five clipping vendors have real, documented REST APIs in November 2026: Klap, OpusClip, Vizard, Submagic and Reap. Klap is the only one with published pure pay-per-use API prices; the others bill the API against a subscription's minutes or credits. No public clipping API was found for Munch or Riverside, and Descript's API is reported as still beta.

### Cited Findings

**Klap (integrable, pay-per-use)**
- REST API v2, base URL `https://api.klap.app/v2`, auth `Authorization: Bearer <key>`, JSON; resources are Tasks, Projects and Exports. — [Klap docs (primary)](https://docs.klap.app/)
- Usage-based pricing: $0.44 per input video, $0.32 per generated short, $0.48 per export. — [Klap docs (primary)](https://docs.klap.app/)
- A separate "Sign in with Klap" API uses OAuth 2.1 with PKCE and bills the end user's own Klap subscription. — [Klap docs (primary)](https://docs.klap.app/)
- Accepts long videos (AI picks moments) or already-short videos (captions and reframing only); 99+ languages, auto-detected or set by a `language` parameter. — [Klap docs (primary)](https://docs.klap.app/)
- Endpoints `POST /tasks/video-to-shorts`, `GET /tasks/{task_id}`, `GET /projects/{folder_id}`, plus exports; inputs include YouTube, Vimeo, Twitch, Loom, Dropbox, Google Drive, S3/GCP and public file URLs; output is 1080x1920 MP4 with animated captions, speaker reframing, a virality score and transcripts; webhooks are not documented (poll tasks); credit packs from $10; $5 API credit when a card is added. — [itechguides, 4 Nov 2026 (secondary; article is labelled "Sponsored by Klap" and did not run paid jobs)](https://www.itechguides.com/best-ai-video-clipping-api-klap-pricing-and-code/)
- Worked example: one input video with 10 shorts, all 10 exported, costs $8.44; exporting three costs $5.08. — [itechguides (secondary, sponsored)](https://www.itechguides.com/best-ai-video-clipping-api-klap-pricing-and-code/)

**OpusClip (integrable, plan-gated)**
- API access is on Pro (Beta), Max and Business plans. Pro Beta and Max include 15 hours of API video per month and up to 4 parallel projects; Business is by contract with up to 50 parallel projects. — [OpusClip API reference overview (primary)](https://help.opus.pro/api-reference/overview)
- 1 credit = 1 minute of video processing; API projects have a 10-credit minimum. — [OpusClip API reference overview (primary)](https://help.opus.pro/api-reference/overview)
- Rate limit 30 requests per minute per key; max input 10 hours and 30 GB; 20+ languages; projects expire after 30 days by default. — [OpusClip API reference overview (primary)](https://help.opus.pro/api-reference/overview)
- Endpoint pages: Create a Project, Query Clips, Brand Templates, Share a Project, Social Posting (generate copy, publish or schedule), Webhooks, Edit Clips (trim, extend, fix caption typos). — [OpusClip API reference overview (primary)](https://help.opus.pro/api-reference/overview)
- `POST https://api.opus.pro/api/clip-projects` with Bearer auth; options include `videoUrl`, `curationPref` (range, `clipDurations`, `topicKeywords`, `genre`), `importPref.sourceLang`, `brandTemplateId`; six official SDKs (Node, Python, Go, PHP, Ruby, Java), a public OpenAPI spec and an MCP server. — [OpusClip API page (primary)](https://www.opus.pro/api)
- Consumer plan prices are reported as $15 (Starter) and $29 (Pro) per month with a custom Business tier. — [Castmagic (secondary)](https://www.castmagic.io/blog/opus-clip-pricing)
- Effective cost reported as about $2.90 per hour of uploaded video on OpusClip Pro billed yearly. — [revid.ai, Nov 2026 (secondary; competitor)](https://www.revid.ai/opus-clip-alternative)

**Vizard (integrable, plan-gated)**
- API access is included in the Creator and Business plans with no separate API subscription; API submissions consume the same video upload minutes as the web app; above 10,000 minutes per month requires a custom arrangement. — [Vizard docs: Pricing (primary)](https://docs.vizard.ai/docs/pricing)
- Input limits: 600 minutes, 10 GB, up to 4K; clips keep source quality. — [Vizard docs: Pricing (primary)](https://docs.vizard.ai/docs/pricing)
- REST/JSON API that detects engaging moments, returns transcripts and customisable subtitles, and lets the caller set clip durations, aspect ratios and branding templates. — [Vizard docs: Introduction (primary)](https://docs.vizard.ai/docs/introduction)
- The docs index lists clipping endpoints (submit, retrieve clips, delete project) and publishing endpoints (retrieve social accounts, publish to one or several accounts, retrieve publishing results, generate AI social caption), plus Rate Limit and Supported Languages pages. — [Vizard docs index (primary)](https://docs.vizard.ai/llms.txt)
- Effective cost reported as about $1.45 per hour of uploaded video billed yearly. — [revid.ai, Nov 2026 (secondary; competitor)](https://www.revid.ai/opus-clip-alternative)

**Submagic (integrable, captions-first)**
- Auth is an API key in the `x-api-key` header; `POST https://api.submagic.co/v1/projects` creates a project from `videoUrl` with `title`, `language` and `templateName` (example "Hormozi 2"). — [Submagic docs (primary)](https://docs.submagic.co/introduction)
- Features listed: AI captions in 100+ languages, Magic Clips (shorts from YouTube videos), templates with animated text and emojis, webhooks, and an MCP server. — [Submagic docs (primary)](https://docs.submagic.co/introduction)
- Rate limits per hour: 1000 lightweight requests, 500 project retrievals, 500 project creations/uploads, 50 exports. — [Submagic docs (primary)](https://docs.submagic.co/introduction)
- The API docs show no prices. — [itechguides (secondary, sponsored by Klap)](https://www.itechguides.com/best-ai-video-clipping-api-klap-pricing-and-code/)

**Reap (integrable, broadest endpoint set)**
- Base URL `https://public.reap.video/api/v1/automation/`, Bearer auth, keys from Settings → API Keys; MCP server at `https://mcp.reap.video/mcp`. — [Reap API introduction (primary)](https://docs.reap.video/api-reference/1_introduction.md)
- Endpoints: `get-upload-url`, `create-clips`, `create-captions`, `create-reframe`, `create-dubbing`, `create-transcription`, `create-editor`, `get-project-status`, `get-project-clips`, `publish-clip`, `schedule-clips`, `get-all-presets`. — [Reap API introduction (primary)](https://docs.reap.video/api-reference/1_introduction.md)
- Rate limits per minute per key: 60 reads, 30 writes, 10 project creations; concurrency 3 projects (Creator), 10 (Studio), custom (Enterprise). — [Reap API introduction (primary)](https://docs.reap.video/api-reference/1_introduction.md)
- Inputs: MP4 or MOV, 2 minutes to 3 hours, up to 5 GB. — [Reap API introduction (primary)](https://docs.reap.video/api-reference/1_introduction.md)
- Each clip returns a presigned `clipUrl`, `title`, `caption`, virality score and framing metadata; `exportResolution` and `exportOrientation` are settable; reframing targets 9:16, 1:1 and 4:5; transcripts are word-level; dubbing covers 80+ languages; a natural-language `prompt` on `create-clips` is in preview. — [Reap API introduction (primary)](https://docs.reap.video/api-reference/1_introduction.md)
- Webhooks POST on terminal state, must answer 200 within 5 seconds, and are disabled after 5 failed deliveries; no official SDKs yet. — [Reap API introduction (primary)](https://docs.reap.video/api-reference/1_introduction.md)
- Reap's own material says the clipping API is on the Creator tier and the reframe endpoint is Studio-only. — [Reap developer API page (primary, marketing)](https://reap.video/api)

**No public clipping API found / not confirmed**
- Descript: a 2026 comparison reports its API as beta and in development with no public API price. — [clipspeed.ai (secondary)](https://www.clipspeed.ai/compare/best-descript-alternatives-2026.html)
- HeyGen lists "clipping" as a separately metered API product, but the meter was not read. — [HeyGen FAQ (primary)](https://www.heygen.com/faq)

### Inferences
- For a self-hosted tool where the agency supplies its own key, Klap fits the "API key + base URL" connector model most cleanly: no plan tier to check, a fixed per-operation price, and roughly $0.84 per finished exported clip plus $0.44 per source video (derived from the published rates).
- Vizard and OpusClip are far cheaper per source hour ($1.45 to $2.90 per hour, secondary figures) but require the agency to hold a Creator/Pro-or-higher subscription, and OpusClip's 10-credit minimum penalises short inputs.
- Reap, Vizard and OpusClip all bundle their own social publishing endpoints; Spark should ignore those and take only the clip URL, since Spark is the scheduler.
- Vendor project retention is short (OpusClip 30 days; Reap returns presigned URLs), so Spark's worker must download clips into its own media library on completion rather than store vendor URLs.
- All five APIs are asynchronous (submit, then poll or webhook). Spark's existing background worker is the natural place for the polling loop; Klap has no documented webhooks, so polling is the common denominator.

### Gaps
- Munch and Riverside: no API documentation was found in any search; treat both as "no public API found".
- Submagic API pricing and plan requirement were not found on its docs landing page; b-roll, zooms, silence removal and hook-title options were not confirmed in the API (only in the product).
- Whether OpusClip and Vizard return a virality score through the API was not confirmed (their Query Clips / Response pages were not read). Klap's score is confirmed only by a sponsored secondary article.
- No vendor documented b-roll insertion as an API output on the pages read.
- Klap rate limits, maximum input length and processing time were not found.
- Current Vizard plan prices were not read from vizard.ai/pricing; the "$29 per user per month" figure seen in search snippets is dated January 2026 and unverified.
- No independent 2026 benchmark of clip-selection quality across these vendors was found; every comparison located was written by a vendor or a sponsored reviewer.

## 2. Text/image to video generation APIs: models, price per second, durations and aspect ratios

### Takeaway
OpenAI's Sora 2 and its Videos API were shut down on 24 September 2026 with no replacement, so late-2026 options are Google (Veo 3.1 family, now moving to token-billed Gemini Omni), Kling 3.0, Runway Gen-4.5, Seedance 2.x, Luma Ray 3.2, MiniMax Hailuo H3, Pika 2.5 and Wan, at roughly $0.03 to $0.70 per second. Clips are short (typically 4 to 15 seconds), so a 30-second Reel means stitching several generations.

### Cited Findings

**Discontinued or changing (flag these)**
- OpenAI Videos API, `sora-2` and `sora-2-pro` shut down on 24 September 2026; notice given 24 March 2026; "no one-to-one replacement". — [OpenAI deprecations (primary)](https://developers.openai.com/api/docs/deprecations)
- Sora 2 on Azure OpenAI retired 15 October 2026; Amazon Nova Reel reached end of life 30 September 2026; Vertex AI Veo 3 and Veo 3 Fast passed their 30 June 2026 discontinuation date. — [Developers Digest, 18 Oct 2026 (secondary)](https://www.developersdigest.tech/blog/image-video-generation-api-pricing-2026)
- Gemini API preview IDs `veo-3.1-generate-preview`, `-fast-preview`, `-lite-preview` and `gemini-omni-flash-preview` were scheduled for 22 October 2026, replaced by `gemini-omni-1.1-flash`, which changes billing from per second to tokens. — [Developers Digest, 18 Oct 2026 (secondary)](https://www.developersdigest.tech/blog/image-video-generation-api-pricing-2026)
- Gemini Omni 1.1 Flash is itself deprecated: from 3 December 2026 requests route to Omni 1.2 Flash at 1.2 rates. — [Google AI Studio pricing (primary)](https://aistudio.google.com/docs/pricing)

**Google**
- Gemini Omni 1.2 Flash: $12.00 per 1M video output tokens, about $0.07/s at 720p, $0.023/s at 360p, $0.104/s at 1080p (upsampled), $0.209/s at 4K (upsampled); up to 15 seconds with native audio; no free tier; about $0.70 for a 10-second 720p clip. — [Google AI Studio pricing (primary)](https://aistudio.google.com/docs/pricing)
- Veo 3.1 on the Gemini API as read on 1 October 2026 (with audio): standard $0.40/s at 720p and 1080p, $0.60/s at 4K; Fast $0.10/s (720p), $0.12/s (1080p), $0.30/s (4K); Lite $0.05/s (720p), $0.08/s (1080p). Durations 4, 6 or 8 seconds. — [UGC Copilot price index, 1 Oct 2026 (secondary; publisher sells its own credits)](https://ugccopilot.ai/research/ai-video-model-price-index/)
- Veo 3.1 on Vertex AI without audio: $0.20/s (720p/1080p), $0.40/s (4K); Fast $0.08 to $0.25/s; Lite $0.03/s (720p), $0.05/s (1080p). — [UGC Copilot price index, 1 Oct 2026 (secondary)](https://ugccopilot.ai/research/ai-video-model-price-index/)

**Runway (API with its own developer portal)**
- Credits cost $0.01 each. Gen-4.5 is 12 credits/s ($0.12/s); Gen-4 Turbo 5 credits/s ($0.05/s); Act-Two 5 credits/s; Aleph 2.0 (video-to-video edit) 28 credits/s with a 56-credit minimum. — [Runway API pricing (primary)](https://docs.dev.runwayml.com/guides/pricing/)
- Runway also resells Veo 3.1 at 40 credits/s with audio and 20 without, and Veo 3.1 Fast at 15 and 10. — [Runway API pricing (primary)](https://docs.dev.runwayml.com/guides/pricing/)
- Runway image models: `gen4_image` 5 credits (720p) or 8 credits (1080p) per image; `gen4_image_turbo` 2 credits per image. — [Runway API pricing (primary)](https://docs.dev.runwayml.com/guides/pricing/)
- Gen-4.5 durations 2 to 10 seconds; Gen-4 Turbo is image-to-video only. — [UGC Copilot price index, 1 Oct 2026 (secondary)](https://ugccopilot.ai/research/ai-video-model-price-index/)
- Gen-4.5 aspect ratios per one reseller: 1280:720, 720:1280, 1104:832, 960:960, 832:1104; durations 5, 8 or 10 seconds. — [Magnific API docs (secondary reseller)](https://docs.magnific.com/api-reference/video/runway-gen-4-5/overview.md); other resellers list different sets, e.g. [OpenRouter](https://openrouter.ai/runway/gen-4.5/llms.txt) says 16:9 and 9:16 only

**Kling 3.0 (official API and fal.ai, same price)**
- 720p $0.084/s silent or $0.126/s with audio; 1080p $0.112/s silent or $0.168/s with audio; 4K $0.42/s; Kling 3.0 Turbo with audio $0.112/s (720p) and $0.14/s (1080p). Clip length 3 to 15 seconds on fal.ai. — [UGC Copilot price index, 1 Oct 2026 (secondary)](https://ugccopilot.ai/research/ai-video-model-price-index/)
- Kling's own API prices in Units: 0.6 / 0.8 / 3.0 Units per second at 720p / 1080p / 4K. — [Developers Digest, 18 Oct 2026 (secondary)](https://www.developersdigest.tech/blog/image-video-generation-api-pricing-2026)

**ByteDance Seedance**
- On fal.ai: Seedance 2.0 $0.3024/s (720p) and $0.682/s (1080p), 4 to 15 seconds; Seedance 2.0 Fast $0.2419/s (720p); Seedance 2.5 $0.2205/s (480p) and $0.473/s (720p), 4 to 30 seconds. Audio included. — [UGC Copilot price index, 1 Oct 2026 (secondary)](https://ugccopilot.ai/research/ai-video-model-price-index/)
- On BytePlus ModelArk the same models are roughly half the fal.ai price: Seedance 2.0 $0.07/s (480p), $0.152/s (720p), $0.374/s (1080p), $0.778/s (4K); Seedance 2.5 $0.1028/s (480p), $0.2312/s (720p), $0.5686/s (1080p). — [UGC Copilot price index, 1 Oct 2026 (secondary)](https://ugccopilot.ai/research/ai-video-model-price-index/)

**Luma, MiniMax, Pika, xAI, Wan**
- Luma Ray 3.2 is priced per clip: $0.15 (540p, 5 s), $0.30 (720p, 5 s), $0.90 (720p, 10 s), $1.20 (1080p, 5 s), $3.60 (1080p, 10 s). — [UGC Copilot price index, 1 Oct 2026 (secondary)](https://ugccopilot.ai/research/ai-video-model-price-index/)
- MiniMax Hailuo H3: $0.08/s (768p), $0.13/s (2K), 4 to 15 seconds. — [UGC Copilot price index, 1 Oct 2026 (secondary)](https://ugccopilot.ai/research/ai-video-model-price-index/)
- Pika 2.5: $0.04/s (720p) to $0.09/s (1080p), and requires a $10/month membership on top of usage. — [UGC Copilot price index, 1 Oct 2026 (secondary)](https://ugccopilot.ai/research/ai-video-model-price-index/)
- xAI Grok Imagine Video 1.5: $0.08 / $0.14 / $0.25 per second at 480p / 720p / 1080p; Lite $0.02 / $0.03 / $0.14; clips 1 to 15 seconds. — [Developers Digest, 18 Oct 2026 (secondary)](https://www.developersdigest.tech/blog/image-video-generation-api-pricing-2026)
- Alibaba Wan: `wan2.6-i2v-flash` $0.025/s silent or $0.05/s with audio at 720p; Wan 3.0 on Replicate $0.025 / $0.05 / $0.10 per second at 480p / 720p / 1080p (the article notes the readme and billing table disagree). — [Developers Digest, 18 Oct 2026 (secondary)](https://www.developersdigest.tech/blog/image-video-generation-api-pricing-2026)

**Aggregators and Higgsfield**
- Replicate lists Veo 3.1 at $0.20/s silent and $0.40/s with audio, Veo 3.1 Fast at $0.10 and $0.15. — [Developers Digest, 18 Oct 2026 (secondary)](https://www.developersdigest.tech/blog/image-video-generation-api-pricing-2026)
- Higgsfield's API is described by Higgsfield as a standalone product with its own dollar balance; a website plan neither grants API access nor changes API pricing. — [Higgsfield blog (primary, marketing)](https://higgsfield.ai/blog/higgsfield-api)
- Higgsfield API billing is prepaid from a $5 top-up with no subscription. — [Layer3 Labs guide, updated 21 Sep 2026 (secondary)](https://www.layer3labs.io/guides/higgsfield-api)
- Shotstack resells generation inside its render API: a 5-second MiniMax H3 clip at 768p is 1.88 credits (38 cents). — [Shotstack pricing (primary)](https://shotstack.io/pricing/)

### Inferences
- Cheapest usable 9:16 social clip with audio in late 2026 is roughly $0.05 to $0.10 per second (Veo 3.1 Lite/Fast, Omni 1.2 Flash, Wan 2.6, Hailuo H3); premium tiers run $0.17 to $0.70 per second. A 15-second Reel therefore costs about $1 to $1.50 at the low end and $6 to $10 at the top (derived from the rates above).
- Google's model IDs and billing units changed three times within about ten weeks (Veo previews → Omni 1.1 → Omni 1.2). A Spark connector should treat the model ID as a free-text setting and should not hard-code a price or a per-second assumption.
- An aggregator connector (fal.ai or Replicate) gives one key and one base URL for Kling, Seedance, Veo, Wan and others, which matches Spark's connector model better than five vendor integrations. The trade-off is price: Seedance on fal.ai is about double BytePlus direct, while Kling is identical.
- Because Sora was retired, any design doc or prompt in Spark that names Sora should be treated as stale.

### Gaps
- fal.ai's own model pages were not fetched; all fal.ai prices here come from secondary trackers that disagree with each other (one snippet claimed Kling 3.0 at about $0.029/s on fal.ai, contradicting the $0.084 to $0.42/s index). Verify on the exact fal.ai endpoint before quoting.
- Whether Veo 3.1 is still callable on the Gemini API after 22 October 2026 was not confirmed: the Google pricing page read was truncated and showed only Omni; Runway and Vertex still list Veo 3.1.
- No Veo 4 was found in any source.
- Official aspect-ratio lists were not found for most models; Runway's own docs page did not state them and resellers conflict.
- Higgsfield per-endpoint API prices are not published in its documentation (per secondary sources), and its console/docs hostnames differ between sources (cloud.higgsfield.ai, console.higgsfield.ai, docs.higgsfield.ai).
- Rate limits and typical generation latency were not found for any video model.
- Commercial-use and output-ownership terms for each video model were not researched.

## 3. Image generation/editing APIs and template-based rendering: which support brand kits/templates via API

### Takeaway
Generative image APIs cluster at $0.03 to $0.04 per 1K image, with OpenAI's older image models being retired through December 2026 (Spark's default `gpt-image-1` was shut down on 23 October 2026). For brand-consistent graphics, template renderers (Bannerbear, Placid, Templated, Creatomate, Shotstack) give deterministic layouts at $0.01 to $0.05 per image with self-serve APIs, whereas Canva's autofill/brand-template API is documented as requiring Canva Enterprise and Adobe Firefly Services is sales-quoted.

### Cited Findings

**OpenAI image models (affects Spark's existing connector)**
- `gpt-image-1` shutdown date 23 October 2026 (replacement `gpt-image-2.5-sunburst` or `-flare`); `gpt-image-1.5` and `gpt-image-1-mini` shut down 1 December 2026 (replacement `gpt-image-2.6-sunburst` or `-flare`); `dall-e-2` and `dall-e-3` shut down 12 May 2026. — [OpenAI deprecations (primary)](https://developers.openai.com/api/docs/deprecations)
- Spark repo: `src/spark/config.py` line 37 sets `image_model: str = "gpt-image-1"` and the connector help text reads "gpt-image-1 unless OpenAI tells you otherwise." — Spark repo, `/Users/magnetoid/c/spark/src/spark/config.py` and `/Users/magnetoid/c/spark/src/spark/services/connectors.py` (read 2026-11-13; no URL)
- GPT Image 2.5 Sunburst/Flare are token-priced only: $30 per 1M image output tokens ($15 batch), image input $8 per 1M. — [Developers Digest, 18 Oct 2026 (secondary)](https://www.developersdigest.tech/blog/image-video-generation-api-pricing-2026)
- GPT Image 2 at 1024x1024: $0.006 (low), $0.053 (medium), $0.211 (high). — [Developers Digest, 18 Oct 2026 (secondary)](https://www.developersdigest.tech/blog/image-video-generation-api-pricing-2026)

**Google image models**
- Nano Banana 2.1: $0.0336 (1K), $0.0504 (2K), $0.113 (4K) per image; batch is half. Nano Banana 2 Lite: $0.0336 (1K). Gemini 3 Pro Image (Nano Banana Pro): $0.134 (1K/2K), $0.24 (4K). — [Google AI Studio pricing (primary)](https://aistudio.google.com/docs/pricing)
- Gemini 2.5 Flash Image ($0.039 per image) is deprecated and shuts down 15 March 2027. — [Google AI Studio pricing (primary)](https://aistudio.google.com/docs/pricing)
- Imagen on the Gemini API was shut down 17 August 2026; Vertex AI Imagen 4 had a 30 June 2026 discontinuation date. — [Developers Digest, 18 Oct 2026 (secondary)](https://www.developersdigest.tech/blog/image-video-generation-api-pricing-2026)

**Flux, Ideogram, Recraft, others**
- FLUX 2: klein $0.014 to $0.015 flat; pro $0.03 per megapixel to create and $0.045 per megapixel to edit; flex $0.05 to $0.06; max $0.07. Flux Kontext pro $0.04 and max $0.08 per edit. — [invideo price table, Aug 2026 (secondary)](https://invideo.io/blog/ai-image-model-pricing/)
- A newer FLUX 3 Image Klein is listed at $0.009 (1K) and $0.014 (2K). — [Developers Digest, 18 Oct 2026 (secondary)](https://www.developersdigest.tech/blog/image-video-generation-api-pricing-2026)
- FLUX.2 supports precise colour matching by hex code in the prompt. — [Black Forest Labs FLUX.2 prompting guide (primary)](https://docs.bfl.ai/guides/prompting_guide_flux2)
- Ideogram 4.5 Generate: $0.03 (low) to $0.10 (high), $0.22 with source images. — [Developers Digest, 18 Oct 2026 (secondary)](https://www.developersdigest.tech/blog/image-video-generation-api-pricing-2026)
- Recraft V4.1 $0.035 per image, V4.1 Pro $0.21, vector/SVG endpoints $0.08 to $0.30; cuts took effect 20 June 2026. On Recraft's free plan Recraft owns the images and they carry no commercial licence. — [invideo price table, Aug 2026 (secondary)](https://invideo.io/blog/ai-image-model-pricing/)
- Recraft's API has a Create style endpoint that takes reference images with per-image weights, producing a reusable style ID. — [Recraft API docs: V4 styles (primary)](https://www.recraft.ai/docs/api-reference/models/recraft-v4-styles.md)
- Common price band for a production-quality 1024x1024 image is $0.03 to $0.04. — [invideo price table, Aug 2026 (secondary)](https://invideo.io/blog/ai-image-model-pricing/)

**Template-based rendering (all have self-serve REST APIs)**
- Bannerbear: Automate $49/month for 1,000 API credits, Scale $149 for 10,000, Enterprise $299 for 50,000. An image is 1 credit; animation 2 credits per second; burning subtitles onto video is 4 credits (it transcribes and re-encodes); REST API with OpenAPI spec, Node/Python/Ruby/PHP libraries and MCP; 30-credit trial. — [Bannerbear pricing (primary)](https://www.bannerbear.com/pricing/)
- Placid: plans of 500 / 2,500 / 25,000 / 100,000 credits; 1 image = 1 credit, video = 10 credits per 10 seconds, PDF = 2 credits per page; video up to 1920x1080; REST API and URL API; unused credits roll over up to double; no overage fees. — [Placid pricing (primary)](https://placid.app/pricing)
- Templated: Starter $39/month ($29 annual) for 1,000 credits and 15 templates at 60 requests/min; Scale $99 for 5,000 credits; Enterprise $229 for 25,000. Image = 1 credit; video credits = width x height x fps x duration / 50,000,000 (1080p, 30 fps, 10 s = 13 credits). Includes Canva design import, MCP, and a white-label embedded editor on Scale. — [Templated pricing (primary)](https://templated.io/pricing/)
- Creatomate: Essential $45/month for 2,000 credits, Growth $108 for 10,000+, Beyond $274 for 50,000+. Image = 1 credit; a 30-second vertical 720p video is the reference unit (about 289 per month on Essential). API on every plan including the free 50-credit plan; renders kept 30 days. — [Creatomate pricing (primary)](https://creatomate.com/pricing)
- Shotstack (JSON timeline video render API): pay-as-you-go $10 for 50 minutes (20 cents/min, 1080p); Starter $39 for 250 minutes (15.6 cents/min); Pro $99 for 750 (13.2 cents, 4K); Scale $199 for 2,000 (10 cents); Volume $499 for 10,000 (5 cents). Credits also buy AI generation: GPT Image 2.5 at 1K is 7 cents, ElevenLabs Turbo v2.5 voice is 6 cents per 1,000 characters. — [Shotstack pricing (primary)](https://shotstack.io/pricing/)
- Shotstack's white-label editor is source-available under a PolyForm Shield licence and uses FFmpeg for exports. — [Shotstack pricing (primary)](https://shotstack.io/pricing/)

**Canva and Adobe**
- Canva's autofill job endpoint and autofill guide state that the integration must act on behalf of a user in a Canva Enterprise organisation. — [Canva Connect: create design autofill job (primary)](https://www.canva.dev/docs/connect/api-reference/autofills/create-design-autofill-job/); [Canva autofill guide (primary)](https://www.canva.dev/docs/apps/rest-apis/autofill-guide/); a different Canva page says Pro, Teams and Nonprofit users also qualify: [Canva dataset endpoint docs](https://canva.dev/docs/connect/api-reference/brand-templates/get-brand-template-dataset)
- Canva's own n8n article says autofill requires Enterprise, with limited development trial quotas for paid-plan users; the flow is asynchronous (read the template's dataset, submit a job, poll). — [Canva developer blog (primary)](https://www.canva.dev/blog/developers/automate-canva-with-n8n/)
- Adobe Firefly Services is metered in "operations", for example 25 operations per output asset for refreshed product imagery and 15 operations per second of product video. — [Adobe Firefly Services rate card (primary)](https://helpx.adobe.com/business/enterprise/kb/fireflyservices-ratecard-ver-a.html)
- Firefly custom models: train subject or style models, then call the Generate Image API with a custom model asset ID. — [Adobe Firefly API developer page (primary)](https://developer.adobe.com/firefly-api)
- A third-party advisory site quotes $1,000 to $5,000 per month per custom model and $100 to $250 per 1,000 API calls. — [Redress Compliance (secondary; reseller/advisor, does not match Adobe's operations metering)](https://redresscompliance.com/adobe-firefly-enterprise-pricing-2026)

### Inferences
- Spark's OpenAI image connector is very likely already failing on default settings, because its default model was shut down three weeks before this research; the two models OpenAI named as its replacement are themselves superseded by the 2.6 family. Fixing the default (and making the model a visible setting with a "last verified" note) is a prerequisite to any new image work.
- "Brand kit via API" exists in three different forms: (a) deterministic templates with named layers (Bannerbear, Placid, Templated, Creatomate), (b) a trained or referenced style ID (Recraft styles, Adobe custom models), and (c) prompt-level control such as hex colours and multi-reference images (FLUX.2). Only (a) guarantees logo placement, fonts and exact colours.
- Derived per-image costs for templates: Creatomate about $0.023, Templated about $0.029 to $0.039, Bannerbear about $0.049. These are comparable to a generative image, so the choice is about determinism, not price.
- A practical pattern for a small agency is generative background (Nano Banana 2.1 or Flux at about $0.03) composited into a template render, which Bannerbear and Shotstack already bundle.
- Canva is a poor fit as a default connector for a small agency because of the Enterprise requirement; Templated's "import designs from Canva" is a workaround worth noting.

### Gaps
- Ideogram's style-reference and character-reference API parameters were not confirmed in Ideogram's own docs (only a secondary claim of "up to 10 reference images").
- Whether Recraft's API exposes locked brand colours directly (as opposed to the in-app Brand Kit) was not confirmed.
- FLUX.2 multi-reference limit conflicts across sources (8 via API, 10 in playground, per a secondary source); not verified with BFL.
- Placid dollar prices were not shown on the page read (a competitor snippet said $19/month for 500 credits; unverified).
- No Adobe Express API documentation or pricing was found; Firefly Services list prices are not public.
- Commercial-use terms were found only for Recraft's free plan; licence terms for GPT Image, Gemini image, Flux and Ideogram outputs were not researched.
- Rate limits and latency for image models were not found.
- Seedream pricing was not covered by any source read.

## 4. Transcription and captions: hosted Whisper-class APIs versus open-source in a worker container

### Takeaway
Hosted batch transcription costs $0.12 to $0.36 per audio hour, which is small enough that cost is not the deciding factor for a small agency; faster-whisper (MIT) plus ffmpeg in the worker is a viable zero-marginal-cost option that also gives word-level timestamps for burned-in captions. OpenAI's `whisper-1` is scheduled to shut down on 26 February 2027.

### Cited Findings

**Hosted APIs (batch, per audio hour, list price as of 3 Nov 2026)**
- AssemblyAI Universal-2 $0.15 (99 languages); Universal-3.5 Pro $0.21, with diarization +$0.02 and keyterms +$0.05. — [AssemblyAI pricing guide, 3 Nov 2026 (vendor-authored comparison)](https://assemblyai.com/blog/speech-to-text-api-pricing)
- Deepgram Nova-3 monolingual $0.258 batch, $0.462 streaming. — [AssemblyAI pricing guide, 3 Nov 2026 (competitor-authored)](https://assemblyai.com/blog/speech-to-text-api-pricing)
- OpenAI `gpt-transcribe` $0.27, `gpt-4o-transcribe` $0.36, `gpt-4o-mini-transcribe` $0.18 (per-minute figures are estimates). — [AssemblyAI pricing guide, 3 Nov 2026 (competitor-authored)](https://assemblyai.com/blog/speech-to-text-api-pricing)
- OpenAI `whisper-1` shuts down 26 February 2027 (notice 26 August 2026); replacements are `gpt-transcribe` or `gpt-live-transcribe`, which are also listed as the replacement for the GPT-4o transcribe models. — [OpenAI deprecations (primary)](https://developers.openai.com/api/docs/deprecations)
- ElevenLabs Scribe v2 and v3: $0.20 per hour; keyterm prompting +$0.05 per hour. — [ElevenLabs API pricing (primary)](https://elevenlabs.io/pricing/api); AssemblyAI's guide lists Scribe v2 at $0.22: [AssemblyAI pricing guide](https://assemblyai.com/blog/speech-to-text-api-pricing)
- Speechmatics Melia 1 $0.12, Standard $0.23, Enhanced $0.38; Gladia Solaria-3 EUR 0.16 with diarization bundled; Google Speech-to-Text V2 dynamic batch $0.18. — [AssemblyAI pricing guide, 3 Nov 2026 (competitor-authored)](https://assemblyai.com/blog/speech-to-text-api-pricing)

**Open source in the worker**
- faster-whisper is MIT-licensed; supports word-level timestamps (`word_timestamps=True`), Silero VAD filtering (`vad_filter=True`), and a `BatchedInferencePipeline`; needs Python 3.9+; FFmpeg does not need to be installed because PyAV bundles the FFmpeg libraries; GPU use needs CUDA 12 with cuDNN 9; model names include `large-v3`, `turbo` and `distil-large-v3`. — [SYSTRAN/faster-whisper README (primary)](https://github.com/SYSTRAN/faster-whisper)
- Benchmark, 13 minutes of audio: large-v2 on an RTX 3070 Ti takes 1m03s (fp16) or 17s batched at 8, using 4.5 to 6.1 GB VRAM; the small model on an i7-12700K CPU (8 threads, int8) takes 1m42s, or 51s batched, using 1.5 to 3.6 GB RAM. — [SYSTRAN/faster-whisper README (primary)](https://github.com/SYSTRAN/faster-whisper)
- Whisper large-v3-turbo is reported as about 6x faster than large-v3 on CPU through faster-whisper (about 20 s versus 143 s per file on an i7) and is MIT-licensed. — [VexaScribe decision guide (secondary)](https://vexascribe.com/whisper-large-v3-vs-turbo)
- A Ryzen 7 7700X is reported at about 10x real time with INT8 on CPU; guidance is that CPU-only suits batch work. — [LocalAIMaster faster-whisper guide (secondary)](https://localaimaster.com/blog/faster-whisper-guide)
- Turbo is reported at about 80x real time single-stream and 175x batched at 16 on an RTX 4090. — [Spheron deployment guide (secondary; GPU vendor)](https://www.spheron.network/blog/faster-whisper-gpu-cloud-production-deployment-guide/)

**Captions as a service inside other tools**
- Bannerbear burns subtitles onto a video for 4 credits (transcribe plus re-encode). — [Bannerbear pricing (primary)](https://www.bannerbear.com/pricing/)
- Submagic (styled animated captions, 100+ languages), Klap (captions and reframing on already-short videos) and Reap (`create-captions`, `create-transcription` with word-level timestamps) expose captioning as API operations. — [Submagic docs](https://docs.submagic.co/introduction); [Klap docs](https://docs.klap.app/); [Reap API introduction](https://docs.reap.video/api-reference/1_introduction.md)

### Inferences
- At $0.15 to $0.27 per hour, transcribing 20 hours of client video a month costs $3 to $5.40 on a hosted API. The case for self-hosting is privacy, no extra key to manage and no vendor churn, not money.
- A CPU-only worker container can plausibly run faster-whisper `turbo` with int8 at several times real time (secondary figures of 6x to 10x), which is adequate for a background job queue; the main cost is 1.5 to 4 GB of extra worker RAM and a larger image.
- The simplest "captions v1" for Spark with no new vendor is faster-whisper word timestamps → generate an ASS/SRT file → burn in with ffmpeg in the worker. This yields plain or lightly styled captions; the animated word-by-word "Hormozi" styles are what Submagic, Klap and Reap sell.
- ElevenLabs Scribe is the natural hosted option if Spark adds an ElevenLabs connector for voice anyway, since one key then covers both speech-to-text and text-to-speech.
- If any Spark code or plan references `whisper-1`, it has a hard end date of 26 February 2027.

### Gaps
- No independent 2026 word-error-rate benchmark comparing these hosted models with Whisper large-v3/turbo was found; quality trade-offs here rest on vendor claims and should be treated as unverified.
- Deepgram's own pricing page was not read; its figures come from a competitor's comparison.
- WhisperX (forced alignment and diarization) accuracy and current maintenance status were not verified.
- faster-whisper's latest release version and date were not shown on the page read.
- The self-hosted versus API cost table found (Groq hosted large-v3 at about $0.02, self-hosted on an L4 at $0.15 to $0.25) had unclear units and is not relied on.
- Word-timestamp add-on pricing was not listed for any hosted provider.

## 5. AI voice and avatar/UGC video APIs: availability, price, disclosure requirements

### Takeaway
ElevenLabs (voice), HeyGen and Creatify (avatar/UGC video) have documented self-serve APIs with published per-unit prices; Synthesia's API sits on its Creator plan; Arcads API access is reported as higher-tier or custom-quoted with no public docs found; no Captions (Mirage) API documentation was found. Avatar video costs roughly $2 to $4 per finished minute, and realistic synthetic people and voices are exactly the content platforms require to be labelled.

### Cited Findings

**ElevenLabs (integrable)**
- Text-to-speech per 1,000 characters: v3 $0.08, Multilingual v2 $0.08, Flash/Turbo $0.04. — [ElevenLabs API pricing (primary)](https://elevenlabs.io/pricing/api)
- Dubbing v1 $0.33 per minute with watermark or $0.50 without; Dubbing v2 $2.20 per minute; Music $0.15 per minute; Sound Effects $0.12 per minute; Voice Isolator and Voice Changer $0.12 per minute. — [ElevenLabs API pricing (primary)](https://elevenlabs.io/pricing/api)
- Subscription tiers: Starter $6 (75,000 characters), Creator $22 (275,000), Pro $99, Scale $299, Business $990. Concurrency limits rise by tier from 4 to 40 concurrent calls. — [ElevenLabs API pricing (primary)](https://elevenlabs.io/pricing/api)
- Commercial-use licensing is stated for Music on Starter and above. — [ElevenLabs API pricing (primary)](https://elevenlabs.io/pricing/api)
- ElevenLabs voices are also resold through Runway (ElevenLabs v3 at 1 credit per 50 characters) and Shotstack (Turbo v2.5 at 6 cents per 1,000 characters). — [Runway API pricing](https://docs.dev.runwayml.com/guides/pricing/); [Shotstack pricing](https://shotstack.io/pricing/)

**HeyGen (integrable)**
- Enterprise docs: Avatar IV costs 0.1 credits per second for Photo, Digital Twin and Studio avatars, and 1 credit costs $0.50, i.e. $0.05 per second. — [HeyGen enterprise pricing docs (primary)](https://developers.heygen.com/docs/enterprise-pricing)
- HeyGen's help article estimates about $4 per minute of Avatar IV video via API at 1080p. — [HeyGen Avatar IV guide (primary)](https://help.heygen.com/en/articles/11269603-heygen-avatar-iv-complete-guide)
- Pay-as-you-go API starts at $5 with no fixed cost and includes video generation and TTS. — [HeyGen FAQ (primary)](https://www.heygen.com/faq)
- HeyGen's own comparison post states metering per second of output at $0.05/s from a separate USD wallet. — [HeyGen blog (primary, marketing)](https://www.heygen.com/blog/best-ai-avatar-talking-head-apis)

**Creatify (integrable, UGC ad focus)**
- API plans: Starter $99/month for 500 credits; Pro $299/month for 2,000 credits; Enterprise custom. — [Creatify API billing docs (primary)](https://docs.creatify.ai/billing)
- Credit costs: URL to Video 5 per 30 s; AI Avatar lipsync 5 per 30 s; AI Shorts / AI Editing 5 per 30 s; Custom Template Video 5 per 30 s; Text to Speech 1 per 30 s; Aurora 2.0 avatar 0.4 / 0.7 / 1.4 / 2.8 per second at 480p / 720p / 1080p / 2K; Product Video 2 per image or 10 per 30 s; Ad Clone 12 per 5 s; AI Scripts 1 per request. — [Creatify API billing docs (primary)](https://docs.creatify.ai/billing)
- Endpoint families: URL to Video, Boreal (prompt/image/audio to video ad), Aurora Avatar, Stock AI Avatar lipsync-v2 with 1,500+ personas, Custom Templates, Asset Generator, Ad Clone, IAB Images, Custom Avatar. — [Creatify API reference (primary)](https://docs.creatify.ai/api-reference/introduction)

**Synthesia, Arcads**
- Synthesia: API access comes with the Creator plan and draws on the same credit pool at 90 credits per minute of API generation; the Dubbing API is Enterprise-only; verified against Synthesia's pricing page in August 2026. — [Creatify blog on Synthesia pricing (secondary; competitor)](https://creatify.ai/blog/synthesia-pricing-(2026)-plans-credits-and-what-you-ll-actually-pay)
- Arcads: 800 credits per billed minute per actor, rounded up to the next minute; API not included on Creator, only on the higher Pro tier. — [Creatify blog on Arcads pricing (secondary; competitor)](https://creatify.ai/blog/arcads-pricing-(2026)-plans-credits-and-what-you-ll-actually-pay); contradicted by [FluxNote, verified June 2026](https://fluxnote.io/guides/arcads-pricing-2026), which lists $110/month Starter (10 videos), $220/month Creator (20 videos) and says API access is custom-quoted
- Arcads has not provided pricing information to G2. — [G2](https://www.g2.com/products/arcads/pricing)

**Disclosure requirements relevant to avatars and cloned voices**
- Meta may require an AI label when content has photorealistic video or realistic-sounding audio on Facebook, Instagram and Threads; the requirement does not apply to images. — [Meta help: identifying AI content (primary)](https://www.meta.com/en-gb/help/artificial-intelligence/1783222608822690/)
- YouTube requires creators to disclose realistic AI use, and from May 2026 applies a label automatically when it detects significant photorealistic AI use. — [YouTube blog, 27 May 2026 (primary)](https://blog.youtube/news-and-events/improving-ai-labels-viewers-creators/)
- Instagram requires an "AI-generated profile" label for profiles featuring AI-generated people from 31 August 2026; unlabelled profiles lose recommendation eligibility. — [Billo, 16 Oct 2026 (secondary)](https://billo.app/blog/ai-labeling/)
- On TikTok, undisclosed AI ads are rejected or restricted. — [Billo, 16 Oct 2026 (secondary)](https://billo.app/blog/ai-labeling/)

### Inferences
- Derived costs per finished minute: HeyGen Avatar IV about $3.00 (at $0.05/s) to $4.00 (help-article estimate); Creatify stock-avatar lipsync about $1.98 on API Starter (10 credits per minute at $0.198 per credit) and about $1.50 on API Pro; Creatify Aurora 2.0 at 720p about $8.30 per minute on Starter. ElevenLabs narration for a 150-word (about 900 characters) 60-second script is about $0.07 at v3 rates.
- HeyGen's $5 pay-as-you-go wallet suits Spark's "bring your own key" model; Creatify's API has a $99/month floor, which is a meaningful commitment for a small agency that only occasionally makes UGC-style ads.
- Voice is the cheapest and lowest-risk first step: ElevenLabs TTS plus a template renderer (or ffmpeg) produces narrated slideshows/quote videos without any avatar likeness issues.
- Any avatar or cloned-voice output should set Spark's AI-disclosure flag to on by default, because it is by definition photorealistic synthetic people or realistic synthetic audio (the category Meta, YouTube and TikTok all single out).

### Gaps
- HeyGen's self-serve API price page redirects into the logged-in app and could not be read. Third-party summaries (not traced to a single page) report Avatar IV Digital Twin at $0.0667/s, Avatar III Photo Avatar at $0.0433/s, Video Agent at $0.0333/s, API credits expiring after 12 months, and free API credits removed in February 2026; all unverified.
- HeyGen and Creatify rate limits, concurrency, max duration, resolution and auth header details were not found on the pages read.
- Captions (the app, "Mirage" model): two searches returned no API documentation or pricing; list as "no public API found".
- Arcads: no official API documentation found; list as "no public API found (API reportedly on higher/custom tiers)".
- Synthesia's own API docs and current plan prices were not read; the only source is a competitor's blog.
- ElevenLabs voice-cloning price and consent/verification requirements, and commercial-use terms for TTS output by plan, were not stated on the pricing page read.
- Likeness/consent rules for custom avatars (HeyGen, Creatify, Synthesia) were not researched.

## 6. Platform rules on AI-generated content labelling that a scheduler must pass through

### Takeaway
Three platforms have a documented publish-time API flag for AI disclosure: TikTok (`is_aigc`), YouTube (`status.containsSyntheticMedia`) and Instagram (`is_ai_generated`, added 22 June 2026). Platforms also label automatically from C2PA/IPTC metadata and their own detectors, and EU AI Act Article 50 transparency duties have applied since 2 August 2026, so a scheduler should carry one "AI-generated" boolean per post and map it per platform. Spark currently has no such field.

### Cited Findings

**Publish-time API flags (primary documentation)**
- TikTok Content Posting API, Direct Post `post_info.is_aigc` (bool, optional, default false): "Set to true if the video is AI generated content." When set, the video is labelled with the "Creator labeled as AI-generated" tag. — [TikTok Content Posting API reference (primary)](https://developers.tiktok.com/doc/content-posting-api-reference-direct-post)
- The same TikTok `post_info` requires `brand_content_toggle` and offers `brand_organic_toggle`; rate limit is 6 requests per minute per user token; unaudited API clients can only post privately. — [TikTok Content Posting API reference (primary)](https://developers.tiktok.com/doc/content-posting-api-reference-direct-post)
- YouTube Data API: "To indicate whether a video contains A/S content, set the `status.containsSyntheticMedia` property" on `videos.insert` or `videos.update`; added 30 October 2024. No 2025 or 2026 revision entries about AI disclosure were found in the portion of the page read. — [YouTube Data API revision history (primary)](https://developers.google.com/youtube/v3/revision_history)
- Instagram: since 22 June 2026 the Content Publishing API "supports self-disclosure of AI-generated content at publish time" by setting `is_ai_generated` to `true` on `POST /{ig_user_id}/media`; for carousels it is set on the carousel container only; readable via `GET /{ig_media_id}?fields=is_ai_generated`; available with both Facebook Login and Instagram Login. — [Instagram Platform changelog (primary)](https://developers.facebook.com/documentation/instagram-platform/changelog.md)
- Related Instagram change on 22 April 2026: `is_paid_partnership` and `branded_content_sponsor_ids` (up to 2) add the "Paid partnership" label at publish time. — [Instagram Platform changelog (primary)](https://developers.facebook.com/documentation/instagram-platform/changelog.md)

**Flags reported by a third-party publishing API (not verified against platform docs)**
- Upload-Post maps a single `is_ai_generated` alias to: TikTok `is_aigc`, Instagram `is_ai_generated`, YouTube `containsSyntheticMedia`, X `made_with_ai` (media posts only), Threads `is_made_with_ai` (its own parameter list calls it `threads_is_made_with_ai`), and Facebook Reels only. — [Upload-Post AI labelling guide (secondary)](https://docs.upload-post.com/guides/ai-content-labeling)
- No API-level parameter exists for Facebook Page non-Reel posts, LinkedIn or Pinterest; LinkedIn labels automatically from C2PA Content Credentials and Pinterest from IPTC metadata and its own classifiers. — [Upload-Post AI labelling guide (secondary)](https://docs.upload-post.com/guides/ai-content-labeling)

**Platform behaviour and policy**
- YouTube, 27 May 2026: the label for photorealistic, meaningfully AI-altered or generated content now sits below the player on long-form and as an overlay on Shorts; YouTube auto-applies a label when its systems detect significant photorealistic AI use and the creator has not disclosed; creators can dispute in Studio, except for content made with YouTube's own tools (Veo, Dream Screen) or whose C2PA metadata indicates fully generative AI, which stays labelled; a label alone does not change recommendations or monetisation eligibility. — [YouTube blog, 27 May 2026 (primary)](https://blog.youtube/news-and-events/improving-ai-labels-viewers-creators/)
- Meta: since June 2026 Meta detects third-party AI tools in ads through C2PA metadata and shows "AI info" under "About this ad". — [Billo, 16 Oct 2026 (secondary)](https://billo.app/blog/ai-labeling/)
- TikTok adopted C2PA Content Credentials in May 2024, combines creator labels, C2PA metadata, invisible watermarks and its own detection, and had labelled over 3 billion pieces of content by July 2026. — [Billo, 16 Oct 2026 (secondary)](https://billo.app/blog/ai-labeling/)
- Google Ads: since 9 July 2026 a "How this ad was made" section exists; advertisers declare AI use from non-Google tools. — [Billo, 16 Oct 2026 (secondary)](https://billo.app/blog/ai-labeling/)
- C2PA: Content Credentials 2.4 (April 2026) added a dedicated AI disclosure assertion; the Interim Trust List was frozen 1 January 2026 so tampered or self-signed manifests no longer validate; many distribution pipelines strip metadata on upload, so platform detection does most of the enforcement. — [Billo, 16 Oct 2026 (secondary)](https://billo.app/blog/ai-labeling/)
- EU AI Act Article 50 applies from 2 August 2026; AI systems already on the EU market have until 2 December 2026 to add machine-readable marking. — [Billo, 16 Oct 2026 (secondary)](https://billo.app/blog/ai-labeling/)

**Spark's current position**
- Spark repo: a search of the code for `is_aigc`, `containsSyntheticMedia`, `is_ai_generated` and `ai_generated` returned no matches; publishing goes through `src/spark/platforms/zernio.py`. — Spark repo, `/Users/magnetoid/c/spark/src/spark/platforms/zernio.py` (read 2026-11-13; no URL)
- A public Zernio feature-request page exists titled "AI-Generated Content Disclosure for Facebook and Pinterest". — [Zernio feature board (primary, title only; page not read)](https://zernio.featurebase.app/p/feature-request-ai-generated-content-disclosure-for-facebook-and-pinterest)

### Inferences
- Spark needs one per-post boolean (for example `ai_generated`) plus a per-platform mapping, defaulting to on when media came from a generation connector (image, video, avatar, cloned voice) and editable by the user for media uploaded from elsewhere.
- Because Spark publishes through Zernio rather than directly, the pass-through depends on Zernio exposing these fields; the existence of a feature request for Facebook and Pinterest suggests Zernio already supports some platforms but this must be checked in Zernio's API docs.
- Spark's worker should not strip metadata when it re-encodes or resizes media: generated images and video from Google, OpenAI and Adobe commonly carry C2PA/IPTC provenance that platforms read, and on YouTube a fully generative C2PA marker makes the label permanent. Preserving provenance is the honest default and avoids a mismatch between Spark's flag and the platform's own detection.
- Paid-partnership flags sit beside AI flags in the same publish calls (TikTok `brand_content_toggle`, Instagram `is_paid_partnership`), so the two disclosures can share one "post disclosures" section in the composer.
- For EU-facing clients, Article 50 makes disclosure of realistic synthetic media a legal matter and not only a platform rule; this is the report writer's cue to recommend legal review, since the legal detail here comes from one secondary source.

### Gaps
- Threads, X and Facebook Reels AI-disclosure parameters are attested only by a third-party API vendor; Meta's Threads and Pages references and X's API docs were not checked, and the Threads field name is inconsistent within that vendor's own page.
- Whether Zernio's publishing API accepts and forwards `is_aigc`, `containsSyntheticMedia` and `is_ai_generated` was not checked.
- LinkedIn and Pinterest official policy pages were not read.
- The second half of the YouTube revision history (older entries) was not read; this does not affect the 2025 to 2026 finding.
- EU AI Act Article 50 dates and the C2PA version history come from one secondary source and were not checked against the regulation text or the C2PA specification.
- Penalties for non-disclosure on organic (non-ad) posts on Meta and TikTok were not found; YouTube's announcement mentions none.
- Whether each generation API (Kling, Runway, Seedance, Flux, Ideogram, HeyGen, Creatify, ElevenLabs) embeds C2PA manifests or watermarks in its output was not researched.
- TikTok's and Meta's own policy pages on AI-generated content were not fetched; the TikTok flag itself is confirmed from developer docs.
