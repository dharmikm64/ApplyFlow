"""FastAPI application factory."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from app.api.errors import ApiError
from app.config import REPO_ROOT, get_settings
from app.logging import configure_logging

log = logging.getLogger(__name__)
FRONTEND_DIST = REPO_ROOT / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    worker = None
    if settings.WORKER_MODE == "embedded":
        from app.jobs.worker import start_embedded_worker

        worker = start_embedded_worker()
    try:
        yield
    finally:
        if worker is not None:
            worker.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    settings.validate_runtime()
    configure_logging(settings.LOG_LEVEL)

    app = FastAPI(
        title="ApplyFlow",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    # Signed cookie holding ONLY Authlib's transient OAuth state/nonce/PKCE verifier (R3).
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.SESSION_SECRET,
        session_cookie="af_oauth",
        max_age=600,
        same_site="lax",
        https_only=settings.secure_cookies,
    )

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse({"error": exc.code, "message": exc.message}, status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields = sorted({".".join(str(p) for p in e.get("loc", [])[1:]) for e in exc.errors()})
        return JSONResponse(
            {"error": "validation", "message": f"Invalid value for: {', '.join(fields)}"},
            status_code=422,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = "not_found" if exc.status_code == 404 else "http_error"
        return JSONResponse({"error": code, "message": str(exc.detail)}, status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def _unhandled(_: Request, exc: Exception) -> JSONResponse:
        log.error("unhandled error", extra={"error_type": type(exc).__name__})
        return JSONResponse(
            {"error": "internal_error", "message": "Something went wrong."}, status_code=500
        )

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    from app.api.routers import all_routers as api_routers
    from app.auth.gmail_oauth import router as gmail_auth_router
    from app.auth.oidc import router as oidc_router

    app.include_router(oidc_router)
    app.include_router(gmail_auth_router)
    for r in api_routers:
        app.include_router(r)

    if settings.APP_ENV == "test":
        from app.testing.routes import router as test_router

        app.include_router(test_router)

    _mount_spa(app)
    return app


def _mount_spa(app: FastAPI) -> None:
    """Serve the built frontend (single origin in production, R13)."""
    if not FRONTEND_DIST.is_dir():
        return
    index = FRONTEND_DIST / "index.html"

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str) -> FileResponse:
        if path.startswith(("api/", "auth/", "test/")):
            raise StarletteHTTPException(status_code=404, detail="Not found")
        candidate = (FRONTEND_DIST / path).resolve()
        if path and candidate.is_file() and FRONTEND_DIST.resolve() in candidate.parents:
            return FileResponse(candidate)
        return FileResponse(index)


app = create_app()
