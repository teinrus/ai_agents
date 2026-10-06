"""Ошибки контракта платформы."""

from __future__ import annotations


class PlatformError(Exception):
    """Базовая ошибка платформы."""


class ValidationError(PlatformError):
    """Вход задачи не проходит пределы платформы."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class ConfigError(PlatformError):
    """Конфигурация процесса неполна или противоречит контракту."""

    def __init__(self, variable: str, message: str | None = None) -> None:
        self.variable = variable
        self.message = message or f"Не задана переменная окружения {variable}"
        super().__init__(self.message)


class InvalidTransition(PlatformError):
    """Переход автомата отсутствует в контракте."""

    def __init__(self, source: str, target: str) -> None:
        self.source = source
        self.target = target
        super().__init__(f"Переход {source} → {target} запрещён")


class NoModelError(PlatformError):
    """Роутер не нашёл модель под требования шага."""

    def __init__(self, message: str = "Нет модели, закрывающей требования шага") -> None:
        self.message = message
        super().__init__(message)


class ProviderError(PlatformError):
    """Сбой вызова провайдера. Модель не подменяется."""

    def __init__(self, kind: str, message: str) -> None:
        self.kind = kind
        self.message = message
        super().__init__(message)


class MemoryAccessError(PlatformError):
    """Обращение к разделу памяти вне допустимой области."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class RunNotFound(PlatformError):
    """Прогон с таким run_id не существует."""

    def __init__(self, run_id: str) -> None:
        self.run_id = run_id
        super().__init__(f"Прогон {run_id} не найден")


class ThreadNotFound(PlatformError):
    """Тред с таким thread_id не существует."""

    def __init__(self, thread_id: str) -> None:
        self.thread_id = thread_id
        super().__init__(f"Тред {thread_id} не найден")


class ConfirmationError(PlatformError):
    """Ответ на подтверждение не относится к ожидающему прогону."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)
