"""Per-user preferences: profile, notifications, composer defaults, shortcuts, password."""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.config import get_settings
from spark.db import get_db
from spark.models import Brand, User
from spark.security import hash_password, verify_password
from spark.web.deps import current_user, flash, render, require_brand

router = APIRouter()

DEFAULT_ACTIONS = [("queue", "Add to queue (next free slot)"), ("next", "Share next"),
                   ("schedule", "Pick a time"), ("draft", "Save as draft")]
DEFAULT_PREFS = {"notify_failed": True, "notify_approvals": True, "digest_weekly": True,
                 "default_action": "queue", "shortcuts": True}


def effective_prefs(user: User) -> dict:
    return {**DEFAULT_PREFS, **(user.prefs or {})}


@router.get("/me")
async def me(request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(current_user),
             brand: Brand = Depends(require_brand)):
    s = get_settings()
    return await render(request, "me.html", db, user, brand, prefs=effective_prefs(user),
                        actions=DEFAULT_ACTIONS, email_live=s.email_backend != "console")


@router.post("/me")
async def me_save(request: Request, db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    form = await request.form()
    name = (form.get("name") or "").strip()
    email = (form.get("email") or "").strip().lower()
    if not name or "@" not in email:
        flash(request, "Name and a valid email are required", "error")
        return RedirectResponse("/me", 303)
    other = await db.scalar(select(User).where(User.email == email, User.id != user.id))
    if other:
        flash(request, "That email belongs to another team member", "error")
        return RedirectResponse("/me", 303)
    user.name, user.email = name, email
    prefs = dict(user.prefs or {})
    for key in ("notify_failed", "notify_approvals", "digest_weekly", "shortcuts"):
        prefs[key] = form.get(key) == "true"
    action = form.get("default_action") or "queue"
    if action in dict(DEFAULT_ACTIONS):
        prefs["default_action"] = action
    user.prefs = prefs
    await db.commit()
    flash(request, "Preferences saved")
    return RedirectResponse("/me", 303)


@router.post("/me/password")
async def me_password(request: Request, current: str = Form(...), new: str = Form(...),
                      db: AsyncSession = Depends(get_db), user: User = Depends(current_user)):
    if not verify_password(user.password_hash, current):
        flash(request, "Current password is wrong", "error")
    elif len(new) < 10:
        flash(request, "Use at least 10 characters for the new password", "error")
    else:
        user.password_hash = hash_password(new)
        await db.commit()
        flash(request, "Password changed")
    return RedirectResponse("/me", 303)
