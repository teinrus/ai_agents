# AI Department

Платформа цифровых сотрудников. Клиент пишет в одно окно — приёмную; она разбирает сообщение, передаёт задачу подходящему сотруднику, следит за подтверждением рискованных действий и возвращает ответ по итогам прогона. Сотрудник — плагин роли; ядро ни одной роли не знает.

Первая демонстрационная роль — почтовый сотрудник (`mail`): читает непрочитанные письма, открывает их целиком, готовит черновики ответов, отправляет письма только с разрешения человека. Вторая — учёт записей (`records`).

## Что внутри

- **Оркестратор** — не LLM. Выбирает роль по `score`, ведёт один автомат состояний для всех ролей, передаёт итог на оценку. `WaitingConfirmation` обойти нельзя.
- **Runtime** — общий цикл шагов агента: модель → инструмент → модель … → итог. Не ветвится по роли.
- **Роутер моделей** — агент заявляет требования шага (`reasoning | coding | tools`, `cheap | fast | long_context`), имя модели подбирается по каталогу. Роль имён моделей не знает.
- **Шлюз инструментов** — единственный путь к обработчику. Аргументы проверяются по JSON-схеме, политика отвечает `allow | confirm | deny` по уровням риска `read < draft < act < destructive`. `act` требует одноразового подтверждения человека.
- **Оценка** — отдельный контур. Без пройденной проверки итог клиенту не уходит: схема вывода, лимит шагов, подтверждения `act`, потолок риска, след инструментов (`tool_evidence`).
- **Память** — разделы `run`, `agent`, `department`; чужой `run` закрыт.
- **Шина событий** — общий конверт для лога, счётчиков и панели.
- **Приёмная и треды** — одно окно диалога поверх оркестратора.
- **API** — тонкий FastAPI-край. **Панель** — React, один чат с кнопками подтверждения и подробностями прогона.

Полный контракт — в [`docs/architecture.md`](docs/architecture.md). Этапы и критерии приёмки — в [`docs/roadmap.md`](docs/roadmap.md).

## Быстрый старт

Нужны Python 3.12+ и Node.js 20+ (только для сборки панели).

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate ; Linux/macOS: source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
python -m ai_department
```

API поднимается на `http://127.0.0.1:8000`. С настройками из `.env.example` платформа работает на моках: модель — `MockLlmProvider`, ящик — в памяти процесса, сеть не открывается.

Панель:

```bash
cd web
npm install
npm run build
```

После сборки откройте `http://127.0.0.1:8000/` — API отдаёт панель с того же адреса. Для разработки `npm run dev` поднимает Vite на `5173` с прокси на API.

## Живой запуск

Локальная модель через OpenAI-совместимый endpoint (например, Ollama):

```env
LLM_ADAPTER=local
LOCAL_LLM_BASE_URL=http://127.0.0.1:11434/v1
LOCAL_LLM_API_KEY=ollama
LOCAL_LLM_MODEL=<имя модели в Ollama>
```

Почтовый ящик по IMAP/SMTP:

```env
ENABLED_ROLES=mail
MAILBOX_BACKEND=imap
IMAP_HOST=imap.yandex.ru
IMAP_USER=you@yandex.ru
IMAP_PASSWORD=<пароль приложения>
SMTP_HOST=smtp.yandex.ru
```

Секреты только через окружение или `.env`; `.env` в репозиторий не входит. Диалоги по умолчанию живут в памяти процесса. Чтобы пережить перезапуск, задайте `THREADS_BACKEND=sqlite` и при необходимости `THREADS_SQLITE_PATH=data/threads.db`. Что умеет почтовый сотрудник и как это проверялось на живом ящике — в [`docs/mail-role.md`](docs/mail-role.md).

## HTTP API

