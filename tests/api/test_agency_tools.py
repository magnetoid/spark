"""Phase 3B-1: an overview of every client, approval deadlines with a reminder and a rule for what
happens after them (never publishing), and copying one brand's setup to another."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from spark.models import (
    ActivityLog,
    Brand,
    BrandMember,
    ContentPillar,
    HashtagGroup,
    InboxItem,
    Post,
    PostStatus,
    PostTarget,
    PostTemplate,
    QueueSlot,
    Role,
    SavedReply,
    SocialAccount,
    User,
)
from spark.security import hash_password
from spark.services import approvals
from spark.services.email import ConsoleSender
from tests.api.conftest import API


async def _acc(db, brand) -> SocialAccount:
    return await db.scalar(select(SocialAccount).where(SocialAccount.brand_id == brand.id))


async def _post(db, acc, status: PostStatus, when: datetime | None, **kw) -> Post:
    p = Post(
        brand_id=acc.brand_id, content="Boots are back", status=status, scheduled_at=when, **kw
    )
    p.targets = [PostTarget(account_id=acc.id, status=status, scheduled_at=when)]
    db.add(p)
    await db.commit()
    return p


async def _brand(db, name: str, slug: str) -> tuple[Brand, SocialAccount]:
    b = Brand(name=name, slug=slug, timezone="UTC")
    db.add(b)
    await db.flush()
    a = SocialAccount(brand_id=b.id, platform="dry_run", external_id=f"dry-{slug}", handle=slug)
    a.access_token = "tok"
    db.add(a)
    await db.commit()
    return b, a


async def _member(db, email: str, brand_id: int, role: str, global_role=Role.editor) -> User:
    u = User(
        email=email,
        name=email.split("@")[0].title(),
        role=global_role,
        password_hash=hash_password("password123"),
    )
    db.add(u)
    await db.flush()
    db.add(BrandMember(brand_id=brand_id, user_id=u.id, role=role))
    await db.commit()
    return u


# ---- all-clients overview -----------------------------------------------------------------------
async def test_overview_lists_every_brand_with_what_needs_attention(api, db, brand):
    acc = await _acc(db, brand)
    now = datetime.now(UTC)
    await _post(db, acc, PostStatus.failed, now - timedelta(hours=2))
    await _post(db, acc, PostStatus.pending_approval, now + timedelta(days=1))
    await _post(db, acc, PostStatus.scheduled, now + timedelta(days=2))
    db.add(
        InboxItem(
            account_id=acc.id,
            brand_id=brand.id,
            kind="comment",
            external_id="c1",
            text="Love it",
            author_name="Ana",
        )
    )
    acc.extra = {"needs_reconnection": True}
    other, _ = await _brand(db, "Beta", "beta")
    r = await api.get(f"{API}/overview")
    assert r.status_code == 200, r.text
    rows = {b["name"]: b for b in r.json()["brands"]}
    assert set(rows) == {"Acme", "Beta"}
    a = rows["Acme"]
    assert a["failed"] == 1 and a["approvals"] == 1 and a["channels"] == 1 and a["replies"] == 1
    assert a["scheduled_week"] == 2
    assert 0 <= a["empty_days"] <= 6  # two of the next seven days have a post
    assert a["next_post_at"] is not None
    assert rows["Beta"]["empty_days"] == 7 and rows["Beta"]["next_post_at"] is None
    assert r.json()["brands"][0]["name"] == "Acme"  # the brand with problems comes first
    assert r.json()["totals"]["failed"] == 1


async def test_overview_shows_only_brands_the_person_can_see(api, db, brand):
    other, _ = await _brand(db, "Beta", "beta")
    user = await db.scalar(select(User).where(User.email == "owner@example.com"))
    user.role = Role.editor
    db.add(BrandMember(brand_id=other.id, user_id=user.id, role="editor"))
    await db.commit()
    r = await api.get(f"{API}/overview")
    assert [b["name"] for b in r.json()["brands"]] == ["Beta"]
    assert r.json()["brands"][0]["role"] == "editor"


async def test_overview_counts_overdue_approvals(api, db, brand):
    acc = await _acc(db, brand)
    now = datetime.now(UTC)
    await _post(
        db,
        acc,
        PostStatus.pending_approval,
        now + timedelta(days=1),
        approval_due_at=now - timedelta(minutes=5),
    )
    await _post(db, acc, PostStatus.pending_approval, now - timedelta(hours=1))  # time passed
    await _post(db, acc, PostStatus.pending_approval, now + timedelta(days=3))
    r = await api.get(f"{API}/overview")
    assert r.json()["brands"][0]["approvals"] == 3
    assert r.json()["brands"][0]["approvals_overdue"] == 2


# ---- approval deadlines -------------------------------------------------------------------------
async def test_brand_approval_rule_is_saved(api, db, brand):
    r = await api.patch(
        f"{API}/brands/{brand.id}", json={"approval_lead_hours": 24, "approval_timeout": "drafts"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["approval_lead_hours"] == 24 and r.json()["approval_timeout"] == "drafts"
    r = await api.patch(f"{API}/brands/{brand.id}", json={"approval_timeout": "publish"})
    assert r.status_code == 422  # there is no rule that publishes without approval


async def test_request_for_approval_gets_a_due_date(api, db, brand):
    brand.require_approval = True
    brand.approval_lead_hours = 24
    user = await db.scalar(select(User))
    user.role = Role.editor
    db.add(BrandMember(brand_id=brand.id, user_id=user.id, role="editor"))
    await db.commit()
    acc = await _acc(db, brand)
    when = datetime.now(UTC).replace(microsecond=0) + timedelta(days=3)
    r = await api.post(
        f"{API}/brands/{brand.id}/posts",
        json={
            "content": "Boots",
            "targets": [{"account_id": acc.id}],
            "action": "schedule",
            "scheduled_at": when.isoformat(),
        },
    )
    post = r.json()["post"]
    assert post["status"] == "pending_approval", r.text
    due = datetime.fromisoformat(post["approval_due_at"])
    assert due == when - timedelta(hours=24)


def test_due_date_is_never_in_the_past_nor_after_the_post():
    brand = Brand(name="A", slug="a", approval_lead_hours=24)
    now = datetime(2026, 11, 15, 12, tzinfo=UTC)
    soon = Post(scheduled_at=now + timedelta(hours=5))
    assert approvals.due_for(soon, brand, now) == now + timedelta(hours=1)
    very_soon = Post(scheduled_at=now + timedelta(minutes=20))
    assert approvals.due_for(very_soon, brand, now) == now + timedelta(minutes=20)
    assert approvals.due_for(Post(scheduled_at=None), brand, now) is None
    assert approvals.due_for(soon, Brand(name="B", slug="b"), now) is None  # no rule


async def test_reminder_goes_out_once_before_the_deadline(db, brand):
    ConsoleSender.sent.clear()
    brand.approval_lead_hours = 24
    acc = await _acc(db, brand)
    now = datetime(2026, 11, 15, 12, tzinfo=UTC)
    post = await _post(
        db,
        acc,
        PostStatus.pending_approval,
        now + timedelta(days=2),
        approval_due_at=now + timedelta(hours=3),
    )
    sender = ConsoleSender()
    assert await approvals.run(db, sender, now - timedelta(hours=5)) == 0  # too early
    assert await approvals.run(db, sender, now) == 1
    assert await approvals.run(db, sender, now + timedelta(minutes=30)) == 0  # only once
    mail = ConsoleSender.sent[-1]
    assert mail["to"] == "owner@example.com" and "Approval due" in mail["subject"]
    await db.refresh(post)
    assert post.approval_reminded_at is not None and post.status == PostStatus.pending_approval


async def test_after_the_deadline_wait_rule_keeps_the_post_waiting(db, brand):
    brand.approval_lead_hours = 24
    brand.approval_timeout = "wait"
    acc = await _acc(db, brand)
    now = datetime(2026, 11, 15, 12, tzinfo=UTC)
    post = await _post(
        db,
        acc,
        PostStatus.pending_approval,
        now + timedelta(hours=10),
        approval_due_at=now - timedelta(minutes=1),
    )
    await approvals.run(db, ConsoleSender(), now)
    await db.refresh(post)
    assert post.status == PostStatus.pending_approval
    assert post.targets[0].status == PostStatus.pending_approval


async def test_after_the_deadline_drafts_rule_moves_it_to_drafts_and_tells_the_author(db, brand):
    ConsoleSender.sent.clear()
    brand.approval_lead_hours = 24
    brand.approval_timeout = "drafts"
    acc = await _acc(db, brand)
    author = await _member(db, "ed@example.com", brand.id, "editor")
    now = datetime(2026, 11, 15, 12, tzinfo=UTC)
    post = await _post(
        db,
        acc,
        PostStatus.pending_approval,
        now + timedelta(hours=10),
        approval_due_at=now - timedelta(minutes=1),
        author_id=author.id,
    )
    await approvals.run(db, ConsoleSender(), now)
    await db.refresh(post)
    assert post.status == PostStatus.draft and post.targets[0].status == PostStatus.draft
    assert any(
        m["to"] == "ed@example.com" and "moved to drafts" in m["subject"]
        for m in ConsoleSender.sent
    )
    log = await db.scalar(select(ActivityLog).where(ActivityLog.object_id == post.id))
    assert log is not None and "approval" in log.summary.lower()


async def test_a_deadline_never_publishes(db, brand):
    for rule in ("wait", "drafts"):
        brand.approval_lead_hours = 1
        brand.approval_timeout = rule
        acc = await _acc(db, brand)
        now = datetime(2026, 11, 15, 12, tzinfo=UTC)
        post = await _post(
            db,
            acc,
            PostStatus.pending_approval,
            now - timedelta(minutes=5),
            approval_due_at=now - timedelta(hours=1),
        )
        await approvals.run(db, ConsoleSender(), now)
        await db.refresh(post)
        assert post.status not in (
            PostStatus.scheduled,
            PostStatus.publishing,
            PostStatus.published,
        )


async def test_waiting_posts_without_a_due_date_get_one(db, brand):
    """Posts that reach approval through RSS or evergreen recycling get their date from the job."""
    brand.approval_lead_hours = 12
    acc = await _acc(db, brand)
    now = datetime(2026, 11, 15, 12, tzinfo=UTC)
    post = await _post(db, acc, PostStatus.pending_approval, now + timedelta(days=2))
    await approvals.run(db, ConsoleSender(), now)
    await db.refresh(post)
    assert post.approval_due_at.replace(tzinfo=UTC) == now + timedelta(days=2, hours=-12)


async def test_rescheduling_resets_the_reminder(db, brand):
    from spark.services import scheduler

    brand.require_approval = True
    brand.approval_lead_hours = 24
    acc = await _acc(db, brand)
    now = datetime.now(UTC)
    post = await _post(
        db,
        acc,
        PostStatus.pending_approval,
        now + timedelta(days=2),
        approval_due_at=now,
        approval_reminded_at=now,
    )
    editor = User(email="e@example.com", name="E", role=Role.editor, password_hash="x")
    scheduler.schedule(post, now + timedelta(days=5), editor, brand, can_approve=False)
    assert post.approval_reminded_at is None
    assert abs(post.approval_due_at - (now + timedelta(days=4))) < timedelta(seconds=5)


# ---- copy setup to another brand ----------------------------------------------------------------
async def _setup_source(db, brand):
    brand.voice_tone = "Warm"
    brand.default_hashtags = "#boots"
    brand.agent_config = {"never_say": ["cheap"], "avoid_topics": ["politics"], "keywords": []}
    db.add_all(
        [
            ContentPillar(brand_id=brand.id, name="Education", target_share=40),
            ContentPillar(brand_id=brand.id, name="Product", target_share=60),
            SavedReply(brand_id=brand.id, title="Thanks", body="Thank you!"),
            PostTemplate(brand_id=brand.id, name="Tip", body="Tip: {{tip}}"),
            HashtagGroup(brand_id=brand.id, name="Core", tags=["boots", "leather"]),
            QueueSlot(brand_id=brand.id, weekday=0, time="08:15"),
            QueueSlot(brand_id=brand.id, weekday=2, time="18:45"),
        ]
    )
    acc = await _acc(db, brand)
    db.add(QueueSlot(brand_id=brand.id, weekday=1, time="10:00", account_id=acc.id))
    await db.commit()


async def test_copy_setup_to_a_new_brand(api, db, brand):
    await _setup_source(db, brand)
    r = await api.post(f"{API}/brands", json={"name": "Beta"})
    target = r.json()["id"]
    r = await api.post(
        f"{API}/brands/{target}/copy-setup",
        json={
            "from_brand_id": brand.id,
            "parts": [
                "pillars",
                "slots",
                "guardrails",
                "saved_replies",
                "templates",
                "hashtags",
                "voice",
            ],
        },
    )
    assert r.status_code == 200, r.text
    c = r.json()["copied"]
    assert c["pillars"] == 2 and c["saved_replies"] == 1 and c["templates"] == 1
    assert c["hashtags"] == 1 and c["slots"] == 2  # the channel's own slot stays behind
    names = (
        (await db.execute(select(ContentPillar.name).where(ContentPillar.brand_id == target)))
        .scalars()
        .all()
    )
    assert sorted(names) == ["Education", "Product"]
    slots = (
        (await db.execute(select(QueueSlot).where(QueueSlot.brand_id == target))).scalars().all()
    )
    assert sorted((s.weekday, s.time) for s in slots) == [(0, "08:15"), (2, "18:45")]  # replaced
    t = await db.get(Brand, target)
    await db.refresh(t)
    assert t.voice_tone == "Warm" and t.default_hashtags == "#boots"
    assert t.agent_config["never_say"] == ["cheap"]


async def test_copy_setup_twice_does_not_duplicate(api, db, brand):
    await _setup_source(db, brand)
    target = (await api.post(f"{API}/brands", json={"name": "Beta"})).json()["id"]
    body = {"from_brand_id": brand.id, "parts": ["pillars", "saved_replies", "templates"]}
    await api.post(f"{API}/brands/{target}/copy-setup", json=body)
    r = await api.post(f"{API}/brands/{target}/copy-setup", json=body)
    assert r.json()["copied"] == {"pillars": 0, "saved_replies": 0, "templates": 0}
    n = (await db.execute(select(ContentPillar).where(ContentPillar.brand_id == target))).all()
    assert len(n) == 2


async def test_copy_setup_needs_access_to_both_brands(api, db, brand):
    other, _ = await _brand(db, "Beta", "beta")
    user = await db.scalar(select(User).where(User.email == "owner@example.com"))
    user.role = Role.editor
    db.add(BrandMember(brand_id=other.id, user_id=user.id, role="owner"))
    await db.commit()
    r = await api.post(
        f"{API}/brands/{other.id}/copy-setup",
        json={"from_brand_id": brand.id, "parts": ["pillars"]},
    )
    assert r.status_code == 404  # Acme is not theirs
    r = await api.post(
        f"{API}/brands/{other.id}/copy-setup",
        json={"from_brand_id": other.id, "parts": ["pillars"]},
    )
    assert r.status_code == 422  # not onto itself


async def test_copy_setup_is_logged(api, db, brand):
    await _setup_source(db, brand)
    target = (await api.post(f"{API}/brands", json={"name": "Beta"})).json()["id"]
    await api.post(
        f"{API}/brands/{target}/copy-setup", json={"from_brand_id": brand.id, "parts": ["pillars"]}
    )
    log = await db.scalar(
        select(ActivityLog).where(
            ActivityLog.brand_id == target, ActivityLog.verb == "copied setup"
        )
    )
    assert log is not None and "Acme" in log.summary
