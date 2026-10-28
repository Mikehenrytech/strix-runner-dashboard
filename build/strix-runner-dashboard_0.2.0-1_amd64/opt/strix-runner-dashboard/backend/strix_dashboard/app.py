"""FastAPI application for the read-only Strix dashboard."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from . import __version__
from .catalog import DashboardError, HistoryCatalog, RunnerHistorySource
from .settings import DashboardSettings


def _exclusion_set(values: list[str] | None) -> set[str]:
    """Validate bounded opaque run IDs supplied as read-only view filters."""
    if not values:
        return set()
    if len(values) > 1_000:
        raise HTTPException(status_code=422, detail="Demasiadas exclusiones.")
    if any(
        len(value) != 20 or any(character not in "0123456789abcdef" for character in value)
        for value in values
    ):
        raise HTTPException(status_code=422, detail="ID de exclusión inválido.")
    return set(values)


def create_app(
    settings: DashboardSettings | None = None,
    catalog: HistoryCatalog | None = None,
) -> FastAPI:
    """Create an application with injectable settings and history source."""
    settings = settings or DashboardSettings.from_environment()
    catalog = catalog or HistoryCatalog(settings, RunnerHistorySource(settings).load)
    app = FastAPI(
        title="Strix History Dashboard",
        version=__version__,
        docs_url=None,
        redoc_url=None,
        openapi_url="/api/openapi.json",
    )
    app.state.catalog = catalog

    @app.middleware("http")
    async def security_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; base-uri 'none'; object-src 'none'; "
            "frame-ancestors 'none'; img-src 'self' data:; "
            "style-src 'self'; script-src 'self'; connect-src 'self'"
        )
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        return response

    @app.exception_handler(DashboardError)
    async def dashboard_error_handler(
        _request: Request,
        exc: DashboardError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": str(exc)},
        )

    @app.get("/api/v1/health")
    def health() -> dict[str, object]:
        snapshot = catalog.snapshot()
        return {
            "status": "ok",
            "readonly": True,
            "generated_at": snapshot.generated_at,
            "runs": len(snapshot.runs),
        }

    @app.get("/api/v1/summary")
    def summary(
        exclude: Annotated[list[str] | None, Query()] = None,
        refresh: bool = False,
    ) -> dict[str, object]:
        return catalog.summary_excluding(
            _exclusion_set(exclude),
            force=refresh,
        )

    @app.get("/api/v1/facets")
    def facets(
        exclude: Annotated[list[str] | None, Query()] = None,
        refresh: bool = False,
    ) -> dict[str, list[str]]:
        return catalog.facets(
            excluded_ids=_exclusion_set(exclude),
            force=refresh,
        )

    @app.get("/api/v1/runs")
    def runs(
        profile: str | None = Query(default=None, max_length=200),
        status: str | None = Query(default=None, max_length=100),
        agent: str | None = Query(default=None, max_length=200),
        skill: str | None = Query(default=None, max_length=200),
        utility: str | None = Query(default=None, max_length=100),
        from_date: date | None = Query(default=None, alias="from"),
        to_date: date | None = Query(default=None, alias="to"),
        search: str | None = Query(default=None, max_length=500),
        sort_by: Annotated[
            str,
            Query(
                pattern=(
                    "^(start_time|profile|status|findings|duration_seconds|"
                    "total_tokens)$"
                )
            ),
        ] = "start_time",
        order: Annotated[str, Query(pattern="^(asc|desc)$")] = "desc",
        page: Annotated[int, Query(ge=1)] = 1,
        page_size: Annotated[int, Query(ge=1, le=200)] = 25,
        exclude: Annotated[list[str] | None, Query()] = None,
        refresh: bool = False,
    ) -> dict[str, object]:
        return catalog.list_runs(
            profile=profile,
            status=status,
            agent=agent,
            skill=skill,
            utility=utility,
            from_date=from_date.isoformat() if from_date else None,
            to_date=to_date.isoformat() if to_date else None,
            search=search,
            sort_by=sort_by,
            order=order,
            page=page,
            page_size=page_size,
            excluded_ids=_exclusion_set(exclude),
            force=refresh,
        )

    @app.get("/api/v1/runs/{stable_id}")
    def run_detail(stable_id: str) -> dict[str, object]:
        return catalog.detail(stable_id)

    @app.get("/api/v1/runs/{stable_id}/report")
    def run_report(stable_id: str) -> Response:
        content, filename = catalog.report(stable_id)
        return Response(
            content=content,
            media_type="text/plain; charset=utf-8",
            headers={
                "Content-Disposition": f'inline; filename="{filename}"',
                "X-Content-Type-Options": "nosniff",
            },
        )

    frontend = settings.frontend_dist.resolve()
    index = frontend / "index.html"
    assets = frontend / "assets"
    if index.is_file():
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{requested_path:path}", include_in_schema=False)
        def frontend_file(requested_path: str) -> FileResponse:
            if requested_path == "api" or requested_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="Ruta API no encontrada.")
            requested = (frontend / requested_path).resolve()
            try:
                requested.relative_to(frontend)
            except ValueError:
                requested = index
            if requested.is_file() and requested != index:
                return FileResponse(requested)
            return FileResponse(index)

    else:

        @app.get("/", include_in_schema=False)
        def frontend_missing() -> JSONResponse:
            return JSONResponse(
                status_code=503,
                content={
                    "detail": "Frontend no compilado. Ejecuta el build de frontend/."
                },
            )

    return app