| Метод | Путь | Смысл |
| --- | --- | --- |
| `GET` | `/health` | Адаптеры, число моделей каталога, роли и состояния сотрудников. Секретов нет |
| `POST` | `/threads` | Открыть тред |
| `GET` | `/threads` | Список диалогов: новые сверху, без тел сообщений |
| `GET` | `/threads/{thread_id}` | Сообщения, прогоны, ожидающее подтверждение |
| `POST` | `/threads/{thread_id}/messages` | Написать в тред, получить ответ приёмной |
| `POST` | `/threads/{thread_id}/confirmations` | `approve` или `reject` ожидающего действия |
| `GET` | `/threads/{thread_id}/events` | События треда |
| `POST` | `/tasks` | Поставить задачу напрямую, минуя приёмную |
| `GET` | `/runs/{run_id}` | Состояние прогона |
| `GET` | `/runs/{run_id}/events` | Лента прогона |
| `POST` | `/runs/{run_id}/confirmations` | Подтверждение на уровне прогона |

Пример диалога:

```bash
curl -X POST http://127.0.0.1:8000/threads
curl -X POST http://127.0.0.1:8000/threads/<thread_id>/messages \
  -H "Content-Type: application/json" \
  -d '{"text": "Посмотри непрочитанные письма и расскажи, от кого они"}'
```

## Структура

```
docs/                 контракт платформы и дорожная карта
src/ai_department/    ядро: domain, orchestrator, runtime, evaluation, memory,
                      tools, llm, events, observability, dialog, api
src/roles/<role_id>/  плагины ролей: mail, records, clerk (тестовая)
tests/unit            чистые решения: политика, роутер, оценщик, разбор
tests/integration     прогоны на моках через оркестратор и API
web/                  панель на React + Vite
Dockerfile            образ: панель и API
Makefile              цели install, check, run, docker
.cursor/              методология разработки для Cursor (не runtime)
```

## Запуск в Docker и через make

Локально через make:

```bash
make install
make web-build
make run
```

Проверки: `make check` (ruff, mypy, pytest).

Контейнер:

```bash
docker build -t ai-department .
docker run --rm -p 8000:8000 --env-file .env ai-department
```

В контейнере сервер слушает `0.0.0.0:8000`. Данные (SQLite, журнал событий) живут в томе `/app/data` — в `.env` указывайте пути внутри `data/`. Для постоянного тома: `make docker-run` (монтирует `ai-department-data` в `/app/data`).

## Разработка

```bash
ruff format src tests
ruff check .
mypy
pytest -q
```

Тесты ядра идут на моках и не открывают сеть. Коммиты — Conventional Commits.

Правила, которые держат платформу платформой, а не одним агентом:

- Сначала контракт в `docs/`, потом код. Поведения, которого нет в спеке, в коде нет.
- Ядро не импортирует роли и не содержит типов письма, ящика, IMAP, SMTP.
- Новая роль — плагин. Если ради неё пришлось менять оркестратор или runtime, контракт платформы неверен.
- Две системы скиллов не смешиваются: `.cursor/skills/` читает IDE, скиллы сотрудников живут в плагинах ролей.

## Документация

- [`docs/architecture.md`](docs/architecture.md) — контракты: автомат, статусы, роутер, инструменты и риск, оценка, память, события, безопасность, API, приёмная.
- [`docs/roadmap.md`](docs/roadmap.md) — этапы 0–6 с критериями приёмки.
- [`docs/mail-role.md`](docs/mail-role.md) — почтовый сотрудник: возможности, настройка, результаты живой проверки, ограничения.
- [`.cursor/skills/ai-department-development/`](.cursor/skills/ai-department-development/SKILL.md) — метод разработки по областям.

## Статус

Этапы 0–6 дорожной карты закрыты: ядро на моках, две роли, панель, адаптеры local/cloud/sqlite/shared, приёмная, живой прогон почтовой роли на локальной модели. Вне плана: уровень `destructive`, оценщик качества на модели, сохранение тредов между запусками.
