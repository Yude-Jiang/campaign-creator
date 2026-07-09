import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.config import settings

# Ensure data directory exists
DATA_DIR = Path(settings.data_dir)
DATA_DIR.mkdir(parents=True, exist_ok=True)
(DATA_DIR / "campaigns").mkdir(exist_ok=True)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    from fastapi import Request
    from fastapi.responses import JSONResponse

    app = FastAPI(title=settings.app_name, version=settings.app_version)
    app.mount("/static", StaticFiles(directory="static"), name="static")

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        """Convert ValueError (e.g. invalid campaign_id) to HTTP 400."""
        logger.warning("ValueError: %s", exc)
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    # Register API routers
    from app.api.pages import router as pages_router
    from app.api.campaign import router as campaign_router

    app.include_router(pages_router, tags=["pages"])
    app.include_router(campaign_router, prefix="/api", tags=["campaign"])

    logger.info("Campaign Factory started in %s mode", settings.app_env)
    return app


app = create_app()
