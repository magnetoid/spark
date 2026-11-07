"""Phase 1 of v3: adapter capabilities, Zernio link handling, link shortening everywhere,
SSRF-safe page fetching and the shared post service used by the web UI, API and MCP."""

from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx
from sqlalchemy import select

from spark.models import Brand, PostStatus, SocialAccount, User
from spark.platforms import PublishPayload, get_adapter
from spark.platforms.zernio import ZernioAdapter

# ---- adapter capabilities ---------------------------------------------------------------

def test_adapter_capabilities_match_what_each_adapter_sends():
    # Zernio: first comment and threads only where its API has a field for them
    assert get_adapter("linkedin", provider="zernio").supports_first_comment is True
    assert get_adapter("linkedin", provider="zernio").supports_thread is False
    assert get_adapter("mastodon", provider="zernio").supports_first_comment is False
    assert get_adapter("mastodon", provider="zernio").supports_thread is False
    assert get_adapter("x", provider="zernio").supports_thread is True
    # direct adapters that post replies themselves
    assert get_adapter("x").supports_first_comment and get_adapter("x").supports_thread
    assert get_adapter("mastodon").supports_thread is True
    assert get_adapter("bluesky").supports_first_comment is True
    # the direct Threads adapter never posts a reply, so the composer must not offer one
    assert get_adapter("threads").supports_first_comment is False
    # dry run can do everything, so tests and demos exercise both features
    assert get_adapter("dry_run").supports_first_comment and get_adapter("dry_run").supports_thread


@respx.mock
async def test_zernio_puts_the_link_in_the_text_for_facebook_and_linkedin(monkeypatch):
    from spark.config import get_settings

    monkeypatch.setattr(get_settings(), "zernio_api_key", "sk_test")
    route = respx.post("https://zernio.com/api/v1/posts").mock(
        return_value=httpx.Response(201, json={"post": {"_id": "p1", "platforms": [{"status": "published"}]}}))
    for platform in ("linkedin", "facebook"):
        acc = SocialAccount(id=1, brand_id=1, platform=platform, provider="zernio", external_id="a", handle="h", extra={})
        await ZernioAdapter.for_platform(platform, httpx.AsyncClient()).publish(
            acc, PublishPayload(text="Read this", media=[], link="https://example.com/post"))
        sent = route.calls.last.request.content.decode()
        assert "https://example.com/post" in sent, platform


# ---- page fetching (SSRF) ---------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "http://127.0.0.1:8000/admin", "http://localhost/", "http://169.254.169.254/latest/meta-data",
    "http://10.0.0.5/", "http://[::1]/", "file:///etc/passwd", "ftp://example.com/x", "not a url",
])
async def test_fetch_page_text_refuses_private_and_non_http_urls(url):
    from spark.services.fetch import fetch_page_text

    with respx.mock(assert_all_called=False) as mock:
        mock.route().mock(return_value=httpx.Response(200, text="<p>secret</p>"))
        assert await fetch_page_text(url) is None
        assert not mock.calls


@respx.mock
async def test_fetch_page_text_reads_public_pages_but_not_redirects_to_private_hosts():
    from spark.services.fetch import fetch_page_text

    respx.get("https://example.com/article").mock(return_value=httpx.Response(
        200, text="<html><nav>menu</nav><p>Hello <b>world</b></p><script>x()</script></html>"))
    respx.get("https://example.com/redirect").mock(return_value=httpx.Response(
        302, headers={"Location": "http://127.0.0.1:6379/"}))
    inner = respx.get("http://127.0.0.1:6379/").mock(return_value=httpx.Response(200, text="PONG"))
    assert await fetch_page_text("https://example.com/article") == "Hello world"
    assert await fetch_page_text("https://example.com/redirect") is None
    assert not inner.called


# ---- the shared post service ------------------------------------------------------------

async def _owner(db) -> User:
    return await db.scalar(select(User))


async def test_save_post_shortens_links_in_every_text_field(db, brand):
    from spark.services import posts as svc

    brand.auto_shorten_links = True
    await db.commit()
    acc = await db.scalar(select(SocialAccount))
    post = await svc.save_post(
        db, brand, await _owner(db), None,
        content="Main https://example.com/a", link=None, media_ids=[], campaign_id=None, notes=None,
        source="manual",
        targets=[svc.TargetInput(account_id=acc.id, override="Override https://example.com/b",
                                 first_comment="More at https://example.com/c",
                                 thread=["Part two https://example.com/d", "plain"])],
    )
    t = post.targets[0]
    for text in (post.content, t.content_override, t.first_comment, t.thread[0]):
        assert "example.com" not in text and "/l/" in text, text
    assert t.thread[1] == "plain"


async def test_save_post_ignores_accounts_of_other_brands_and_resets_failed_targets(db, brand):
    from spark.services import posts as svc

    other = Brand(name="Other", slug="other")
    db.add(other)
    await db.flush()
    foreign = SocialAccount(brand_id=other.id, platform="dry_run", external_id="x", handle="x")
    db.add(foreign)
    await db.commit()
    acc = await db.scalar(select(SocialAccount).where(SocialAccount.brand_id == brand.id))
    user = await _owner(db)
    post = await svc.save_post(db, brand, user, None, content="Hi", link=None, media_ids=[], campaign_id=None,
                               notes=None, source="manual",
                               targets=[svc.TargetInput(account_id=acc.id), svc.TargetInput(account_id=foreign.id)])
    assert [t.account_id for t in post.targets] == [acc.id]
    post.targets[0].status = PostStatus.failed
    await db.commit()
    post = await svc.save_post(db, brand, user, post, content="Hi again", link=None, media_ids=[], campaign_id=None,
                               notes=None, source="manual", targets=[svc.TargetInput(account_id=acc.id)])
    assert post.targets[0].status == PostStatus.draft and post.content == "Hi again"


