from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from financial_assistant.api.config import get_settings
from financial_assistant.api.controllers import ROUTERS
from financial_assistant.api.errors import DeskError


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Pythia API",
        description=(
            "Portfolio anomalies explained by the news that was "
            "public when they happened."
        ),
        version="0.3.0",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(DeskError)
    def handle_desk_error(_: Request, error: DeskError) -> JSONResponse:
        return JSONResponse(
            status_code=error.status_code,
            content={"detail": error.message},
        )

    for router in ROUTERS:
        app.include_router(router, prefix="/api")

    # A production build of the frontend is served by the
    # API itself, so the whole desk is one process.
    if settings.frontend_dist.is_dir():
        app.mount(
            "/",
            StaticFiles(directory=settings.frontend_dist, html=True),
            name="frontend",
        )

    return app


app = create_app()
