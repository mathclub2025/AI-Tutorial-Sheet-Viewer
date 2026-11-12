"""FastAPI dependency injection providers."""

from app.extraction.services.extractor import GeminiMathExtractor
from app.extraction.services.pdf_processor import PDFProcessor
from app.extraction.services.preprocessor import ImagePreprocessor


def get_preprocessor() -> ImagePreprocessor:
    """Dependency provider returning an ImagePreprocessor instance."""
    return ImagePreprocessor()


def get_pdf_processor() -> PDFProcessor:
    """Dependency provider returning a PDFProcessor instance."""
    return PDFProcessor()


def get_extractor() -> GeminiMathExtractor:
    """Dependency provider returning a GeminiMathExtractor instance."""
    return GeminiMathExtractor()

