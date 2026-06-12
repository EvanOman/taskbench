"""ClickUp API exceptions."""

from typing import Any


class ClickUpError(Exception):
    """Base exception for ClickUp API errors."""

    def __init__(
        self, message: str, status_code: int | None = None, response_data: dict[str, Any] | None = None
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_data = response_data or {}


class AuthenticationError(ClickUpError):
    """Authentication failed."""

    pass


class AuthorizationError(ClickUpError):
    """Authorization failed (insufficient permissions)."""

    pass


class NotFoundError(ClickUpError):
    """Resource not found."""

    pass


class ValidationError(ClickUpError):
    """Request validation failed."""

    pass


class RateLimitError(ClickUpError):
    """API rate limit exceeded."""

    def __init__(self, message: str, retry_after: int | None = None, **kwargs: Any) -> None:
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class ServerError(ClickUpError):
    """Server error (5xx status codes)."""

    pass


class NetworkError(ClickUpError):
    """Network connectivity error."""

    pass


class RequestTimeoutError(ClickUpError):
    """Request timed out.

    Named ``RequestTimeoutError`` (not ``TimeoutError``) to avoid shadowing
    the builtin ``TimeoutError``.
    """

    pass


class ConfigurationError(ClickUpError):
    """Configuration error."""

    pass
