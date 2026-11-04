"""Endpoints for mathematics paper processing and extraction."""

import time
from typing import List

from fastapi import APIRouter, Depends, File, UploadFile

from app.api.deps import get_extractor, get_pdf_processor, get_preprocessor
from app.config import settings
from app.schemas.api import (
    ErrorResponse,
    ImageMetadata,
    PaperExtractResponse,
)
from app.services.extractor import GeminiMathExtractor
from app.services.pdf_processor import PDFProcessor
from app.services.preprocessor import (
    ImagePreprocessor,
    InvalidImageError,
    OversizedImageError,
    UnsupportedFormatError,
)

router = APIRouter()


@router.post(
    "/extract",
    response_model=PaperExtractResponse,
    summary="Extract mathematics paper content",
    description=(
        "Accepts an uploaded photograph, scan, or PDF document of a mathematics exam paper or problem set "
        "(JPG, JPEG, PNG, WEBP, PDF), performs preprocessing and contrast enhancement while preserving "
        "mathematical strokes, and extracts questions, subquestions, explicit answers, and LaTeX formatting."
    ),
    responses={
        200: {"model": PaperExtractResponse, "description": "Successful extraction"},
        400: {"model": ErrorResponse, "description": "Invalid, corrupted, or encrypted document, or page limit exceeded"},
        413: {"model": ErrorResponse, "description": "Document exceeds maximum allowed size"},
        415: {"model": ErrorResponse, "description": "Unsupported document format"},
        429: {"model": ErrorResponse, "description": "Upstream rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Internal server or configuration error"},
        502: {"model": ErrorResponse, "description": "Upstream Gemini extraction failure"},
        503: {"model": ErrorResponse, "description": "Upstream AI extraction service temporarily unavailable"},
        504: {"model": ErrorResponse, "description": "Extraction timeout"},
    },
)
async def extract_paper(
    file: UploadFile = File(
        ...,
        description="Mathematics paper document file (JPG, JPEG, PNG, WEBP, or PDF)",
    ),
    preprocessor: ImagePreprocessor = Depends(get_preprocessor),
    pdf_processor: PDFProcessor = Depends(get_pdf_processor),
    extractor: GeminiMathExtractor = Depends(get_extractor),
) -> PaperExtractResponse:
    """Process uploaded paper image or PDF and extract mathematical questions and answers."""
    start_time = time.perf_counter()

    # Determine filename and validate extension
    filename = file.filename or "paper.jpg"
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in settings.ALLOWED_EXTENSIONS:
        raise UnsupportedFormatError(
            detected_format=extension or "unknown",
            allowed_formats=set(settings.ALLOWED_EXTENSIONS),
        )

    # Validate declared MIME type if provided and not generic octet-stream
    if file.content_type and file.content_type != "application/octet-stream":
        if file.content_type not in settings.ALLOWED_MIME_TYPES:
            raise UnsupportedFormatError(
                detected_format=file.content_type,
                allowed_formats=set(settings.ALLOWED_EXTENSIONS),
            )

    # Read uploaded bytes
    raw_bytes = await file.read()
    if len(raw_bytes) == 0:
        raise InvalidImageError("Uploaded file is empty (0 bytes).")

    is_pdf = (
        extension == "pdf"
        or file.content_type == "application/pdf"
        or b"%PDF-" in raw_bytes[:1024]
    )

    rendered_pages = None
    preprocessed_pages = None
    warnings: List[str] = []

    try:
        if is_pdf:
            # 1. Process and render PDF pages into images
            rendered_pages = pdf_processor.process_pdf(raw_bytes)

            # 2. Preprocess each rendered page image
            preprocessed_pages = []
            for page in rendered_pages:
                prep = preprocessor.preprocess(page.image_bytes)
                if prep.was_resized:
                    warnings.append(
                        f"Page {page.page_number} resized from {prep.original_dimensions} "
                        f"to {prep.processed_dimensions} to fit model limits."
                    )
                preprocessed_pages.append((page.page_number, prep))

            # 3. Extract across all pages and reconcile multi-page hierarchy
            extraction_result = extractor.extract_from_pdf_pages(preprocessed_pages)

            primary_dimensions = (
                rendered_pages[0].dimensions if rendered_pages else (0, 0)
            )
            image_metadata = ImageMetadata(
                filename=filename,
                content_type="application/pdf",
                original_size_bytes=len(raw_bytes),
                dimensions={
                    "width": primary_dimensions[0],
                    "height": primary_dimensions[1],
                },
                page_count=len(rendered_pages),
            )

        else:
            # Enforce image size limit before decoding
            max_img_bytes = settings.MAX_IMAGE_SIZE_MB * 1024 * 1024
            if len(raw_bytes) > max_img_bytes:
                raise OversizedImageError(size_bytes=len(raw_bytes), max_bytes=max_img_bytes)

            # Preprocess image (EXIF rotation, contrast enhancement, stroke preservation)
            preprocessed_result = preprocessor.preprocess(raw_bytes)
            if preprocessed_result.was_resized:
                warnings.append(
                    f"Image resized from {preprocessed_result.original_dimensions} "
                    f"to {preprocessed_result.processed_dimensions} to fit model limits."
                )

            # Extract questions and visible answers using Gemini Vision
            extraction_result = extractor.extract_from_image(preprocessed_result)

            image_metadata = ImageMetadata(
                filename=filename,
                content_type=preprocessed_result.mime_type,
                original_size_bytes=len(raw_bytes),
                dimensions={
                    "width": preprocessed_result.processed_dimensions[0],
                    "height": preprocessed_result.processed_dimensions[1],
                },
                page_count=1,
            )

        # Append human review warnings
        if extraction_result.requires_human_review:
            warnings.append(
                f"Extraction flagged for human review: {', '.join(extraction_result.review_reasons)}."
            )

        elapsed_ms = round((time.perf_counter() - start_time) * 1000, 2)

        return PaperExtractResponse(
            success=True,
            data=extraction_result,
            image_metadata=image_metadata,
            processing_time_ms=elapsed_ms,
            warnings=warnings,
        )

    finally:
        # Guarantee deterministic cleanup of temporary image buffers
        del raw_bytes
        if rendered_pages:
            del rendered_pages
        if preprocessed_pages:
            del preprocessed_pages

