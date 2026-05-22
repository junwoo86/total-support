"""FastAPI 엔트리포인트 — /api/grant/* 네임스페이스 (PRD §9)."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from total_support import __version__
from total_support.api import collection, domains, keywords, logs, postings
from total_support.config import get_settings

API_PREFIX = "/api/grant"

# SPA 정적 파일 — backend/../total_support_ui/ 디렉토리
_REPO_ROOT = Path(__file__).resolve().parents[3].parent  # backend/src/total_support/api → repo
_SPA_DIR = _REPO_ROOT / "total_support_ui"


def create_app() -> FastAPI:
    app = FastAPI(
        title="Total Support API",
        version=__version__,
        description="지원사업 통합 수집 및 다중 분야 스크리닝 대시보드 백엔드 (PRD v9.0)",
        docs_url=f"{API_PREFIX}/docs",
        openapi_url=f"{API_PREFIX}/openapi.json",
    )

    # CORS — G10: .env의 TS_CORS_ORIGINS로 환경별 분리.
    cors = get_settings().cors_origin_list or ["*"]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 라우터 등록
    app.include_router(postings.router, prefix=API_PREFIX)
    app.include_router(domains.router, prefix=API_PREFIX)
    app.include_router(keywords.router, prefix=API_PREFIX)
    app.include_router(keywords.preview_router, prefix=API_PREFIX)
    app.include_router(collection.router, prefix=API_PREFIX)
    app.include_router(logs.router, prefix=API_PREFIX)

    @app.get(f"{API_PREFIX}/ping")
    def ping():
        return {"ok": True}

    # ----- SPA 정적 서빙 ------------------------------------
    # /ui/* 로 total_support_ui/* 노출. 동일 origin이라 CORS 무관.
    if _SPA_DIR.is_dir():
        app.mount(
            "/ui",
            StaticFiles(directory=str(_SPA_DIR), html=True),
            name="spa",
        )

        @app.get("/")
        def root_redirect():
            return RedirectResponse(url="/ui/")

        @app.get("/favicon.ico", include_in_schema=False)
        def favicon():
            f = _SPA_DIR / "favicon.ico"
            if f.exists():
                return FileResponse(str(f))
            return RedirectResponse(url="/ui/")
    else:
        @app.get("/")
        def root():
            return {
                "app": "Total Support",
                "version": __version__,
                "docs": f"{API_PREFIX}/docs",
                "note": f"SPA 디렉토리 없음: {_SPA_DIR}",
            }

    return app


app = create_app()


def run() -> None:
    """`ts-api` 콘솔 스크립트."""
    import uvicorn
    uvicorn.run("total_support.api.main:app", host="0.0.0.0", port=8000, reload=False)
