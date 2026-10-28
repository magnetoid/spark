from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from spark.db import get_db
from spark.models import Role, User
from spark.security import hash_password, verify_password
from spark.web.deps import flash, render

router = APIRouter()


@router.get("/login")
async def login_page(request: Request, db: AsyncSession = Depends(get_db)):
    has_users = bool(await db.scalar(select(func.count(User.id))))
    if not has_users:
        return RedirectResponse("/setup", 303)
    return await render(request, "auth/login.html", db)


@router.post("/login")
async def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    user = await db.scalar(select(User).where(func.lower(User.email) == email.strip().lower()))
    if not user or not user.is_active or not verify_password(user.password_hash, password):
        return await render(
            request, "auth/login.html", db, error="Invalid email or password", email=email,
            status_code=400,
        )
    request.session.clear()
    request.session["user_id"] = user.id
    return RedirectResponse("/", 303)


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", 303)


@router.get("/setup")
async def setup_page(request: Request, db: AsyncSession = Depends(get_db)):
    if await db.scalar(select(func.count(User.id))):
        return RedirectResponse("/login", 303)
    return await render(request, "auth/setup.html", db)


@router.post("/setup")
async def setup(
    request: Request,
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(..., min_length=8),
    db: AsyncSession = Depends(get_db),
):
    """First-run: create the owner account. Disabled once any user exists."""
    if await db.scalar(select(func.count(User.id))):
        return RedirectResponse("/login", 303)
    user = User(
        name=name.strip(), email=email.strip().lower(), password_hash=hash_password(password),
        role=Role.owner,
    )
    db.add(user)
    await db.commit()
    request.session.clear()
    request.session["user_id"] = user.id
    flash(request, "Welcome to Spark! Create your first brand.")
    return RedirectResponse("/brands/new", 303)
