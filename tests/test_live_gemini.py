"""Optional live integration test with the real Gemini API.

Only executes if a valid GEMINI_API_KEY is configured in the environment (.env).
Otherwise, skips automatically to allow safe offline testing.
"""

import pytest
from app.config import settings
from app.services.extractor import GeminiMathExtractor
from app.services.preprocessor import ImagePreprocessor
from tests.test_preprocessor import create_synthetic_image


@pytest.mark.skipif(
    not settings.GEMINI_API_KEY or settings.GEMINI_API_KEY == "your_gemini_api_key_here",
    reason="Live Gemini API test skipped: GEMINI_API_KEY is not configured.",
)
def test_live_gemini_extraction():
    """Live integration test against the real Gemini API endpoint."""
    # Create synthetic test paper with a math question
    raw_bytes = create_synthetic_image("PNG", width=400, height=300, with_math_strokes=True)

    preprocessor = ImagePreprocessor()
    preprocessed = preprocessor.preprocess(raw_bytes)

    extractor = GeminiMathExtractor()
    result = extractor.extract_from_image(preprocessed)

    # Validate that structured output conforms to Pydantic schema
    assert hasattr(result, "questions")
    assert hasattr(result, "total_questions_detected")
    assert hasattr(result, "requires_human_review")
