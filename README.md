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
