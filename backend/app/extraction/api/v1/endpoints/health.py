"""Health check endpoint."""

from fastapi import APIRouter

from app.extraction.config import settings
from app.extraction.schemas.api import HealthResponse

router = APIRouter()


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Check the service status, version, and whether Gemini API is configured.",
    tags=["Health"],
)
async def health_check() -> HealthResponse:
    """Return API health status and configuration info."""
    api_key_configured = bool(
        settings.GEMINI_API_KEY
        and settings.GEMINI_API_KEY.strip()
        and settings.GEMINI_API_KEY != "your_gemini_api_key_here"
    )
    return HealthResponse(
        status="healthy",
        version=settings.APP_VERSION,
        gemini_configured=api_key_configured,
    )

