"""Claude-powered content generation.

Every request carries the brand voice in a cached system block, so repeated
generations for the same brand reuse the prompt cache.
"""

from __future__ import annotations

import logging
from datetime import date

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


class ContentAI:
    def __init__(self, client: anthropic.AsyncAnthropic | None = None):
        s = get_settings()
        if client is None:
            if not s.anthropic_api_key:
                raise AIUnavailable("Set SPARK_ANTHROPIC_API_KEY to enable AI features")
            client = anthropic.AsyncAnthropic(api_key=s.anthropic_api_key)
        self.client = client
        self.model = s.ai_model
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