async def test_place_post_actions_and_errors(db, brand):
    from spark.models import QueueSlot
    from spark.services import posts as svc

    db.add(QueueSlot(brand_id=brand.id, weekday=0, time="09:00"))
    await db.commit()
    acc = await db.scalar(select(SocialAccount))
    user = await _owner(db)
    post = await svc.save_post(db, brand, user, None, content="Hello", link=None, media_ids=[], campaign_id=None,
                               notes=None, source="manual", targets=[svc.TargetInput(account_id=acc.id)])
    assert await svc.place_post(db, brand, user, post, "draft", None) == "Draft saved"
    assert post.status == PostStatus.draft
    msg = await svc.place_post(db, brand, user, post, "queue", None)
    assert msg.startswith("Queued for") and post.status == PostStatus.scheduled
    when = datetime.now(UTC) + timedelta(days=1)
    assert await svc.place_post(db, brand, user, post, "schedule", when) == "Scheduled"
    assert post.scheduled_at == when
    with pytest.raises(svc.PlaceError) as e:
        await svc.place_post(db, brand, user, post, "schedule", None)
    assert "date and time" in e.value.problems[0]
    with pytest.raises(svc.PlaceError):
        await svc.place_post(db, brand, user, post, "bogus", None)
    empty = await svc.save_post(db, brand, user, None, content="No channels", link=None, media_ids=[],
                                campaign_id=None, notes=None, source="manual", targets=[])
    with pytest.raises(svc.PlaceError) as e:
        await svc.place_post(db, brand, user, empty, "queue", None)
    assert "at least one" in e.value.problems[0]
    # the post that failed validation is left as a draft, not half-scheduled
    assert empty.status == PostStatus.draft


async def test_place_post_marks_editor_posts_pending_when_brand_requires_approval(db, brand):
    from spark.models import Role
    from spark.services import posts as svc

    brand.require_approval = True
    editor_user = User(email="ed@example.com", name="Ed", role=Role.editor, password_hash="x")
    db.add(editor_user)
    await db.commit()
    acc = await db.scalar(select(SocialAccount))
    post = await svc.save_post(db, brand, editor_user, None, content="Approve me", link=None, media_ids=[],
                               campaign_id=None, notes=None, source="manual",
                               targets=[svc.TargetInput(account_id=acc.id)])
    msg = await svc.place_post(db, brand, editor_user, post, "now", None)
    assert post.status == PostStatus.pending_approval and "approval" in msg


async def test_retry_and_duplicate_helpers(db, brand):
    from spark.services import posts as svc

    acc = await db.scalar(select(SocialAccount))
    user = await _owner(db)
    post = await svc.save_post(db, brand, user, None, content="Retry me", link="https://example.com", media_ids=[],
                               campaign_id=None, notes=None, source="manual",
                               targets=[svc.TargetInput(account_id=acc.id, first_comment="fc", thread=["t1"])])
    post.targets[0].status = PostStatus.failed
    post.targets[0].attempts = 3
    post.refresh_status()
    await db.commit()
    assert svc.retry_failed(post) == 1
    assert post.targets[0].status == PostStatus.scheduled and post.targets[0].attempts == 0
    assert svc.retry_failed(post) == 0
    copy = await svc.duplicate_post(db, brand, user, post)
    assert copy.id != post.id and copy.status == PostStatus.draft and copy.content == "Retry me"
    assert copy.targets[0].first_comment == "fc" and copy.targets[0].thread == ["t1"]
    assert copy.targets[0].status == PostStatus.draft


async def test_api_tokens_live_in_a_service(db, brand):
    from spark.services import tokens

    user = await _owner(db)
    raw, row = await tokens.create_token(db, user, "Claude Code")
    assert raw.startswith(tokens.TOKEN_PREFIX) and row.token_hash == tokens.hash_token(raw) and raw not in row.prefix + "x" * 0
    assert (await tokens.user_for_token(db, raw)).id == user.id
    assert await tokens.user_for_token(db, "spk_nope") is None
    assert await tokens.user_for_token(db, None) is None


async def test_post_is_scheduled_now_enqueues_publish(db, brand, monkeypatch):
    """`now` through the service enqueues a publish job for each scheduled target."""
    from spark.services import jobs
    from spark.services import posts as svc

    calls = []

    async def fake_enqueue(job, *args):
        calls.append((job, args))
        return True

    monkeypatch.setattr(jobs, "enqueue", fake_enqueue)
    acc = await db.scalar(select(SocialAccount))
    user = await _owner(db)
    post = await svc.save_post(db, brand, user, None, content="Go", link=None, media_ids=[], campaign_id=None,
                               notes=None, source="manual", targets=[svc.TargetInput(account_id=acc.id)])
    await svc.place_post(db, brand, user, post, "now", None)
    await db.commit()
    await svc.enqueue_due(post)
    assert calls == [("publish_now", (post.targets[0].id,))]
