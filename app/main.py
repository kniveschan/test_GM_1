import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from redis.asyncio import Redis

from app.config import get_settings
from app.db import close_db, init_db
from app.routes import router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    init_db(settings.database_url)
    app.state.settings = settings
    app.state.redis = Redis.from_url(settings.redis_url, decode_responses=True)
    logger.info("Application started")
    yield
    await app.state.redis.aclose()
    await close_db()
    logger.info("Application stopped")


def create_app(*, testing: bool = False) -> FastAPI:
    app_lifespan = None if testing else lifespan
    application = FastAPI(title="Hello World API", lifespan=app_lifespan)
    application.include_router(router)
    return application


app = create_app()
