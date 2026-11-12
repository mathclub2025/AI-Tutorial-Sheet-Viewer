"""Services package initialization."""

from app.extraction.services.extractor import (
    EmptyModelResponseError,
    ExtractionTimeoutError,
    ExtractorError,
    GeminiConfigurationError,
    GeminiMathExtractor,
    MalformedModelOutputError,
    ProviderAPIError,
    RateLimitExceededError,
    UpstreamServiceUnavailableError,
)
from app.extraction.services.pdf_processor import (
    CorruptPDFError,
    EncryptedPDFError,
    InvalidPDFPageError,
    OversizedPDFError,
    PDFPageLimitExceededError,
    PDFProcessingError,
    PDFProcessor,
    RenderedPDFPage,
)
from app.extraction.services.preprocessor import (
    CorruptImageError,
    ImagePreprocessor,
    InvalidImageError,
    OversizedImageError,
    PreprocessedImageResult,
    PreprocessorError,
    UnsupportedFormatError,
)

__all__ = [
    "ImagePreprocessor",
    "PreprocessedImageResult",
    "PreprocessorError",
    "InvalidImageError",
    "CorruptImageError",
    "OversizedImageError",
    "UnsupportedFormatError",
    "PDFProcessor",
    "RenderedPDFPage",
    "PDFProcessingError",
    "OversizedPDFError",
    "PDFPageLimitExceededError",
    "CorruptPDFError",
    "EncryptedPDFError",
    "InvalidPDFPageError",
    "GeminiMathExtractor",
    "ExtractorError",
    "GeminiConfigurationError",
    "EmptyModelResponseError",
    "MalformedModelOutputError",
    "RateLimitExceededError",
    "ExtractionTimeoutError",
    "ProviderAPIError",
    "UpstreamServiceUnavailableError",
]
