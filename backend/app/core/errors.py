"""domain errors raised by usecases. mapped to http status codes in main.py."""


class AppError(Exception):
    """base for all domain errors."""


class NotFoundError(AppError):
    """resource not found by id or query."""


class ValidationError(AppError):
    """payload or input value failed validation."""


class ConflictError(AppError):
    """write would violate a uniqueness or state constraint."""


class InferenceUnavailable(AppError):
    """upstream inference service unreachable or timed out."""
