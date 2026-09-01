import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.config import settings
from app.workers.scheduler import setup_scheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler = setup_scheduler()
    scheduler.start()
    logger.info("%s started (env=%s)", settings.APP_NAME, settings.ENVIRONMENT)
    yield
    scheduler.shutdown(wait=False)
    logger.info("%s stopped", settings.APP_NAME)


app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0-mvp",
    lifespan=lifespan,
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"detail": "VALIDATION_ERROR", "errors": exc.errors()})


app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/health", tags=["system"])
async def health() -> dict:
    return {"status": "ok"}
