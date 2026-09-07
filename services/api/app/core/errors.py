"""domain errors raised by usecases. mapped to http status codes in main.py."""


class AppError(Exception):
    """base for all domain errors."""


class NotFoundError(AppError):
    """resource not found by id or query."""


class ValidationError(AppError):
    """payload or input value failed validation."""


class ConflictError(AppError):
    """write would violate a uniqueness or state constraint."""


class InferenceUnavailableError(AppError):
    """upstream inference service unreachable or timed out."""


class AlertUnavailableError(AppError):
    """upstream alert service unreachable or timed out."""


class AlertRejectedError(AppError):
    """alert service accepted the call but refused the alert."""


class AuthUnavailableError(AppError):
    """auth service unreachable or timed out during token verification."""
