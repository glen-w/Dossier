"""FastAPI workbench: server-rendered pages + SSE job progress."""

from __future__ import annotations

import secrets
from urllib.parse import urlparse

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from dossier.paths import TomlConfigError
from dossier.web.context import CSRF_COOKIE, STATIC
from dossier.web.routers import ask, jobs, locker, match, review, settings, tailor

_LOOPBACK = frozenset({"127.0.0.1", "::1", "testclient", "localhost"})
_BODY_CAP = 2_000_000


def create_app() -> FastAPI:
    app = FastAPI(title="Dossier", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")

    @app.middleware("http")
    async def harden(request: Request, call_next):
        client = request.client.host if request.client else ""
        if client not in _LOOPBACK:
            return HTMLResponse("loopback only", status_code=403)
        length = request.headers.get("content-length")
        if length and length.isdigit() and int(length) > _BODY_CAP:
            return HTMLResponse("payload too large", status_code=413)
        token = request.cookies.get(CSRF_COOKIE) or secrets.token_urlsafe(32)
        request.state.csrf_token = token
        mutating = request.method not in {"GET", "HEAD", "OPTIONS"}
        if mutating and client != "testclient":
            site = (request.headers.get("sec-fetch-site") or "").lower()
            origin = request.headers.get("origin") or ""
            host = urlparse(origin).hostname if origin else ""
            if site == "cross-site" or (
                origin and host not in {"127.0.0.1", "localhost", "::1"}
            ):
                return HTMLResponse("csrf rejected", status_code=403)
            cookie = request.cookies.get(CSRF_COOKIE) or ""
            header = request.headers.get("x-csrf-token") or ""
            form_token = ""
            ctype = (request.headers.get("content-type") or "").lower()
            if "form" in ctype:
                form = await request.form()
                form_token = str(form.get("csrf_token") or "")
            if cookie and header != cookie and form_token != cookie:
                return HTMLResponse("csrf rejected", status_code=403)
        try:
            response = await call_next(request)
        except Exception as extra:
            if isinstance(extra, TomlConfigError):
                return HTMLResponse(
                    f"<h1>dossier.toml is invalid</h1><p>{extra}</p>",
                    status_code=400,
                )
            raise
        response.set_cookie(
            CSRF_COOKIE,
            token,
            httponly=False,
            samesite="strict",
            path="/",
        )
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = "default-src 'self'"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response

    app.include_router(locker.router)
    app.include_router(review.router)
    app.include_router(ask.router)
    app.include_router(match.router)
    app.include_router(tailor.router)
    app.include_router(settings.router)
    app.include_router(jobs.router)
    return app


def serve(*, host: str = "127.0.0.1", port: int = 8766) -> None:
    import uvicorn

    if host not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("workbench binds loopback only")
    uvicorn.run(create_app(), host=host, port=port, log_level="warning")
