"""One opaque error envelope; never reflect request bodies or dependency messages."""

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException


class ServiceError(Exception):
    def __init__(self, code: str, message: str, status_code: int):
        super().__init__(message)
        self.code, self.message, self.status_code = code, message, status_code


def unavailable(service: str) -> ServiceError:
    return ServiceError("DEPENDENCY_UNAVAILABLE", f"{service} is not configured or reachable", 503)


def error_response(request_id, status, code, message, details=None, headers=None):
    return JSONResponse(
        status_code=status,
        headers=headers,
        content={
            "error": code,
            "message": message,
            "request_id": request_id,
            "details": details or [],
        },
    )


async def service_error_handler(request: Request, exc: ServiceError):
    return error_response(request.state.request_id, exc.status_code, exc.code, exc.message)


async def http_error_handler(request: Request, exc: HTTPException):
    codes = {
        400: "BAD_REQUEST",
        401: "UNAUTHORIZED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        405: "METHOD_NOT_ALLOWED",
        413: "PAYLOAD_TOO_LARGE",
        503: "DEPENDENCY_UNAVAILABLE",
    }
    return error_response(
        request.state.request_id,
        exc.status_code,
        codes.get(exc.status_code, "HTTP_ERROR"),
        str(exc.detail) if isinstance(exc.detail, str) else "Request failed",
        headers=exc.headers,
    )


async def validation_error_handler(request: Request, exc: RequestValidationError):
    # Exclude input/context to avoid echoing a query, token or exception object.
    details = [
        {"location": list(e["loc"]), "type": e["type"], "message": "Invalid value"}
        for e in exc.errors()
    ]
    return error_response(
        request.state.request_id,
        422,
        "VALIDATION_ERROR",
        "Request does not match the API contract",
        details,
    )
