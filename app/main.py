"""FastAPI application entrypoint for Maths Paper Parser."""

import utils.transport
import utils.session
import logging
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.endpoints import health
from app.api.v1.router import api_router
from app.config import settings
from app.schemas.api import ErrorResponse
from app.services.extractor import (
    EmptyModelResponseError,
    ExtractionTimeoutError,
    ExtractorError,
    GeminiConfigurationError,
    MalformedModelOutputError,
    ProviderAPIError,
    RateLimitExceededError,
    UpstreamServiceUnavailableError,
)
from app.services.preprocessor import (
    CorruptImageError,
    InvalidImageError,
    OversizedImageError,
    PreprocessorError,
    UnsupportedFormatError,
)
from app.services.pdf_processor import (
    CorruptPDFError,
    EncryptedPDFError,
    InvalidPDFPageError,
    OversizedPDFError,
    PDFPageLimitExceededError,
    PDFProcessingError,
)

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="Vision-based mathematical paper question and answer extraction API.",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # Configure CORS
    if settings.CORS_ORIGINS:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.CORS_ORIGINS,
            allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
            allow_methods=settings.CORS_ALLOW_METHODS,
            allow_headers=settings.CORS_ALLOW_HEADERS,
        )

    # Register Exception Handlers
    register_exception_handlers(app)

    # Root-level health check (for load balancers and orchestrators)
    app.include_router(health.router)

    # Versioned API routes
    app.include_router(api_router, prefix="/api/v1")

    return app


