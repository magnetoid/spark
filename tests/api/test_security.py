"""Every write route on the API needs a role dependency or an explicit allowlist entry."""

from fastapi.routing import APIRoute


def test_every_api_write_route_requires_a_role():
    from spark.api import deps
    from spark.api.app import api

    allow = {"/auth/login", "/auth/logout", "/auth/setup", "/me", "/me/password"}
    offenders = []
    for r in api.routes:
        if not isinstance(r, APIRoute) or not (r.methods & {"POST", "PUT", "PATCH", "DELETE"}):
            continue
        if r.path in allow:
            continue
        calls = {d.call for d in r.dependant.dependencies} | {p.depends.dependency for p in r.dependant.query_params if getattr(p, "depends", None)}
        if not ({deps.editor_brand, deps.owner_brand, deps.editor, deps.owner} & calls):
            offenders.append(r.path)
    assert offenders == [], offenders
