PYTHON ?= python

.PHONY: help install web-install web-build format lint typecheck test check run docker-build docker-run

help: ## Показать список целей
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-16s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Установить пакет и инструменты разработки
	$(PYTHON) -m pip install -e ".[dev]"

web-install: ## Установить зависимости панели (npm ci)
	cd web && npm ci

web-build: ## Собрать панель в web/dist
	cd web && npm run build

format: ## Отформатировать src и tests (ruff format)
	$(PYTHON) -m ruff format src tests

lint: ## Проверить стиль (ruff check)
	$(PYTHON) -m ruff check .

typecheck: ## Проверить типы (mypy)
	$(PYTHON) -m mypy

test: ## Запустить тесты (pytest)
	$(PYTHON) -m pytest -q

check: lint typecheck test ## lint, typecheck и test подряд

run: ## Запустить API на 127.0.0.1
	$(PYTHON) -m ai_department

docker-build: ## Собрать образ ai-department
	docker build -t ai-department .

docker-run: ## Запустить контейнер на порту 8000 с томом данных
	docker run --rm -p 8000:8000 --env-file .env -v ai-department-data:/app/data ai-department
