"""Two-factor sign-in: authenticator codes (RFC 6238), recovery codes, and the workspace rule."""

import time

from spark.models import Role, User
from spark.security import hash_password
from tests.api.conftest import API

RFC_SECRET = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # base32 of "12345678901234567890"
OWNER = {"email": "owner@example.com", "password": "password123"}


def _code(secret: str, shift: int = 0) -> str:
    from spark.services import twofactor

    return twofactor.code_at(secret, time.time() + shift * 30)


async def _turn_on(client, password: str = "password123") -> tuple[str, list[str]]:
    """Set up and confirm two-factor for the signed-in user. Returns the secret and the codes."""
    r = await client.post(f"{API}/me/two-factor/setup", json={"password": password})
    assert r.status_code == 200, r.text
    secret = r.json()["secret"]
    r = await client.post(f"{API}/me/two-factor/enable", json={"code": _code(secret)})
    assert r.status_code == 200, r.text
    return secret, r.json()["recovery_codes"]


async def _member(db, email="ed@example.com", role=Role.editor) -> User:
    u = User(email=email, name="Ed", role=role, password_hash=hash_password("password456"))
    db.add(u)
    await db.commit()
    return u


async def _sign_in(client, email="ed@example.com", password="password456", code=None):
    body = {"email": email, "password": password} | ({"code": code} if code else {})
    r = await client.post(f"{API}/auth/login", json=body)
    if r.status_code == 200:
        client.headers["X-CSRF-Token"] = r.json()["csrf_token"]
    return r


# ---- the algorithm ---------------------------------------------------------------------------
def test_codes_match_the_rfc_6238_test_vectors():
    from spark.services import twofactor

    assert twofactor.code_at(RFC_SECRET, 59) == "287082"
    assert twofactor.code_at(RFC_SECRET, 1111111109) == "081804"


def test_the_authenticator_link_names_spark_and_the_account():
    from spark.services import twofactor

    uri = twofactor.otpauth_uri(RFC_SECRET, "ana@example.com")
    assert uri.startswith("otpauth://totp/Spark:ana%40example.com?")
    assert f"secret={RFC_SECRET}" in uri and "issuer=Spark" in uri


# ---- turning it on ---------------------------------------------------------------------------
async def test_setup_needs_the_password(api):
    r = await api.post(f"{API}/me/two-factor/setup", json={"password": "nope"})
    assert r.status_code == 400 and r.json()["code"] == "wrong_password"


async def test_setup_alone_does_not_turn_it_on(api):
    r = await api.post(f"{API}/me/two-factor/setup", json={"password": "password123"})
    assert r.status_code == 200
    assert len(r.json()["secret"]) == 32 and r.json()["otpauth_uri"].startswith("otpauth://totp/")
    assert (await api.get(f"{API}/me")).json()["two_factor"] is False


async def test_a_wrong_code_does_not_turn_it_on(api):
    await api.post(f"{API}/me/two-factor/setup", json={"password": "password123"})
    r = await api.post(f"{API}/me/two-factor/enable", json={"code": "000000"})
    assert r.status_code == 400 and r.json()["code"] == "invalid_code"
    assert (await api.get(f"{API}/me")).json()["two_factor"] is False


async def test_the_right_code_turns_it_on_and_shows_recovery_codes(api):
    _, codes = await _turn_on(api)
    assert len(codes) == 10 and len(set(codes)) == 10
    me = (await api.get(f"{API}/me")).json()
    assert me["two_factor"] is True and me["recovery_codes_left"] == 10


async def test_the_secret_is_not_stored_in_clear_text(api, db):
    secret, codes = await _turn_on(api)
    u = (await db.execute(User.__table__.select())).mappings().one()
    assert secret not in (u["totp_secret"] or "")
    assert not set(codes) & set(u["recovery_codes"])


# ---- signing in ------------------------------------------------------------------------------
async def test_sign_in_asks_for_a_code_once_two_factor_is_on(api, anon):
    await _turn_on(api)
    r = await _sign_in(anon, **OWNER)
    assert r.status_code == 401 and r.json()["code"] == "two_factor_required"
    assert (await anon.get(f"{API}/session")).json()["user"] is None


async def test_a_wrong_code_does_not_sign_in(api, anon):
    await _turn_on(api)
    r = await _sign_in(anon, **OWNER, code="000000")
    assert r.status_code == 401 and r.json()["code"] == "invalid_code"


async def test_the_next_code_signs_in(api, anon):
    secret, _ = await _turn_on(api)
    r = await _sign_in(anon, **OWNER, code=_code(secret, 1))
    assert r.status_code == 200 and r.json()["user"]["email"] == "owner@example.com"


async def test_a_code_works_only_once(api, anon):
    secret, _ = await _turn_on(api)
    code = _code(secret, 1)
    assert (await _sign_in(anon, **OWNER, code=code)).status_code == 200
    again = await _sign_in(anon, **OWNER, code=code)
    assert again.status_code == 401 and again.json()["code"] == "invalid_code"


async def test_a_recovery_code_signs_in_once(api, anon):
    _, codes = await _turn_on(api)
    r = await _sign_in(anon, **OWNER, code=codes[0].upper().replace("-", " "))
    assert r.status_code == 200
    assert r.json()["user"]["recovery_codes_left"] == 9
    again = await _sign_in(anon, **OWNER, code=codes[0])
    assert again.status_code == 401 and again.json()["code"] == "invalid_code"