def register_exception_handlers(app: FastAPI) -> None:
    """Register custom exception handlers mapping domain exceptions to HTTP responses."""

    @app.exception_handler(OversizedImageError)
    async def oversized_image_handler(request: Request, exc: OversizedImageError) -> JSONResponse:
        return JSONResponse(
            status_code=getattr(status, "HTTP_413_CONTENT_TOO_LARGE", 413),
            content=ErrorResponse(
                success=False,
                error="OversizedImageError",
                details=str(exc),
            ).model_dump(),
        )

    @app.exception_handler(OversizedPDFError)
    async def oversized_pdf_handler(request: Request, exc: OversizedPDFError) -> JSONResponse:
        return JSONResponse(
            status_code=getattr(status, "HTTP_413_CONTENT_TOO_LARGE", 413),
            content=ErrorResponse(
                success=False,
                error="OversizedPDFError",
                details=str(exc),
            ).model_dump(),
        )

    @app.exception_handler(PDFPageLimitExceededError)
    async def pdf_page_limit_handler(request: Request, exc: PDFPageLimitExceededError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=ErrorResponse(
                success=False,
                error="PDFPageLimitExceededError",
                details=str(exc),
            ).model_dump(),
        )

    @app.exception_handler(EncryptedPDFError)
    async def encrypted_pdf_handler(request: Request, exc: EncryptedPDFError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=ErrorResponse(
                success=False,
                error="EncryptedPDFError",
                details=str(exc),
            ).model_dump(),
        )

    @app.exception_handler(CorruptPDFError)
    async def corrupt_pdf_handler(request: Request, exc: CorruptPDFError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=ErrorResponse(
                success=False,
                error="CorruptPDFError",
                details=str(exc),
            ).model_dump(),
        )

    @app.exception_handler(InvalidPDFPageError)
    async def invalid_pdf_page_handler(request: Request, exc: InvalidPDFPageError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=ErrorResponse(
                success=False,
                error="InvalidPDFPageError",
                details=str(exc),
            ).model_dump(),
        )

    @app.exception_handler(PDFProcessingError)
    async def pdf_processing_error_handler(request: Request, exc: PDFProcessingError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=ErrorResponse(
                success=False,
                error="PDFProcessingError",
                details=str(exc),
            ).model_dump(),
        )

    @app.exception_handler(UnsupportedFormatError)
    async def unsupported_format_handler(request: Request, exc: UnsupportedFormatError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            content=ErrorResponse(
                success=False,
                error="UnsupportedFormatError",
                details=str(exc),
            ).model_dump(),
        )

    @app.exception_handler(InvalidImageError)
    async def invalid_image_handler(request: Request, exc: InvalidImageError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=ErrorResponse(
                success=False,
                error="InvalidImageError",
                details=str(exc),
            ).model_dump(),
        )

    @app.exception_handler(CorruptImageError)
    async def corrupt_image_handler(request: Request, exc: CorruptImageError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=ErrorResponse(
                success=False,
                error="CorruptImageError",
                details=str(exc),
            ).model_dump(),
        )

    @app.exception_handler(PreprocessorError)
    async def preprocessor_error_handler(request: Request, exc: PreprocessorError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content=ErrorResponse(
                success=False,
                error="PreprocessorError",
                details=str(exc),
            ).model_dump(),
        )

    @app.exception_handler(RateLimitExceededError)
    async def rate_limit_handler(request: Request, exc: RateLimitExceededError) -> JSONResponse:
        logger.warning("Upstream rate limit reached: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content=ErrorResponse(
                success=False,
                error="RateLimitExceededError",
                details="Rate limit exceeded for extraction service. Please retry after a brief delay.",
            ).model_dump(),
        )

    @app.exception_handler(ExtractionTimeoutError)
    async def timeout_handler(request: Request, exc: ExtractionTimeoutError) -> JSONResponse:
        logger.warning("Extraction timed out: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            content=ErrorResponse(
                success=False,
                error="ExtractionTimeoutError",
                details="Extraction request timed out. Please try again with a clearer or smaller image.",
            ).model_dump(),
        )

    @app.exception_handler(EmptyModelResponseError)
    async def empty_response_handler(request: Request, exc: EmptyModelResponseError) -> JSONResponse:
        logger.warning("Empty model response: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content=ErrorResponse(
                success=False,
                error="EmptyModelResponseError",
                details="Upstream AI model returned an empty response. Verify the document has readable content.",
            ).model_dump(),
        )

    @app.exception_handler(MalformedModelOutputError)
    async def malformed_output_handler(request: Request, exc: MalformedModelOutputError) -> JSONResponse:
        logger.error("Malformed model output: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content=ErrorResponse(
                success=False,
                error="MalformedModelOutputError",
                details="Upstream AI model returned output that could not be validated against the schema.",
            ).model_dump(),
        )

    @app.exception_handler(UpstreamServiceUnavailableError)
    async def upstream_service_unavailable_handler(
        request: Request, exc: UpstreamServiceUnavailableError
    ) -> JSONResponse:
        logger.warning("Upstream service unavailable: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content=ErrorResponse(
                success=False,
                error="UpstreamServiceUnavailableError",
                details="The AI extraction service is temporarily unavailable. Please retry shortly.",
            ).model_dump(),
        )

    @app.exception_handler(ProviderAPIError)
    async def provider_api_error_handler(request: Request, exc: ProviderAPIError) -> JSONResponse:
        logger.error("Provider API error: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content=ErrorResponse(
                success=False,
                error="ProviderAPIError",
                details="An error occurred communicating with the upstream AI extraction provider.",
            ).model_dump(),
        )

    @app.exception_handler(GeminiConfigurationError)
    async def gemini_config_error_handler(request: Request, exc: GeminiConfigurationError) -> JSONResponse:
        logger.error("Gemini configuration error: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                success=False,
                error="ConfigurationError",
                details="Mathematical extraction service is not properly configured.",
            ).model_dump(),
        )

    @app.exception_handler(ExtractorError)
    async def extractor_error_handler(request: Request, exc: ExtractorError) -> JSONResponse:
        logger.error("Extraction error: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                success=False,
                error="ExtractorError",
                details="An error occurred during paper extraction.",
            ).model_dump(),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=getattr(status, "HTTP_422_UNPROCESSABLE_CONTENT", 422),
            content=ErrorResponse(
                success=False,
                error="ValidationError",
                details=exc.errors(),
            ).model_dump(),
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(
                success=False,
                error=exc.detail if isinstance(exc.detail, str) else "HTTPException",
                details=exc.detail if not isinstance(exc.detail, str) else None,
            ).model_dump(),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled server exception: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                success=False,
                error="InternalServerError",
                details="An unexpected server error occurred while processing the request.",
            ).model_dump(),
        )


app = create_app()
