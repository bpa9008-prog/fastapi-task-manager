# Менеджер задач — FastAPI + PostgreSQL

![CI](https://github.com/bpa9008-prog/fastapi-task-manager/actions/workflows/ci.yml/badge.svg)

Отчёт по **практической работе № 3** «Тестирование, контейнеризация и CI/CD для FastAPI-приложения» идёт первым. Под ним сохранён отчёт по [практической работе № 2](#практическая-работа--2--менеджер-задач-fastapi--postgresql--sqlalchemy--pydantic), где описаны само приложение и его эндпоинты.

# Практическая работа № 3 — тесты, Docker и CI/CD

## Опубликованные образы

| Реестр | Ссылка | Pull |
|---|---|---|
| GitHub Container Registry | <https://github.com/bpa9008-prog/fastapi-task-manager/pkgs/container/fastapi-task-manager> | `docker pull ghcr.io/bpa9008-prog/fastapi-task-manager:latest` |
| Docker Hub | <https://hub.docker.com/r/bpa9008/fastapi-task-manager> | `docker pull bpa9008/fastapi-task-manager:latest` |

Каждый образ публикуется с двумя тегами: `latest` и `sha-<короткий хеш коммита>`.

## Что сделано

```
.
├── .github/workflows/ci.yml   # CI/CD: lint → test, compose → build & push
├── tests/
│   ├── conftest.py            # тестовая БД tasks_test, чистые таблицы, dependency_overrides
│   ├── test_users.py
│   └── test_tasks.py
├── Dockerfile                 # многоэтапный: builder → test / runtime (USER app)
├── .dockerignore
├── docker-compose.yml         # db (healthcheck) → migrate → app; tests (profile test)
├── requirements-dev.txt       # pytest, pytest-asyncio, httpx, ruff
├── pytest.ini
└── ruff.toml
```

### Тесты

Тесты ходят в реальный PostgreSQL, в отдельную БД `tasks_test`. Устроено это так (`tests/conftest.py`):

- URL берётся из `TEST_DATABASE_URL`, по умолчанию `postgresql+asyncpg://app:app@localhost:5432/tasks_test`. Если базы `tasks_test` нет, фикстура создаёт её сама.
- Перед сессией тестов таблицы создаются по `Base.metadata`, после сессии удаляются.
- Перед каждым тестом выполняется `TRUNCATE tasks, users RESTART IDENTITY CASCADE`, поэтому каждый тест начинает с пустых таблиц, а `id` снова идут с 1.
- `app.dependency_overrides[get_session]` подменяет сессию на сессию тестовой БД. Запросы идут через `httpx.AsyncClient` + `ASGITransport`, сервер не поднимается.

Всего 11 тестов. Девять обязательных из шага 4 и два дополнительных:

| # | Тест | Проверяет |
|---|---|---|
| 1 | `test_users.py::test_create_user` | создание пользователя → **201** |
| 2 | `test_users.py::test_create_user_duplicate_email` | повторный email → **409** |
| 3 | `test_users.py::test_create_user_invalid_email` | невалидный email → **422** |
| 4 | `test_tasks.py::test_create_task` | создание задачи → **201** |
| 5 | `test_tasks.py::test_create_task_unknown_owner` | задача с несуществующим владельцем → **404** |
| 6 | `test_tasks.py::test_list_tasks_done_filter_and_pagination` | фильтр `done` и пагинация `limit`/`offset` |
| 7 | `test_tasks.py::test_patch_task_updates_only_passed_fields` | PATCH меняет только переданные поля |
| 8 | `test_tasks.py::test_delete_task_then_get_404` | DELETE → 204, затем GET → **404** |
| 9 | `test_tasks.py::test_process_time_header` | наличие заголовка `X-Process-Time` |
| + | `test_users.py::test_get_user_not_found` | GET несуществующего пользователя → 404 |
| + | `test_tasks.py::test_list_tasks_invalid_limit` | `limit=0` → 422 |

### Dockerfile

Сборка из трёх этапов:

- **builder** ставит зависимости из `requirements.txt` в venv `/opt/venv`;
- **test** берёт builder, доставляет `requirements-dev.txt` и копирует весь проект. На этом этапе запускаются тесты в Docker Compose;
- **runtime** — финальный образ на чистом `python:3.12-slim`. В него копируются только `/opt/venv`, `app/`, `migrations/` и `alembic.ini`. Pip-кеша, тестов и dev-зависимостей там нет. Процесс работает от системного пользователя `app` (`USER app`), а не от root. Есть `HEALTHCHECK` по `/docs`.

### docker-compose.yml

- `db`: `postgres:16` с healthcheck `pg_isready`;
- `migrate`: тот же образ, что и у приложения. Ждёт `db: service_healthy`, выполняет `alembic upgrade head` и завершается;
- `app`: стартует, только когда `db` здоров, а `migrate` завершился успешно (`service_completed_successfully`);
- `tests` (профиль `test`): собирается из этапа `test` и гоняет pytest против `db`, в базе `tasks_test`.

### CI/CD (`.github/workflows/ci.yml`)

Workflow запускается на каждый `push` и `pull_request`.

| Job | Что делает | Когда |
|---|---|---|
| `lint` | `ruff check .` и `ruff format --check .` | всегда |
| `test` | поднимает service-контейнер `postgres:16`, `pip install -r requirements-dev.txt`, `pytest -v` | всегда |
| `compose` | `docker compose up -d --build --wait app` (db → migrate → app), `curl /tasks`, проверка, что `id -u` в контейнере ≠ 0, `docker compose run --rm tests` | всегда |
| `build` | сборка этапа `runtime`, push в GHCR (`GITHUB_TOKEN`) и Docker Hub (`DOCKERHUB_USERNAME` / `DOCKERHUB_TOKEN`) | только `push` в ветку по умолчанию и только если `lint`, `test`, `compose` успешны (`needs`) |

> Ветка по умолчанию в репозитории называется `master`, а не `main`. Условие в workflow привязано к ветке по умолчанию (`github.event.repository.default_branch`), поэтому после переименования в `main` ничего менять не придётся.

## Запуск тестов

### Локально

Нужны Python 3.12 и запущенный PostgreSQL. Проще всего поднять БД из compose:

```bash
docker compose up -d db

python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt

pytest -v                          # БД tasks_test создаётся автоматически
ruff check . && ruff format --check .
```

Если PostgreSQL другой, укажите его URL:

```bash
TEST_DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/tasks_test pytest -v
```

### Через Docker Compose

```bash
# тесты в контейнере (поднимет db, соберёт этап test, запустит pytest)
docker compose run --rm tests

# всё приложение: db -> migrate (alembic upgrade head) -> app на http://localhost:8000
docker compose up -d --build
docker compose ps
curl -i http://localhost:8000/tasks

# остановить и удалить данные
docker compose --profile test down -v
```

## Проверка pipeline (шаг 8)

В [pull request #1](https://github.com/bpa9008-prog/fastapi-task-manager/pull/1) специально запушен коммит, где в `test_create_user` ожидается `200` вместо `201` (`436ab4a`). Pipeline покраснел: упали `test` и `compose` (в нём тесты тоже гоняются), а `build` не запустился. Затем тест исправлен (`5a573da`), pipeline снова зелёный, PR смёржен в `master`.

### «Упавший» pipeline

[Run #7](https://github.com/bpa9008-prog/fastapi-task-manager/actions/runs/40524779911): `test` и `compose` красные, `build` пропущен.

![Упавший pipeline](docs/screenshots/ci_failed_pipeline.png)

Лог упавшего job `test`. Это вывод `gh run view 40524779911 --log-failed`, потому что без входа в аккаунт GitHub логи не показывает:

![Лог упавшего теста](docs/screenshots/ci_failed_test_log.png)

### Успешный pipeline

[Run #10](https://github.com/bpa9008-prog/fastapi-task-manager/actions/runs/40543878308) запустился после merge PR #1 в `master`. Все четыре job-а зелёные, `build` опубликовал образ `sha-bdb381d` / `latest` в GHCR и Docker Hub.

![Успешный pipeline](docs/screenshots/ci_success_pipeline.png)

История PR #1: у коммита `436ab4a` со сломанным тестом красный крестик, у исправления `5a573da` — зелёная галочка, PR смёржен.

![PR #1](docs/screenshots/ci_pr1_merged.png)

## Ответы на контрольные вопросы

**1. Чем CI отличается от CD (continuous delivery и continuous deployment)?**

- **Continuous Integration** — изменения часто вливаются в общую ветку, и на каждое из них автоматически запускаются сборка, линтер и тесты. Цель — быстро узнать, что изменение что-то сломало, пока оно маленькое. Результат CI — проверенный коммит.
- **Continuous Delivery** продолжает CI. Каждое изменение, прошедшее проверки, автоматически собирается в готовый к выпуску артефакт (здесь это Docker-образ в GHCR и Docker Hub) и в любой момент может быть выкачено. Само развёртывание в production запускает человек: кнопка, approve, тег релиза.
- **Continuous Deployment** идёт ещё дальше: ручного шага нет, каждое изменение, прошедшее все проверки, само уезжает в production.

В этой работе есть CI (lint, test, compose) и continuous delivery (публикация образа после успешных тестов). Автоматического деплоя на сервер нет.

**2. Как работает `dependency_overrides` и зачем он нужен в тестах?**

`app.dependency_overrides` — словарь `{исходная_зависимость: замена}`. Когда FastAPI разрешает `Depends(get_session)`, он сначала смотрит в этот словарь. Если там есть ключ `get_session`, вызывается замена, причём с теми же правилами: можно `yield`, у неё могут быть свои `Depends`. Код роутеров при этом не меняется.

В тестах так подменяют внешние ресурсы. Здесь `get_session` заменён функцией, которая выдаёт сессию тестовой БД `tasks_test`, поэтому тесты не трогают рабочую БД. Так же подменяют авторизацию (текущий пользователь), внешние API, часы и т. п. После теста словарь нужно очистить (`app.dependency_overrides.clear()`), иначе подмена протечёт в другие тесты.

**3. Зачем нужна многоэтапная сборка образа?**

Сборке нужно больше, чем запуску: компиляторы, заголовки, pip-кеш, dev-зависимости, тесты. В многоэтапном Dockerfile всё это остаётся на промежуточных этапах, а финальный образ получает через `COPY --from=builder` только готовое (здесь это venv и код). Что это даёт:
- образ меньше, поэтому быстрее pull/push и меньше места в реестре;
- меньше поверхность атаки: в образе нет компилятора, pip-кеша, тестов, лишних пакетов и связанных с ними CVE;
- кеш слоёв лучше работает, зависимости пересобираются только при изменении `requirements.txt`;
- из одного Dockerfile собираются разные цели. Здесь `target: test` используется для тестов в compose, а `target: runtime` — для публикуемого образа.

**4. Почему контейнер не следует запускать от root?**

UID 0 внутри контейнера по умолчанию тот же root, что и на хосте. Изоляцию дают namespaces и capabilities, но не отдельный пользователь. Если приложение взломают (RCE через уязвимость в зависимости и т. п.), у атакующего будет root в контейнере. Тогда он может:
- менять любые файлы образа, ставить пакеты, подменить код приложения;
- с куда большими шансами выбраться на хост через уязвимость ядра или runtime, смонтированный том, `docker.sock` или лишние capabilities, и сразу оказаться там root;
- писать в смонтированные тома от root.

Принцип наименьших привилегий: веб-сервису root не нужен. Поэтому в `runtime` создаётся системный пользователь `app` и ставится `USER app`. В CI job `compose` проверяет, что `id -u` в контейнере не равен 0. Многие платформы (Kubernetes с `runAsNonRoot`, OpenShift) вообще не запустят контейнер от root.

**5. Как в GitHub Actions передаются секреты и почему их нельзя хранить в репозитории?**

Секреты хранятся в настройках репозитория, окружения или организации (Settings → Secrets and variables → Actions), в зашифрованном виде. В workflow на них ссылаются через `${{ secrets.NAME }}`, обычно передают в `with:` действия или в `env:` шага. Runner получает значение только во время запуска, а в логах оно автоматически заменяется на `***`. Для PR из форков секреты не передаются. Кроме пользовательских секретов, на каждый запуск выдаётся временный `GITHUB_TOKEN` с правами из блока `permissions:`. Здесь он используется для push в GHCR (`packages: write` только у job `build`). Для Docker Hub используются `DOCKERHUB_USERNAME` и `DOCKERHUB_TOKEN`; `DOCKERHUB_TOKEN` — это access token с ограниченными правами, а не пароль.

Хранить секреты в репозитории нельзя:
- их видит каждый, у кого есть доступ к коду, а у публичного репозитория это весь интернет. Боты сканируют GitHub на утёкшие ключи за минуты;
- git хранит историю: удаление файла следующим коммитом не убирает секрет из истории и из форков, ключ остаётся скомпрометированным, его надо отзывать;
- секрет нельзя сменить или ограничить по окружению, не меняя код; нет аудита, кто им пользовался.

**6. Что произойдёт с job-ом `build`, если упадёт `test`? Где это задаётся?**

`build` не запустится и получит статус **skipped**, поэтому образ не соберётся и не опубликуется. Зависимость задаётся ключом `needs` в описании job:

```yaml
build:
  needs: [lint, test, compose]
  if: github.event_name == 'push' && github.ref_name == github.event.repository.default_branch
```

Без `needs` все job-ы workflow выполняются параллельно и независимо друг от друга. С `needs` job ждёт перечисленные и по умолчанию запускается, только если все они успешны: неявное условие `success()` добавляется к `if`. Это видно на скриншоте упавшего pipeline: `build` перечёркнут. Запустить job несмотря на падение можно только явно, через `if: always()` или `failure()`.

**7. Где лучше применять миграции: при старте контейнера или отдельным шагом в CD? Каковы плюсы и минусы каждого варианта?**

*При старте контейнера* (`alembic upgrade head && uvicorn ...` в entrypoint):
- плюсы: просто, ничего не нужно настраивать; схема всегда соответствует коду образа; удобно для разработки и одного экземпляра;
- минусы: при нескольких репликах миграцию одновременно запускают все экземпляры. Нужны блокировки, иначе гонки и падения. Долгая миграция задерживает старт, из-за неё срабатывают health-check и рестарты. Упавшая миграция превращается в crash loop всех подов. Приложению нужны права на DDL. Откат образа не откатывает схему.

*Отдельным шагом в CD* (job перед деплоем, Kubernetes Job / init-задача, `docker compose run migrate`):
- плюсы: миграция выполняется ровно один раз и явно. Если она упала, деплой останавливается до выкатки нового кода. Есть отдельный лог и права: DDL-права только у шага миграций, приложение работает от пользователя с DML. Можно поставить ручное подтверждение для опасных миграций;
- минусы: пайплайн сложнее, нужен доступ из CD к БД. Есть окно, когда новая схема уже применена, а работает старый код, поэтому миграции должны быть обратно совместимыми (expand/contract): сначала добавляем, потом в следующем релизе удаляем.

Для production обычно выбирают отдельный шаг. В этом проекте взят компромисс: в `docker-compose.yml` миграции вынесены в отдельный одноразовый сервис `migrate`, а `app` стартует только после его успешного завершения (`service_completed_successfully`). Миграция запускается один раз и не зашита в entrypoint приложения.

---


# Практическая работа № 2 — «Менеджер задач» (FastAPI + PostgreSQL + SQLAlchemy + Pydantic)

REST API сервис, который хранит пользователей и их задачи.
Стек: **FastAPI**, **SQLAlchemy 2.0** (async, `asyncpg`), **PostgreSQL 16**, **Pydantic v2**, **pydantic-settings**, **Alembic**, middleware **Starlette**.

## Структура проекта

```
.
├── app/
│   ├── __init__.py
│   ├── main.py            # создание приложения, middleware, подключение роутеров
│   ├── config.py          # настройки (pydantic-settings, DATABASE_URL)
│   ├── db.py              # async-движок, фабрика сессий, Base, get_session
│   ├── models.py          # ORM-модели User, Task (Mapped / mapped_column)
│   ├── schemas.py         # Pydantic-схемы *Create / *Read / *Update
│   └── routers/
│       ├── users.py       # POST /users, GET /users/{id}
│       └── tasks.py       # CRUD /tasks
├── migrations/            # Alembic (шаблон async)
│   ├── env.py
│   └── versions/57e0c06a86dd_create_users_and_tasks.py
├── docs/screenshots/      # скриншоты для отчёта
├── alembic.ini
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── README.md
```

## Эндпоинты

| Метод  | Путь          | Описание                                                        | Коды ответа         |
|--------|---------------|-----------------------------------------------------------------|---------------------|
| POST   | `/users`      | создать пользователя                                            | 201, 409, 422       |
| GET    | `/users/{id}` | получить пользователя                                           | 200, 404            |
| POST   | `/tasks`      | создать задачу                                                  | 201, 404, 422       |
| GET    | `/tasks`      | список задач, фильтры `done`, `owner_id`, `limit` (1–100), `offset` | 200 (422 при неверных параметрах) |
| GET    | `/tasks/{id}` | получить задачу                                                 | 200, 404            |
| PATCH  | `/tasks/{id}` | частично обновить задачу                                        | 200, 404, 422       |
| DELETE | `/tasks/{id}` | удалить задачу                                                  | 204, 404            |

Каждый ответ содержит заголовок `X-Process-Time`. Middleware пишет в лог метод, путь, статус и время обработки:

```
2026-10-19 10:38:51,778 INFO app.requests: PATCH /tasks/999 -> 404 (2.02 ms)
2026-10-19 10:38:51,842 INFO app.requests: DELETE /tasks/2 -> 204 (4.92 ms)
2026-10-19 10:38:51,869 INFO app.requests: DELETE /tasks/2 -> 404 (1.53 ms)
```

## Инструкция по запуску

Нужны Python 3.11+, Docker с Docker Compose и Git.

**1. Клонировать репозиторий**

```bash
git clone https://github.com/bpa9008-prog/fastapi-task-manager.git
cd fastapi-task-manager
```

**2. Запустить PostgreSQL и проверить доступность**

```bash
docker compose up -d db
docker compose exec db psql -U app -d tasks -c "select 1"
```

**3. Создать виртуальное окружение и установить зависимости**

```bash
python -m venv .venv
# Linux / macOS:
source .venv/bin/activate
# Windows (PowerShell):
.venv\Scripts\Activate.ps1

pip install -r requirements.txt
```

**4. Настроить переменные окружения**

Строка подключения читается из переменной `DATABASE_URL` (через pydantic-settings, также подхватывается файл `.env`):

```bash
cp .env.example .env
# DATABASE_URL=postgresql+asyncpg://app:app@localhost:5432/tasks
```

**5. Применить миграции** (таблицы создаёт Alembic, `create_all` не используется)

```bash
alembic upgrade head
```

Как создавалась миграция (повторять не нужно, она уже в репозитории):

```bash
alembic init -t async migrations
alembic revision --autogenerate -m "create users and tasks"
```

**6. Запустить сервис**

```bash
uvicorn app.main:app --reload
```

**7. Открыть Swagger UI:** <http://127.0.0.1:8000/docs>

**8. Посмотреть таблицы в БД**

```bash
docker compose exec db psql -U app -d tasks -c "\dt"
```

## Скриншоты Swagger UI

Общий вид документации:

![Swagger overview](docs/screenshots/00_swagger_overview.png)

### Пользователи

| Запрос | Результат |
|---|---|
| `POST /users` — создание | ![](docs/screenshots/01_post_users_201.png) |
| `POST /users` — email уже занят | ![](docs/screenshots/02_post_users_409.png) |
| `POST /users` — некорректный email | ![](docs/screenshots/03_post_users_422.png) |
| `GET /users/1` | ![](docs/screenshots/04_get_user_200.png) |
| `GET /users/999` — **404** | ![](docs/screenshots/05_get_user_404.png) |

### Задачи

| Запрос | Результат |
|---|---|
| `POST /tasks` — создание | ![](docs/screenshots/06_post_tasks_201.png) |
| `POST /tasks` — вторая задача | ![](docs/screenshots/07_post_tasks_201_second.png) |
| `POST /tasks` — владелец не найден, **404** | ![](docs/screenshots/08_post_tasks_404_owner.png) |
| `PATCH /tasks/1` — `{"done": true}` | ![](docs/screenshots/09_patch_task_200.png) |
| `GET /tasks?done=true&owner_id=1&limit=10&offset=0` | ![](docs/screenshots/10_list_tasks_filters_200.png) |
| `GET /tasks/1` | ![](docs/screenshots/11_get_task_200.png) |
| `GET /tasks/999` — **404** | ![](docs/screenshots/12_get_task_404.png) |
| `PATCH /tasks/999` — **404** | ![](docs/screenshots/13_patch_task_404.png) |
| `DELETE /tasks/2` | ![](docs/screenshots/14_delete_task_204.png) |
| `DELETE /tasks/2` повторно — **404** | ![](docs/screenshots/15_delete_task_404.png) |

## Таблицы в БД (`\dt` в psql)

![psql \dt](docs/screenshots/16_psql_dt.png)

## Ответы на контрольные вопросы

**1. Чем FastAPI отличается от Starlette и какие компоненты Starlette он использует?**

Starlette — лёгкий ASGI-фреймворк/тулкит. Он даёт маршрутизацию, объекты `Request`/`Response`, middleware, WebSocket, фоновые задачи, статику, тестовый клиент. Валидации данных, сериализации и автодокументации в нём нет.
FastAPI построен поверх Starlette (класс `FastAPI` наследуется от `Starlette`) и добавляет:
- объявление параметров через аннотации типов, их валидацию и преобразование средствами Pydantic;
- сериализацию ответов по `response_model`;
- систему внедрения зависимостей `Depends`;
- автоматическую генерацию OpenAPI-схемы, Swagger UI (`/docs`) и ReDoc (`/redoc`);
- утилиты безопасности (OAuth2, API keys и т. п.).

Компоненты Starlette, которые использует FastAPI: роутинг (`APIRouter`/`APIRoute` расширяют `Router`/`Route`), `Request`, `Response`, `JSONResponse` и другие ответы, middleware (`@app.middleware("http")` — это `BaseHTTPMiddleware`, а также CORS, GZip, TrustedHost), `HTTPException` (наследник Starlette-исключения) и обработчики исключений, `BackgroundTasks`, WebSocket, `StaticFiles`, события lifespan, `TestClient`.

**2. Зачем разделять схемы Create, Read и Update?**

Набор полей и правила валидации различаются в зависимости от операции:
- **Create** содержит только то, что присылает клиент при создании. В нём нет `id` и `created_at`, их генерирует БД. Обязательные поля здесь обязательны.
- **Read** описывает, что сервер отдаёт наружу. Есть `id`, `created_at`, служебных и секретных полей (например, хеша пароля) нет.
- **Update** нужен для частичного обновления: все поля необязательны (`None` по умолчанию), чтобы PATCH мог передать только изменяемые поля.

Такое разделение защищает от mass assignment: клиент не подменит `id`, `created_at` или `owner_id` там, где это запрещено. Кроме того, контракт API становится явным, а в OpenAPI-документации появляются точные схемы запросов и ответов.

**3. Что делает `from_attributes=True`?**

Разрешает Pydantic создавать модель из произвольного объекта, читая значения из его **атрибутов**, а не только из словаря. Без этой настройки `TaskRead.model_validate(orm_task)` упадёт с ошибкой. С ней Pydantic берёт `orm_task.id`, `orm_task.title` и т. д. Благодаря этому эндпоинт может вернуть ORM-объект SQLAlchemy, и FastAPI сам преобразует его в `response_model`. В Pydantic v1 эта опция называлась `orm_mode = True`.

**4. Почему сессия передаётся через `Depends`, а не создаётся глобально?**

- `AsyncSession` не потокобезопасна и не рассчитана на параллельное использование. Одна глобальная сессия на все одновременные запросы привела бы к перемешиванию транзакций, ошибкам «another operation is in progress» и утечке данных между запросами.
- Зависимость с `yield` задаёт жизненный цикл «сессия на запрос»: сессия создаётся перед обработчиком и гарантированно закрывается после ответа (даже при исключении), соединение возвращается в пул.
- Каждый запрос работает в своей транзакции, ошибка в одном запросе не ломает другие.
- В тестах зависимость легко подменить через `app.dependency_overrides[get_session]` (например, на тестовую БД) без изменения кода роутеров.
- Код роутеров не зависит от того, откуда берётся сессия (инверсия зависимостей).

**5. Чем `exclude_unset=True` отличается от `exclude_none=True`?**

- `exclude_unset=True` исключает поля, которые **не были переданы** при создании модели (остались значения по умолчанию). Явно переданный `null` в результат попадёт.
- `exclude_none=True` исключает все поля со значением **`None`**, неважно, переданы они явно или взялись из умолчания.

Пример для `TaskUpdate`, тело `{"description": null}`:
- `model_dump(exclude_unset=True)` → `{"description": None}`, описание будет очищено;
- `model_dump(exclude_none=True)` → `{}`, ничего не изменится.

Для PATCH правильно использовать `exclude_unset=True` (так и сделано в `app/routers/tasks.py`). Тогда обновляются только реально переданные поля, а необязательное поле можно явно сбросить в `null`.

**6. Почему в production таблицы не создают через `create_all`?**

- `create_all` только создаёт **отсутствующие** таблицы. Изменения существующих (новая колонка, смена типа, индекс, ограничение) он не применяет, и схема БД расходится с моделями.
- Нет версионирования: непонятно, в каком состоянии схема на конкретном сервере, нет истории изменений и нельзя откатиться (`downgrade`).
- Нельзя выполнить миграцию данных (перенос, заполнение новых колонок) вместе с изменением схемы.
- Миграции Alembic — это файлы в репозитории. Их можно проверить на code review, они одинаково применяются на всех окружениях (dev/stage/prod), а таблица `alembic_version` хранит текущую ревизию.
- Изменение схемы становится явным контролируемым шагом деплоя (`alembic upgrade head`), а не побочным эффектом запуска приложения. Это важно, когда запущено несколько экземпляров сервиса одновременно.
