import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import get_cached_hello, set_cached_hello
from app.config import Settings
from app.db import get_session
from app.models import Greeting

logger = logging.getLogger(__name__)

router = APIRouter()

SESSION_COOKIE = "session_id"


def get_app_settings(request: Request) -> Settings:
    return request.app.state.settings


def _attach_session_cookie(response: Response, session_id: str, is_new: bool) -> None:
    if is_new:
        response.set_cookie(
            key=SESSION_COOKIE,
            value=session_id,
            httponly=True,
            samesite="lax",
        )


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/hello", response_class=PlainTextResponse)
async def hello(
    request: Request,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_app_settings),
) -> PlainTextResponse:
    session_id = request.cookies.get(SESSION_COOKIE)
    is_new = not bool(session_id)
    if is_new:
        session_id = str(uuid.uuid4())
        logger.info("New session created: %s", session_id)

    redis_client = request.app.state.redis
    cached = await get_cached_hello(redis_client, session_id)
    if cached is not None:
        response = PlainTextResponse(content=cached)
        _attach_session_cookie(response, session_id, is_new)
        return response

    try:
        result = await session.execute(
            select(Greeting).order_by(Greeting.id.asc()).limit(1)
        )
        greeting = result.scalar_one_or_none()
    except SQLAlchemyError:
        logger.exception("Failed to load greeting from PostgreSQL")
        raise HTTPException(
            status_code=503,
            detail="PostgreSQL is unavailable",
        ) from None

    if greeting is None:
        logger.error("No greeting found in PostgreSQL")
        raise HTTPException(status_code=404, detail="Greeting not found")

    logger.info("Greeting loaded from PostgreSQL")
    await set_cached_hello(
        redis_client,
        session_id,
        greeting.message,
        settings.cache_ttl,
    )

    response = PlainTextResponse(content=greeting.message)
    _attach_session_cookie(response, session_id, is_new)
    return response
