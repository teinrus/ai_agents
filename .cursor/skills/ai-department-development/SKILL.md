---
name: ai-department-development
description: >-
  Guides Cursor when developing the AI Department platform of many digital
  employees: architecture, agent runtime, LLM provider abstraction, model
  router, employee skill system, memory, tools, evaluation, observability,
  security, testing, FastAPI API, React UI, and docs. Use for any design or
  implementation in this repository. Does not author runtime skills of digital
  employees; those are a separate system from Cursor skills.
---

# Разработка AI Department

Методология для Cursor. Это не скиллы цифровых сотрудников и не каркас приложения.

Платформа обслуживает много ролей. Почтовый сотрудник — первая демонстрация. Ядро его не знает.

## Перед правкой

1. Назови область работ одним словом из карты ниже.
2. Прочитай только её файл. Не загружай весь pack.
3. Сверься с `docs/architecture.md` и `docs/roadmap.md`, если они уже есть. Расхождение: сначала правка спецификации, потом код.
4. Код приложения не начинать, пока этих двух документов нет.
5. Проверь антипаттерн области. Если изменение тащит почту, IMAP или имя модели в ядро — остановись и вынеси это в плагин роли или в каталог.

## Две системы скиллов

| | Cursor | Цифровой сотрудник |
| --- | --- | --- |
| Кто читает | агент IDE | runtime платформы |
| Где лежит | `.cursor/skills/`, `.cursor/rules/` | каталог роли / плагин |
| Зачем | как писать платформу | как роль выполняет задачу |

Скилл сотрудника не создавать в `.cursor/`. Скилл Cursor не регистрировать в оркестраторе. Имя вроде `list_unread` — данные роли, не инструкция IDE.

Как устроен каталог сотрудников: [skills-system.md](skills-system.md).

## Карта

- [architecture.md](architecture.md) — границы модулей и порядок этапов
- [agent-runtime.md](agent-runtime.md) — общий цикл и оркестратор
- [llm-provider.md](llm-provider.md) — порт провайдера и адаптеры
- [model-router.md](model-router.md) — требования задачи и выбор модели
- [skills-system.md](skills-system.md) — каталог умений ролей
- [memory.md](memory.md) — разделы и сменный backend
- [tools.md](tools.md) — шлюз и политика риска
- [evaluation.md](evaluation.md) — отдельный контур оценки
- [observability.md](observability.md) — шина событий и подписчики
- [dialog.md](dialog.md) — приёмная, треды и ответ клиенту
- [security.md](security.md) — секреты, потолок риска, журнал
- [testing.md](testing.md) — что доказывает платформу
- [api-fastapi.md](api-fastapi.md) — тонкий HTTP-край
- [ui-react.md](ui-react.md) — панель как подписчик ленты
- [documentation.md](documentation.md) — какие спеки вести

## Порядок

Этап 0 — спеки. Этап 1 — ядро на моках и одна роль в конце. Этап 2 — вторая роль без копии runtime. Этап 3 — React поверх той же ленты. Этап 4 — другие реализации тех же портов. Этап 5 — приёмная: одно окно диалога поверх оркестратора.

Критерии приёмки этапов — в `docs/roadmap.md`. Пока критерии текущего этапа не закрыты, не начинай панель, облачных провайдеров и брокер.
