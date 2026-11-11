"""Gateway guard and separate server credentials; not a student identity system."""

import secrets

from fastapi import Request, Security
from fastapi.security import APIKeyHeader

from app.core.errors import ServiceError

key_header = APIKeyHeader(name="X-API-Key", auto_error=False)
internal_header = APIKeyHeader(
    name="X-Internal-Token", scheme_name="InternalServiceToken", auto_error=False
)


def check(provided, expected):
    if not expected:
        raise ServiceError("AUTH_NOT_CONFIGURED", "Service authentication is not configured", 503)
    if not provided or not secrets.compare_digest(expected.encode(), provided.encode()):
        raise ServiceError("UNAUTHORIZED", "Invalid or missing service credential", 401)


async def require_api_key(request: Request, provided: str | None = Security(key_header)):
    expected = request.app.state.settings.api_key
    if expected:
        check(provided, expected)


def internal_guard(purpose):
    async def require(request: Request, provided: str | None = Security(internal_header)):
        check(provided, request.app.state.settings.token_for(purpose))

    return require


require_dispatch_token = internal_guard("document_dispatch_token")
require_callback_token = internal_guard("ai_callback_token")
require_operations_token = internal_guard("internal_service_token")
