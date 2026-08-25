from typing import Any


class TracebenchError(Exception):
    status_code = 500
    code = "internal_error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ConfigurationError(TracebenchError):
    code = "misconfigured"


class UnauthorizedError(TracebenchError):
    status_code = 401
    code = "unauthorized"


class NotFoundError(TracebenchError):
    status_code = 404
    code = "not_found"


class ConflictError(TracebenchError):
    status_code = 409
    code = "conflict"


class ValidationFailedError(TracebenchError):
    status_code = 422
    code = "validation_failed"


class UnsupportedMediaTypeError(TracebenchError):
    status_code = 415
    code = "unsupported_media_type"


class PayloadTooLargeError(TracebenchError):
    status_code = 413
    code = "payload_too_large"


class BackpressureError(TracebenchError):
    status_code = 503
    code = "ingest_backpressure"

    def __init__(self, message: str, *, retry_after_seconds: int = 1) -> None:
        super().__init__(message, details={"retry_after_seconds": retry_after_seconds})
        self.retry_after_seconds = retry_after_seconds