async def test_five_wrong_codes_pause_the_code_step(api, anon):
    secret, _ = await _turn_on(api)
    for _ in range(5):
        assert (await _sign_in(anon, **OWNER, code="000000")).status_code == 401
    r = await _sign_in(anon, **OWNER, code=_code(secret, 1))
    assert r.status_code == 429 and r.json()["code"] == "too_many_attempts"


# ---- turning it off, new recovery codes ------------------------------------------------------
async def test_turning_it_off_needs_the_password_and_a_code(api, anon):
    secret, _ = await _turn_on(api)
    r = await api.post(
        f"{API}/me/two-factor/disable", json={"password": "nope", "code": _code(secret, 1)}
    )
    assert r.status_code == 400 and r.json()["code"] == "wrong_password"
    r = await api.post(
        f"{API}/me/two-factor/disable", json={"password": "password123", "code": "000000"}
    )
    assert r.status_code == 400 and r.json()["code"] == "invalid_code"
    r = await api.post(
        f"{API}/me/two-factor/disable", json={"password": "password123", "code": _code(secret, 1)}
    )
    assert r.status_code == 200 and r.json()["two_factor"] is False
    assert (await _sign_in(anon, **OWNER)).status_code == 200


async def test_new_recovery_codes_replace_the_old_ones(api, anon):
    _, old = await _turn_on(api)
    r = await api.post(f"{API}/me/two-factor/recovery-codes", json={"password": "password123"})
    assert r.status_code == 200
    new = r.json()["recovery_codes"]
    assert len(new) == 10 and not set(new) & set(old)
    assert (await _sign_in(anon, **OWNER, code=old[0])).status_code == 401
    assert (await _sign_in(anon, **OWNER, code=new[0])).status_code == 200


# ---- the team --------------------------------------------------------------------------------
async def test_the_team_list_shows_who_has_two_factor(api, db):
    await _member(db)
    await _turn_on(api)
    rows = {m["email"]: m["two_factor"] for m in (await api.get(f"{API}/team")).json()}
    assert rows == {"owner@example.com": True, "ed@example.com": False}


async def test_an_owner_turns_off_a_members_two_factor(api, anon, db):
    ed = await _member(db)
    assert (await _sign_in(anon)).status_code == 200
    await _turn_on(anon, "password456")
    assert (await anon.delete(f"{API}/team/{ed.id}/two-factor")).status_code == 403
    assert (await api.delete(f"{API}/team/{ed.id}/two-factor")).status_code == 204
    out = await anon.post(f"{API}/auth/logout")
    anon.headers["X-CSRF-Token"] = out.json()["csrf_token"]  # signing out starts a new session
    assert (await _sign_in(anon)).status_code == 200  # no code asked any more


async def test_an_owner_cannot_skip_their_own_code_through_the_team_route(api, db):
    await _turn_on(api)
    owner = (await api.get(f"{API}/me")).json()
    r = await api.delete(f"{API}/team/{owner['id']}/two-factor")
    assert r.status_code == 409 and r.json()["code"] == "self"


async def test_reset_from_the_server_clears_everything(api, db):
    from spark.services import twofactor

    await _turn_on(api)
    assert await twofactor.reset_by_email(db, "Owner@Example.com") is True
    me = (await api.get(f"{API}/me")).json()
    assert me["two_factor"] is False and me["recovery_codes_left"] == 0
    assert await twofactor.reset_by_email(db, "nobody@example.com") is False


# ---- required for the whole workspace --------------------------------------------------------
async def test_an_owner_without_two_factor_cannot_require_it(api):
    r = await api.put(f"{API}/settings/security", json={"require_two_factor": True})
    assert r.status_code == 409 and r.json()["code"] == "two_factor_first"
    assert (await api.get(f"{API}/settings/security")).json() == {"require_two_factor": False}


async def test_the_session_says_whether_the_workspace_requires_two_factor(api, anon):
    assert (await api.get(f"{API}/session")).json()["features"]["require_two_factor"] is False
    await _turn_on(api)
    await api.put(f"{API}/settings/security", json={"require_two_factor": True})
    assert (await api.get(f"{API}/session")).json()["features"]["require_two_factor"] is True
    # nobody signed in: the rule is not anyone else's business
    assert (await anon.get(f"{API}/session")).json()["features"]["require_two_factor"] is False


async def test_requiring_two_factor_stops_members_until_they_set_it_up(api, anon, db):
    await _member(db)
    await _turn_on(api)
    r = await api.put(f"{API}/settings/security", json={"require_two_factor": True})
    assert r.status_code == 200 and r.json() == {"require_two_factor": True}

    s = await _sign_in(anon)
    assert s.status_code == 200 and s.json()["two_factor_setup_required"] is True
    blocked = await anon.get(f"{API}/brands")
    assert blocked.status_code == 403 and blocked.json()["code"] == "two_factor_setup_required"

    await _turn_on(anon, "password456")  # the way out stays open
    assert (await anon.get(f"{API}/session")).json()["two_factor_setup_required"] is False
    assert (await anon.get(f"{API}/brands")).status_code == 200


async def test_api_tokens_keep_working_when_two_factor_is_required(api, anon, db):
    from spark.services import tokens

    ed = await _member(db)
    raw, _ = await tokens.create_token(db, ed, "script")
    await _turn_on(api)
    await api.put(f"{API}/settings/security", json={"require_two_factor": True})
    r = await anon.get(f"{API}/brands", headers={"Authorization": f"Bearer {raw}"})
    assert r.status_code == 200


async def test_only_owners_change_the_rule(anon, db):
    await _member(db)
    await _sign_in(anon)
    r = await anon.put(f"{API}/settings/security", json={"require_two_factor": True})
    assert r.status_code == 403
