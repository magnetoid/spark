import os
import re
import tempfile
from pathlib import Path

import pytest

# Settings are read at import time; set env before importing spark.
_tmp = tempfile.mkdtemp(prefix="spark-test-")
os.environ.update(
    SPARK_DATABASE_URL=f"sqlite+aiosqlite:///{_tmp}/test.db",
    SPARK_MEDIA_DIR=f"{_tmp}/media",
    SPARK_SECRET_KEY="test-secret",
    SPARK_BASE_URL="http://testserver",
    SPARK_FORCE_DRY_RUN="false",
    SPARK_EMAIL_BACKEND="console",
    SPARK_ANTHROPIC_API_KEY="",
    SPARK_ZERNIO_API_KEY="",
)
Path(f"{_tmp}/media").mkdir(parents=True, exist_ok=True)

from httpx import ASGITransport, AsyncClient  # noqa: E402

from spark.db import Base, SessionLocal, engine  # noqa: E402
from spark.main import app  # noqa: E402
from spark.models import Brand, Role, SocialAccount, User  # noqa: E402
from spark.security import hash_password  # noqa: E402


@pytest.fixture(autouse=True)
async def fresh_db():
    import spark.models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield


@pytest.fixture
async def db():
    async with SessionLocal() as s:
        yield s


@pytest.fixture
async def brand(db):
    owner = User(email="owner@example.com", name="Owner", role=Role.owner,
                 password_hash=hash_password("password123"))
    b = Brand(name="Acme", slug="acme", timezone="UTC")
    db.add_all([owner, b])
    await db.flush()
    acc = SocialAccount(brand_id=b.id, platform="dry_run", external_id="dry-acme", handle="acme")
    acc.access_token = "tok"
    db.add(acc)
    await db.commit()
    return b


@pytest.fixture
async def client(brand):
    from spark import main as m

    m._buckets.clear()  # each test gets a fresh rate-limit window
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver",
                           follow_redirects=False) as c:
        # CSRF: the token is minted on first render; send it as a header like htmx does
        page = await c.get("/login")
        token = re.search(r'name="csrf" content="([^"]+)"', page.text).group(1)
        c.headers["X-CSRF-Token"] = token
        r = await c.post("/login", data={"email": "owner@example.com", "password": "password123"})
        assert r.status_code == 303, r.text
        page = await c.get("/")  # session was rotated on login: refresh the token
        c.headers["X-CSRF-Token"] = re.search(r'name="csrf" content="([^"]+)"', page.text).group(1)
        yield c
