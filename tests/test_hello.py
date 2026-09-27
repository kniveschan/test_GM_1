from types import SimpleNamespace

from fastapi.testclient import TestClient
from redis.exceptions import RedisError
from sqlalchemy.exc import SQLAlchemyError

from app.cache import hello_cache_key
from app.config import Settings
from app.db import get_session
from app.main import create_app


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.fail = False

    async def get(self, key: str) -> str | None:
        if self.fail:
            raise RedisError("redis unavailable")
        return self.store.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        if self.fail:
            raise RedisError("redis unavailable")
        self.store[key] = value
        return True

    async def aclose(self) -> None:
        return None


class FakeResult:
    def __init__(self, value: object) -> None:
        self._value = value

    def scalar_one_or_none(self) -> object:
        return self._value


class FakeSession:
    def __init__(self, greeting: object | None = None, fail: bool = False) -> None:
        self.greeting = greeting
        self.fail = fail
        self.execute_calls = 0

    async def execute(self, _stmt: object) -> FakeResult:
        self.execute_calls += 1
        if self.fail:
            raise SQLAlchemyError("postgres unavailable")
        return FakeResult(self.greeting)


def _settings() -> Settings:
    return Settings(
        postgres_user="app_user",
        postgres_password="app_password",
        postgres_db="hello_db",
        postgres_host="localhost",
        postgres_port=5432,
        redis_host="localhost",
        redis_port=6379,
        cache_ttl=60,
    )


def _make_client(session: FakeSession, redis_client: FakeRedis) -> TestClient:
    application = create_app(testing=True)
    application.state.settings = _settings()
    application.state.redis = redis_client

    async def override_session() -> FakeSession:
        yield session

    application.dependency_overrides[get_session] = override_session
    return TestClient(application)


def test_hello_returns_plain_text() -> None:
    greeting = SimpleNamespace(message="Hello, World!")
    client = _make_client(FakeSession(greeting=greeting), FakeRedis())

    response = client.get("/hello")

    assert response.status_code == 200
    assert response.text == "Hello, World!"
    assert response.headers["content-type"].startswith("text/plain")


def test_hello_sets_session_cookie_on_first_request() -> None:
    greeting = SimpleNamespace(message="Hello, World!")
    client = _make_client(FakeSession(greeting=greeting), FakeRedis())

    response = client.get("/hello")

    assert "session_id" in response.cookies
    assert response.cookies["session_id"]


def test_repeat_request_uses_redis_and_skips_postgres() -> None:
    greeting = SimpleNamespace(message="Hello, World!")
    session = FakeSession(greeting=greeting)
    redis_client = FakeRedis()
    client = _make_client(session, redis_client)

    first = client.get("/hello")
    session_id = first.cookies["session_id"]
    assert session.execute_calls == 1
    assert hello_cache_key(session_id) in redis_client.store

    second = client.get("/hello")

    assert second.status_code == 200
    assert second.text == "Hello, World!"
    assert session.execute_calls == 1


def test_postgres_is_used_after_ttl_expiry() -> None:
    greeting = SimpleNamespace(message="Hello, World!")
    session = FakeSession(greeting=greeting)
    redis_client = FakeRedis()
    client = _make_client(session, redis_client)

    first = client.get("/hello")
    session_id = first.cookies["session_id"]
    redis_client.store.pop(hello_cache_key(session_id))

    second = client.get("/hello")

    assert second.status_code == 200
    assert session.execute_calls == 2
    assert hello_cache_key(session_id) in redis_client.store


def test_different_session_ids_use_different_keys() -> None:
    greeting = SimpleNamespace(message="Hello, World!")
    session = FakeSession(greeting=greeting)
    redis_client = FakeRedis()
    client = _make_client(session, redis_client)

    client.cookies.set("session_id", "session-a")
    client.get("/hello")
    client.cookies.set("session_id", "session-b")
    client.get("/hello")

    assert hello_cache_key("session-a") in redis_client.store
    assert hello_cache_key("session-b") in redis_client.store
    assert session.execute_calls == 2


def test_missing_greeting_returns_404() -> None:
    client = _make_client(FakeSession(greeting=None), FakeRedis())

    response = client.get("/hello")

    assert response.status_code == 404


def test_health_ok() -> None:
    client = _make_client(FakeSession(greeting=None), FakeRedis())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
