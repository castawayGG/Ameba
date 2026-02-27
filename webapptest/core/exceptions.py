"""
Кастомные исключения для приложения.
Позволяют централизованно обрабатывать ошибки и возвращать понятные сообщения.
"""

class AppException(Exception):
    """Базовое исключение приложения."""
    def __init__(self, message: str = "An error occurred", status_code: int = 500):
        self.message = message
        self.status_code = status_code
        super().__init__(self.message)

class NotFoundException(AppException):
    """Ресурс не найден."""
    def __init__(self, message: str = "Resource not found"):
        super().__init__(message, status_code=404)

class ValidationException(AppException):
    """Ошибка валидации данных."""
    def __init__(self, message: str = "Validation error"):
        super().__init__(message, status_code=400)

class AuthenticationException(AppException):
    """Ошибка аутентификации."""
    def __init__(self, message: str = "Authentication failed"):
        super().__init__(message, status_code=401)

class AuthorizationException(AppException):
    """Недостаточно прав."""
    def __init__(self, message: str = "Access denied"):
        super().__init__(message, status_code=403)

class ConflictException(AppException):
    """Конфликт данных (например, дубликат)."""
    def __init__(self, message: str = "Conflict with existing data"):
        super().__init__(message, status_code=409)

class ProxyException(AppException):
    """Ошибка, связанная с прокси."""
    def __init__(self, message: str = "Proxy error"):
        super().__init__(message, status_code=502)

class TelegramAPIException(AppException):
    """Ошибка при работе с Telegram API."""
    def __init__(self, message: str = "Telegram API error", details: dict = None):
        self.details = details or {}
        super().__init__(message, status_code=502)

class RateLimitException(AppException):
    """Превышен лимит запросов."""
    def __init__(self, message: str = "Rate limit exceeded", retry_after: int = 60):
        self.retry_after = retry_after
        super().__init__(message, status_code=429)