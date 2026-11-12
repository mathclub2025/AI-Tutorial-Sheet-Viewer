"""PDF processing and page rendering service for mathematical documents.

Validates uploaded PDF files (format signature, size limits, page counts, encryption,
and page dimensions), renders pages into high-resolution PNG images suitable for
mathematical and handwriting extraction, and guarantees deterministic cleanup of all
document resources and pixmap buffers.
"""

from dataclasses import dataclass
from typing import List, Optional, Tuple

import pymupdf

from app.extraction.config import settings
from app.extraction.services.preprocessor import PreprocessorError


class PDFProcessingError(PreprocessorError):
    """Base exception for all PDF processing failures."""
    pass


class OversizedPDFError(PDFProcessingError):
    """Raised when PDF file size exceeds the configured upload limit."""

    def __init__(self, size_bytes: int, max_bytes: int) -> None:
        self.size_bytes = size_bytes
        self.max_bytes = max_bytes
        super().__init__(
            f"PDF file size ({size_bytes / (1024 * 1024):.2f} MB) exceeds maximum allowed limit of "
            f"{max_bytes / (1024 * 1024):.2f} MB."
        )


class PDFPageLimitExceededError(PDFProcessingError):
    """Raised when PDF contains more pages than the configured maximum limit."""

    def __init__(self, page_count: int, max_pages: int) -> None:
        self.page_count = page_count
        self.max_pages = max_pages
        super().__init__(
            f"PDF page count ({page_count}) exceeds maximum allowed limit of {max_pages} pages."
        )


class CorruptPDFError(PDFProcessingError):
    """Raised when PDF bytes are corrupted, incomplete, or lack a valid PDF signature."""
    pass


class EncryptedPDFError(PDFProcessingError):
    """Raised when PDF document is password-protected or encrypted."""
    pass


class InvalidPDFPageError(PDFProcessingError):
    """Raised when a PDF page has invalid, degenerate, or excessively large dimensions."""
    pass


@dataclass(frozen=True)
class RenderedPDFPage:
    """Represents a rendered PDF page converted to image format."""

    page_number: int  # 1-based page number
    image_bytes: bytes  # PNG-encoded image bytes
    dimensions: Tuple[int, int]  # (width, height) in pixels


class PDFProcessor:
    """Service for validating and rendering PDF pages into high-resolution images."""

    def __init__(
        self,
        max_size_mb: Optional[int] = None,
        max_pages: Optional[int] = None,
        render_dpi: Optional[int] = None,
        max_dimension_px: Optional[int] = None,
    ) -> None:
        self.max_size_mb = max_size_mb or settings.MAX_PDF_SIZE_MB
        self.max_pages = max_pages or settings.MAX_PDF_PAGES
        self.render_dpi = render_dpi or settings.PDF_RENDER_DPI
        self.max_dimension_px = max_dimension_px or settings.MAX_PAGE_DIMENSION_PX

    def process_pdf(self, raw_bytes: bytes) -> List[RenderedPDFPage]:
        """Validate PDF document and render all pages into high-fidelity PNG image bytes.

        Parameters:
            raw_bytes: Raw binary data of the uploaded PDF.

        Returns:
            List of RenderedPDFPage objects with 1-based page numbers and PNG image bytes.

        Raises:
            OversizedPDFError: If file size exceeds maximum limit.
            CorruptPDFError: If file is empty, lacks %PDF- header, or cannot be parsed.
            EncryptedPDFError: If file is password-protected or encrypted.
            PDFPageLimitExceededError: If page count exceeds maximum allowed limit.
            InvalidPDFPageError: If page dimensions are degenerate or excessively large.
        """
        # 1. Size constraint enforcement prior to parsing
        max_bytes = self.max_size_mb * 1024 * 1024
        if len(raw_bytes) > max_bytes:
            raise OversizedPDFError(len(raw_bytes), max_bytes)

        if len(raw_bytes) == 0:
            raise CorruptPDFError("Uploaded PDF file is empty (0 bytes).")

        # 2. PDF magic byte verification (%PDF- signature within first 1024 bytes)
        header_sample = raw_bytes[:1024]
        if b"%PDF-" not in header_sample:
            raise CorruptPDFError("File does not contain a valid PDF file signature.")

        doc: Optional[pymupdf.Document] = None
        try:
            # 3. Open PDF document in-memory
            try:
                doc = pymupdf.open(stream=raw_bytes, filetype="pdf")
            except Exception as exc:
                raise CorruptPDFError(f"Corrupted or unreadable PDF document: {exc}") from exc

            # 4. Encryption and password protection check
            if doc.is_encrypted or doc.needs_pass:
                raise EncryptedPDFError("Password-protected or encrypted PDFs are not supported.")

            # 5. Page count validation
            page_count = doc.page_count
            if page_count == 0:
                raise CorruptPDFError("PDF document contains no readable pages.")

            if page_count > self.max_pages:
                raise PDFPageLimitExceededError(page_count, self.max_pages)

            # 6. Render each page
            rendered_pages: List[RenderedPDFPage] = []
            for page_idx in range(page_count):
                page = doc.load_page(page_idx)
                rect = page.rect

                # Validate page rectangle
                if rect.width <= 0 or rect.height <= 0:
                    raise InvalidPDFPageError(
                        f"Page {page_idx + 1} has invalid degenerate dimensions: {rect.width}x{rect.height}"
                    )

                # Render page to pixmap at specified DPI
                try:
                    pix = page.get_pixmap(dpi=self.render_dpi)
                except Exception as exc:
                    raise CorruptPDFError(
                        f"Failed to render PDF page {page_idx + 1}: {exc}"
                    ) from exc

                width, height = pix.width, pix.height

                if width <= 0 or height <= 0:
                    raise InvalidPDFPageError(
                        f"Page {page_idx + 1} rendered to degenerate dimensions: {width}x{height}"
                    )

                if width > self.max_dimension_px or height > self.max_dimension_px:
                    raise InvalidPDFPageError(
                        f"Page {page_idx + 1} rendered dimensions ({width}x{height}) exceed "
                        f"maximum allowed limit of {self.max_dimension_px}px."
                    )

                # Extract lossless PNG bytes in-memory
                png_bytes = pix.tobytes("png")

                # Free pixmap buffer
                del pix

                rendered_pages.append(
                    RenderedPDFPage(
                        page_number=page_idx + 1,
                        image_bytes=png_bytes,
                        dimensions=(width, height),
                    )
                )

            return rendered_pages

        finally:
            # 7. Guaranteed deterministic document cleanup
            if doc is not None:
                try:
                    doc.close()
                except Exception:
                    pass

