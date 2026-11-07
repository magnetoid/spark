"""Claude-powered content generation.

Every request carries the brand voice in a cached system block, so repeated
generations for the same brand reuse the prompt cache.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Literal

import anthropic
from pydantic import BaseModel, Field

from spark.config import get_settings
from spark.models import Brand
from spark.platforms import registry

log = logging.getLogger(__name__)

SYSTEM = """You are Spark, a senior social media strategist and copywriter working for one brand.
Write copy that sounds like the brand, not like an AI: concrete, specific, no filler,
no clichés ("unlock", "elevate", "game-changer", "in today's fast-paced world"),
and no emoji unless the brand voice uses them. Respect each platform's culture and
character limits exactly. Never invent facts, prices, statistics or quotes that
were not given to you; if something is unknown, write around it."""


class AIUnavailable(Exception):
    pass


class PostDraft(BaseModel):
    platform: str = Field(description="Platform key, e.g. x, linkedin, instagram")
    text: str = Field(description="Ready-to-publish post text, within the platform's limit")
    hashtags: list[str] = Field(default_factory=list, description="Hashtags without '#'")
    image_prompt: str | None = Field(None, description="Optional prompt for an accompanying image")


class Drafts(BaseModel):
    drafts: list[PostDraft]


class Rewrite(BaseModel):
    text: str


class Hashtags(BaseModel):
    hashtags: list[str]


class PlannedPost(BaseModel):
    date: str = Field(description="ISO date YYYY-MM-DD")
    theme: str
    text: str
    platforms: list[str]


class CampaignPlan(BaseModel):
    summary: str
    posts: list[PlannedPost]


class EmailDraft(BaseModel):
    subject: str
    preheader: str
    body_html: str = Field(description="Email body as simple inline-styled HTML (no <html>/<body>)")


def _limits_text(platforms: list[str]) -> str:
    reg = registry()
    lines = []
    for p in platforms:
        if p in reg:
            lim = reg[p].limits
            lines.append(f"- {p} ({reg[p].label}): max {lim.max_chars} characters")
    return "\n".join(lines)


class InboxLabel(BaseModel):
    id: int
    sentiment: Literal["positive", "neutral", "negative"]
    intent: Literal["question", "complaint", "praise", "lead", "spam", "other"]


class InboxLabels(BaseModel):
    items: list[InboxLabel]


class Suggestions(BaseModel):
    replies: list[str] = Field(description="Three distinct replies in the brand's voice, shortest first")


class ContentAI:
    def __init__(self, client: anthropic.AsyncAnthropic | None = None, *, model: str | None = None):
        s = get_settings()
        if client is None:
            if not s.anthropic_api_key:
                raise AIUnavailable("Set SPARK_ANTHROPIC_API_KEY to enable AI features")
            client = anthropic.AsyncAnthropic(api_key=s.anthropic_api_key)
        self.client = client
        self.model = model or s.ai_model
        self.effort = s.ai_effort

    def _system(self, brand: Brand) -> list[dict]:
        return [
            {"type": "text", "text": SYSTEM},
            {
                "type": "text",
                "text": f"<brand_voice>\n{brand.voice_prompt()}\n</brand_voice>",
                "cache_control": {"type": "ephemeral"},
            },
        ]

    async def _parse(self, brand: Brand, prompt: str, schema: type[BaseModel], max_tokens=16000):
        try:
            resp = await self.client.beta.messages.parse(
                model=self.model,
                max_tokens=max_tokens,
                system=self._system(brand),
                messages=[{"role": "user", "content": prompt}],
                output_format=schema,
                output_config={"effort": self.effort},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except anthropic.RateLimitError as e:
            raise AIUnavailable("AI rate limit reached, try again in a minute") from e
        except anthropic.APIConnectionError as e:
            raise AIUnavailable("Could not reach the AI service") from e
        except anthropic.APIStatusError as e:
            log.warning("Anthropic API error: %s", e)
            raise AIUnavailable(f"AI request failed ({e.status_code})") from e
        if resp.stop_reason == "refusal":
            raise AIUnavailable("The AI declined this request; try rephrasing the brief")
        if resp.parsed_output is None:
            raise AIUnavailable("The AI returned an unexpected response")
        return resp.parsed_output

    async def generate(
        self,
        brand: Brand,
        brief: str,
        platforms: list[str],
        *,
        source_text: str | None = None,
        link: str | None = None,
        variants: int = 1,
    ) -> list[PostDraft]:
        prompt = [
            f"Write {variants} post variant(s) for EACH of these platforms:",
            _limits_text(platforms),
            f"\n<brief>\n{brief}\n</brief>",
        ]
        if source_text:
            prompt.append(f"<source_material>\n{source_text[:20000]}\n</source_material>")
        if link:
            prompt.append(f"The post will link to: {link} (the link is added automatically).")
        prompt.append(
            "Adapt length, tone and format to each platform. Count characters carefully; "
            "the text including hashtags must fit the limit."
        )
        return (await self._parse(brand, "\n".join(prompt), Drafts)).drafts

    async def classify_inbox(self, brand: Brand, items: list[dict]) -> list[dict]:
        """Sentiment and intent for inbox items [{id, kind, text, rating}] with the fast model."""
        lines = "\n".join(f"- id {i['id']} ({i.get('kind')}{', ' + str(i['rating']) + ' stars' if i.get('rating') else ''}): {str(i.get('text') or '')[:600]!r}" for i in items)
        prompt = ("Label each inbox item for the brand's social team. sentiment: positive, neutral or negative. intent: question (wants an "
                  "answer), complaint (unhappy, wants something fixed), praise, lead (wants to buy, book or work together), spam, or other. "
                  "Return one label per id.\n\n" + lines)
        out = await self._parse(brand, prompt, InboxLabels, max_tokens=4000)
        return [lab.model_dump() for lab in out.items]

    async def suggest_replies(self, brand: Brand, item: dict, thread: list[dict]) -> list[str]:
        """Three replies the team can send as they are, in the brand's voice."""
        context = "\n".join(f"[{t['direction']}] {t['author']}: {t['text']}" for t in thread if t.get("text"))
        prompt = (f"Someone wrote to {brand.name} ({item.get('kind')}" + (f", {item['rating']} stars" if item.get("rating") else "") + ").\n"
                  + (f"On the post: {item['post']}\n" if item.get("post") else "")
                  + (f"Thread so far:\n{context}\n" if context else "")
                  + f"The message to answer, from {item.get('author')}: {item.get('text')!r}\n"
                  + (f"It reads as {item.get('sentiment')} and a {item.get('intent')}.\n" if item.get("intent") else "")
                  + "Write three different replies in the brand's voice: one short and warm, one that answers fully, one that moves the "
                    "conversation forward (a question, an offer, a link if the brand has one). Keep each under 280 characters, no hashtags, "
                    "no emoji unless the brand's examples use them. If the message is spam, make the first reply an empty string.")
        out = await self._parse(brand, prompt, Suggestions, max_tokens=2000)
        return out.replies[:3]

    async def describe_image(self, brand: Brand, data: bytes, content_type: str) -> str:
        """Alt text for an image: what is in it, in one or two plain sentences, under 125 characters."""
        import base64

        try:
            resp = await self.client.messages.create(
                model=self.model, max_tokens=200, system=self._system(brand),
                messages=[{"role": "user", "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": content_type, "data": base64.b64encode(data).decode()}},
                    {"type": "text", "text": "Write alt text for this image for a social post: what is shown, who or what matters, "
                                             "no 'image of', no hashtags, under 125 characters. Answer with the alt text only."},
                ]}],
            )
        except anthropic.RateLimitError as e:
            raise AIUnavailable("AI rate limit reached, try again in a minute") from e
        except anthropic.APIConnectionError as e:
            raise AIUnavailable("Could not reach the AI service") from e
        except anthropic.APIStatusError as e:
            raise AIUnavailable(f"AI request failed ({e.status_code})") from e
        text = "".join(getattr(b, "text", "") for b in resp.content).strip().strip('"')
        if not text:
            raise AIUnavailable("The AI returned no description")
        return text[:300]

    async def rewrite(self, brand: Brand, text: str, instruction: str, platform: str | None = None):
        limits = _limits_text([platform]) if platform else ""
        prompt = (
            f"Rewrite this post. Instruction: {instruction}\n{limits}\n\n<post>\n{text}\n</post>\n"
            "Return only the rewritten post text."
        )
        return (await self._parse(brand, prompt, Rewrite, max_tokens=4000)).text

    async def hashtags(self, brand: Brand, text: str, count: int = 8) -> list[str]:
        prompt = (
            f"Suggest {count} relevant, non-spammy hashtags for this post, most specific first. "
            f"No '#' prefix.\n\n<post>\n{text}\n</post>"
        )
        return (await self._parse(brand, prompt, Hashtags, max_tokens=1000)).hashtags

    async def plan_campaign(
        self,
        brand: Brand,
        goal: str,
        start: date,
        end: date,
        platforms: list[str],
        posts_per_week: int = 3,
    ) -> CampaignPlan:
        prompt = (
            f"Plan a social media campaign from {start.isoformat()} to {end.isoformat()}.\n"
            f"Goal: {goal}\nAbout {posts_per_week} posts per week, spread across:\n"
            f"{_limits_text(platforms)}\n"
            "Vary formats and angles (education, proof, behind the scenes, offer, engagement). "
            "Each planned post gets a date inside the range, a theme, ready-to-publish text that "
            "fits the strictest of its platforms, and the platforms it goes to."
        )
        return await self._parse(brand, prompt, CampaignPlan)

    async def email(self, brand: Brand, brief: str) -> EmailDraft:
        prompt = (
            "Write a marketing email.\n"
            f"<brief>\n{brief}\n</brief>\n"
            "Keep it scannable: short paragraphs, one clear call to action as a styled link button. "
            "Use only inline styles. Do not include an unsubscribe link (it is added automatically)."
        )
        return await self._parse(brand, prompt, EmailDraft)
