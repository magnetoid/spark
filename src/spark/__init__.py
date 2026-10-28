"""Spark — social autoposter & marketing app. CLI entry point."""

import argparse
import asyncio
import getpass
import sys


def _create_user(args) -> None:
    from sqlalchemy import select

    from spark.db import SessionLocal, create_all
    from spark.models import Role, User
    from spark.security import hash_password

    async def run():
        await create_all()
        password = args.password or getpass.getpass("Password: ")
        async with SessionLocal() as db:
            if await db.scalar(select(User).where(User.email == args.email.lower())):
                print("User already exists")
                return
            db.add(User(email=args.email.lower(), name=args.name, role=Role(args.role),
                        password_hash=hash_password(password)))
            await db.commit()
            print(f"Created {args.role} {args.email}")

    asyncio.run(run())


def _init_db(args) -> None:
    from spark.db import create_all

    asyncio.run(create_all())
    print("Tables created")


def _serve(args) -> None:
    import uvicorn

    uvicorn.run("spark.main:app", host=args.host, port=args.port, reload=args.reload)


def _worker(args) -> None:
    from arq.worker import run_worker

    from spark.worker import WorkerSettings

    run_worker(WorkerSettings)


def _tick(args) -> None:
    """Run one scheduler pass without Redis (handy for local dev and tests)."""
    from spark.db import SessionLocal
    from spark.services import publisher

    n = asyncio.run(publisher.publish_due(SessionLocal))
    print(f"Published {n} target(s)")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="spark")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("serve", help="Run the web app")
    s.add_argument("--host", default="0.0.0.0")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--reload", action="store_true")
    s.set_defaults(fn=_serve)
    w = sub.add_parser("worker", help="Run the background worker (needs Redis)")
    w.set_defaults(fn=_worker)
    t = sub.add_parser("tick", help="Publish due posts once, without Redis")
    t.set_defaults(fn=_tick)
    i = sub.add_parser("init-db", help="Create tables")
    i.set_defaults(fn=_init_db)
    u = sub.add_parser("create-user", help="Create a user")
    u.add_argument("email")
    u.add_argument("--name", default="Admin")
    u.add_argument("--role", default="owner", choices=["owner", "editor", "viewer"])
    u.add_argument("--password")
    u.set_defaults(fn=_create_user)
    args = p.parse_args(argv)
    args.fn(args)


if __name__ == "__main__":
    main(sys.argv[1:])
