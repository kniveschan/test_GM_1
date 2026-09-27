# Hello World API

Простое веб-приложение на FastAPI: приветствие хранится в PostgreSQL, а в рамках пользовательской сессии отдаётся из Redis.

## Стек

- Python 3.11+
- FastAPI, Uvicorn
- PostgreSQL 16, SQLAlchemy 2.x, asyncpg
- Redis 7, redis-py (asyncio)
- Alembic
- Docker Compose

## Требования к окружению

- Docker и Docker Compose
- (для тестов без Docker) Python 3.11+

## Настройка `.env`

```bash
cp .env.example .env
```

Переменные:

| Переменная | Назначение |
|---|---|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | учётные данные PostgreSQL |
| `POSTGRES_HOST` / `POSTGRES_PORT` | хост и порт БД (`db` внутри Compose) |
| `REDIS_HOST` / `REDIS_PORT` | хост и порт Redis (`redis` внутри Compose) |
| `CACHE_TTL` | время жизни кеша в секундах (целое число > 0) |

## Запуск через Docker Compose

```bash
cp .env.example .env
docker compose up --build
```

Порядок старта:

1. PostgreSQL и Redis проходят healthcheck.
2. Сервис `migrations` выполняет `alembic upgrade head` (таблица `greetings` и запись `Hello, World!`).
3. Только после успешного завершения миграций запускается FastAPI на [http://localhost:8000](http://localhost:8000).

Исходники `app/` смонтированы в контейнер, Uvicorn работает с `--reload`.

## Миграции

Миграции применяются автоматически сервисом `migrations`. Вручную:

```bash
docker compose run --rm migrations alembic upgrade head
```

Откат:

```bash
docker compose run --rm migrations alembic downgrade base
```

## Проверка API

Первый запрос (создаётся cookie `session_id`, фраза читается из PostgreSQL и кладётся в Redis):

```bash
curl -i -c cookies.txt http://localhost:8000/hello
```

Повтор с той же сессией (ответ из Redis, без запроса к PostgreSQL, пока не истёк TTL):

```bash
curl -i -b cookies.txt http://localhost:8000/hello
```

Ожидаемый ответ:

```text
Hello, World!
```

Проверка Redis:

```bash
docker compose exec redis redis-cli
KEYS session:*:hello
GET session:<session_id>:hello
TTL session:<session_id>:hello
```

Проверка PostgreSQL:

```bash
docker compose exec db psql -U app_user -d hello_db -c "SELECT * FROM greetings;"
```

Проверка живости приложения:

```bash
curl http://localhost:8000/health
```

## Как устроен кеш

1. Клиент вызывает `GET /hello`.
2. Если cookie `session_id` нет, сервер генерирует UUID и ставит cookie (`HttpOnly`, `SameSite=Lax`).
3. Формируется ключ Redis: `session:{session_id}:hello`.
4. Если ключ есть — тело ответа берётся из Redis, PostgreSQL не вызывается.
5. Если ключа нет (первый запрос, истёк TTL или Redis недоступен) — читается первая строка из таблицы `greetings`, значение пишется в Redis с TTL из `CACHE_TTL` и возвращается клиенту.
6. Разные `session_id` используют разные ключи. Одна и та же cookie попадает в один и тот же кеш.

Если Redis временно недоступен, API продолжает отвечать из PostgreSQL. Если таблица пуста — HTTP 404. Если PostgreSQL недоступен — HTTP 503.

## Структура проекта

```text
.
├── app/
│   ├── main.py      # FastAPI, lifespan (engine + Redis)
│   ├── config.py    # Pydantic Settings
│   ├── db.py        # async SQLAlchemy session
│   ├── cache.py     # ключи и get/set Redis
│   ├── models.py    # Greeting
│   └── routes.py    # GET /hello, GET /health
├── alembic/         # миграции, включая сид
├── tests/
├── docker-compose.yml
├── Dockerfile
└── .env.example
```

## Запуск тестов

Локально (моки PostgreSQL и Redis, Docker не нужен):

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pytest
```

В Linux/macOS активация: `source .venv/bin/activate`.

## Остановка и очистка

Остановка контейнеров:

```bash
docker compose down
```

Остановка с удалением volume PostgreSQL:

```bash
docker compose down -v
```
