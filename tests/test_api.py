"""Automated tests for FastAPI endpoints (Module 4).

Tests GET /health and POST /api/v1/papers/extract using mocked services:
- Mocks both ImagePreprocessor and GeminiMathExtractor so NO Gemini API credits are consumed.
- Validates status codes, response schemas, LaTeX preservation, and null-answer rules.
- Tests input validation: JPG, JPEG, PNG, WEBP, oversized images, corrupt bytes, empty files.
- Tests exception mapping: 400, 413, 415, 422, 429, 500, 502, 504.
- Verifies that API keys, tracebacks, and internals are never leaked in error responses.
- Verifies CORS preflight and response headers.
"""

from io import BytesIO
from unittest.mock import MagicMock
import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_extractor, get_preprocessor
from app.config import settings
from app.main import app
from app.schemas.extraction import (
    PaperExtractionResult,
    QuestionItem,
    ReviewReason,
    SubQuestion,
)
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
    PreprocessedImageResult,
    UnsupportedFormatError,
)
from tests.test_preprocessor import create_synthetic_image


@pytest.fixture
def client():
    """Fixture providing a TestClient with cleanly reset dependency overrides."""
    app.dependency_overrides.clear()
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def dummy_preprocessed_result():
    """Fixture returning a preprocessed image result."""
    return PreprocessedImageResult(
        original_bytes=b"ORIGINAL_BYTES_123",
        processed_bytes=b"PROCESSED_BYTES_456",
        format="JPEG",
        mime_type="image/jpeg",
        original_dimensions=(1200, 800),
        processed_dimensions=(1200, 800),
        was_resized=False,
        exif_rotation_applied=0,
        is_preprocessed=True,
    )


# ==============================================================================
# Health Check Tests
# ==============================================================================

def test_health_check_configured(client, monkeypatch):
    """Verify GET /health returns 200 with gemini_configured=True when key is present."""
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "valid_mock_api_key_12345")
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["version"] == settings.APP_VERSION
    assert data["gemini_configured"] is True


def test_health_check_unconfigured(client, monkeypatch):
    """Verify GET /health returns gemini_configured=False when key is blank or default."""
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "")
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["gemini_configured"] is False

    monkeypatch.setattr(settings, "GEMINI_API_KEY", "your_gemini_api_key_here")
    response2 = client.get("/health")
    assert response2.json()["gemini_configured"] is False


def test_health_check_versioned_alias(client):
    """Verify GET /api/v1/health also works as an alias."""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["version"] == settings.APP_VERSION


# ==============================================================================
# Paper Extraction Success Tests (Mocked - 0 API Credits)
# ==============================================================================

def test_extract_paper_success_with_explicit_answers(client, dummy_preprocessed_result):
    """Verify POST /api/v1/papers/extract with explicit answers and LaTeX notation."""
    mock_preprocessor = MagicMock()
    mock_preprocessor.preprocess.return_value = dummy_preprocessed_result

    mock_extractor = MagicMock()
    mock_extractor.extract_from_image.return_value = PaperExtractionResult(
        paper_title="Calculus Final Exam",
        questions=[
            QuestionItem(
                question_number="1",
                question_text=r"Evaluate $\int_{0}^{1} x^2 \, dx$.",
                subquestions=[
                    SubQuestion(
                        subquestion_label="(a)",
                        text=r"Find the antiderivative $F(x)$.",
                        answer=r"$F(x) = \frac{x^3}{3}$",
                        confidence_score=0.98,
                    )
                ],
                answer=r"$\frac{1}{3}$",
                confidence_score=0.99,
            )
        ],
    )

    app.dependency_overrides[get_preprocessor] = lambda: mock_preprocessor
    app.dependency_overrides[get_extractor] = lambda: mock_extractor

    image_bytes = create_synthetic_image("JPEG", width=300, height=200)
    files = {"file": ("exam.jpg", image_bytes, "image/jpeg")}

    response = client.post("/api/v1/papers/extract", files=files)
    assert response.status_code == 200
    res_json = response.json()

    assert res_json["success"] is True
    assert res_json["processing_time_ms"] >= 0.0

    # Image metadata checks
    meta = res_json["image_metadata"]
    assert meta["filename"] == "exam.jpg"
    assert meta["content_type"] == "image/jpeg"
    assert meta["original_size_bytes"] == len(image_bytes)
    assert meta["dimensions"] == {"width": 1200, "height": 800}

    # Data checks
    data = res_json["data"]
    assert data["paper_title"] == "Calculus Final Exam"
    assert data["total_questions_detected"] == 1
    assert len(data["questions"]) == 1

    q = data["questions"][0]
    assert q["question_number"] == "1"
    assert r"\int_{0}^{1} x^2 \, dx" in q["question_text"]
    assert q["answer"] == r"$\frac{1}{3}$"
    assert q["has_explicit_answer"] is True

    sq = q["subquestions"][0]
    assert sq["subquestion_label"] == "(a)"
    assert sq["has_explicit_answer"] is True
    assert sq["answer"] == r"$F(x) = \frac{x^3}{3}$"


def test_extract_paper_unanswered_questions_remain_null(client, dummy_preprocessed_result):
    """Verify that unanswered questions have answer=null and has_explicit_answer=False."""
    mock_preprocessor = MagicMock()
    mock_preprocessor.preprocess.return_value = dummy_preprocessed_result

    mock_extractor = MagicMock()
    mock_extractor.extract_from_image.return_value = PaperExtractionResult(
        paper_title="Unanswered Problem Set",
        questions=[
            QuestionItem(
                question_number="1",
                question_text=r"Prove that $\sqrt{2}$ is irrational.",
                subquestions=[
                    SubQuestion(
                        subquestion_label="(i)",
                        text="State contradiction premise.",
                        answer=None,
                    )
                ],
                answer=None,
            )
        ],
    )

    app.dependency_overrides[get_preprocessor] = lambda: mock_preprocessor
    app.dependency_overrides[get_extractor] = lambda: mock_extractor

    image_bytes = create_synthetic_image("PNG", width=200, height=200)
    files = {"file": ("unanswered.png", image_bytes, "image/png")}

    response = client.post("/api/v1/papers/extract", files=files)
    assert response.status_code == 200
    res_json = response.json()

    q = res_json["data"]["questions"][0]
    assert q["answer"] is None
    assert q["has_explicit_answer"] is False
    assert q["subquestions"][0]["answer"] is None
    assert q["subquestions"][0]["has_explicit_answer"] is False


def test_extract_paper_with_review_flags(client, dummy_preprocessed_result):
    """Verify that human review flags and reasons are captured in output and warnings."""
    mock_preprocessor = MagicMock()
    mock_preprocessor.preprocess.return_value = dummy_preprocessed_result

    mock_extractor = MagicMock()
    mock_extractor.extract_from_image.return_value = PaperExtractionResult(
        paper_title="Messy Handwritten Quiz",
        questions=[
            QuestionItem(
                question_number="1",
                question_text="Solve $2x = 5$.",
                answer="x = 2.5?",
                confidence_score=0.55,
                needs_human_review=True,
                review_reasons=[ReviewReason.ILLEGIBLE_HANDWRITING.value],
            )
        ],
    )

    app.dependency_overrides[get_preprocessor] = lambda: mock_preprocessor
    app.dependency_overrides[get_extractor] = lambda: mock_extractor

    image_bytes = create_synthetic_image("WEBP", width=200, height=200)
    files = {"file": ("handwritten.webp", image_bytes, "image/webp")}

    response = client.post("/api/v1/papers/extract", files=files)
    assert response.status_code == 200
    res_json = response.json()

    assert res_json["data"]["requires_human_review"] is True
    assert ReviewReason.ILLEGIBLE_HANDWRITING.value in res_json["data"]["review_reasons"]
    assert any("Extraction flagged for human review" in w for w in res_json["warnings"])


# ==============================================================================
# Supported Format Tests (JPG, JPEG, PNG, WEBP)
# ==============================================================================

@pytest.mark.parametrize("fmt,ext,mime", [
    ("JPEG", "jpg", "image/jpeg"),
    ("JPEG", "jpeg", "image/jpeg"),
    ("PNG", "png", "image/png"),
    ("WEBP", "webp", "image/webp"),
])
def test_extract_supported_formats(client, fmt, ext, mime):
    """Verify all required formats (JPG, JPEG, PNG, WEBP) are accepted."""
    mock_extractor = MagicMock()
    mock_extractor.extract_from_image.return_value = PaperExtractionResult(questions=[])

    app.dependency_overrides[get_extractor] = lambda: mock_extractor

    image_bytes = create_synthetic_image(fmt, width=100, height=100)
    files = {"file": (f"test_paper.{ext}", image_bytes, mime)}

    response = client.post("/api/v1/papers/extract", files=files)
    assert response.status_code == 200
    assert response.json()["success"] is True


# ==============================================================================
# Validation & Error Mapping Tests
# ==============================================================================

def test_extract_unsupported_extension_returns_415(client):
    """Verify unsupported file extensions return HTTP 415 with ErrorResponse."""
    files = {"file": ("paper.docx", b"PK\x03\x04 dummy docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")}
    response = client.post("/api/v1/papers/extract", files=files)
    assert response.status_code == 415
    res = response.json()
    assert res["success"] is False
    assert res["error"] == "UnsupportedFormatError"
    assert "Allowed formats" in res["details"]


def test_extract_empty_file_returns_400(client):
    """Verify empty image (0 bytes) returns HTTP 400."""
    files = {"file": ("empty.jpg", b"", "image/jpeg")}
    response = client.post("/api/v1/papers/extract", files=files)
    assert response.status_code == 400
    res = response.json()
    assert res["success"] is False
    assert res["error"] == "InvalidImageError"


def test_extract_corrupt_image_returns_400(client):
    """Verify corrupted image bytes return HTTP 400."""
    corrupt_bytes = b"\xff\xd8\xff\xe0" + b"CORRUPTED_NON_IMAGE_DATA_12345"
    files = {"file": ("corrupt.jpg", corrupt_bytes, "image/jpeg")}
    response = client.post("/api/v1/papers/extract", files=files)
    assert response.status_code == 400
    res = response.json()
    assert res["success"] is False
    assert res["error"] == "CorruptImageError"


def test_extract_oversized_image_returns_413(client, monkeypatch):
    """Verify oversized image returns HTTP 413 Payload Too Large."""
    # Temporarily set max size to 1 MB for testing
    monkeypatch.setattr(settings, "MAX_IMAGE_SIZE_MB", 1)
    huge_bytes = b"X" * (2 * 1024 * 1024)  # 2 MB
    files = {"file": ("large.jpg", huge_bytes, "image/jpeg")}

    response = client.post("/api/v1/papers/extract", files=files)
    assert response.status_code == 413
    res = response.json()
    assert res["success"] is False
    assert res["error"] == "OversizedImageError"


def test_extract_missing_file_form_data_returns_422(client):
    """Verify missing file field in form returns HTTP 422 validation error."""
    response = client.post("/api/v1/papers/extract", data={"not_a_file": "value"})
    assert response.status_code == 422
    res = response.json()
    assert res["success"] is False
    assert res["error"] == "ValidationError"


# ==============================================================================
# Upstream Extraction Exception Mapping Tests
# ==============================================================================

def test_extract_rate_limit_exceeded_returns_429(client, dummy_preprocessed_result):
    """Verify RateLimitExceededError maps to HTTP 429."""
    mock_preprocessor = MagicMock()
    mock_preprocessor.preprocess.return_value = dummy_preprocessed_result
    mock_extractor = MagicMock()
    mock_extractor.extract_from_image.side_effect = RateLimitExceededError("Rate limit exceeded")

    app.dependency_overrides[get_preprocessor] = lambda: mock_preprocessor
    app.dependency_overrides[get_extractor] = lambda: mock_extractor

    files = {"file": ("paper.jpg", b"\xff\xd8\xff" + b"A"*100, "image/jpeg")}
    response = client.post("/api/v1/papers/extract", files=files)
    assert response.status_code == 429
    res = response.json()
    assert res["success"] is False
    assert res["error"] == "RateLimitExceededError"


def test_extract_timeout_returns_504(client, dummy_preprocessed_result):
    """Verify ExtractionTimeoutError maps to HTTP 504 Gateway Timeout."""
    mock_preprocessor = MagicMock()
    mock_preprocessor.preprocess.return_value = dummy_preprocessed_result
    mock_extractor = MagicMock()
    mock_extractor.extract_from_image.side_effect = ExtractionTimeoutError("Request timed out")

    app.dependency_overrides[get_preprocessor] = lambda: mock_preprocessor
    app.dependency_overrides[get_extractor] = lambda: mock_extractor

    files = {"file": ("paper.jpg", b"\xff\xd8\xff" + b"A"*100, "image/jpeg")}
    response = client.post("/api/v1/papers/extract", files=files)
    assert response.status_code == 504
    res = response.json()
    assert res["success"] is False
    assert res["error"] == "ExtractionTimeoutError"


def test_extract_empty_model_response_returns_502(client, dummy_preprocessed_result):
    """Verify EmptyModelResponseError maps to HTTP 502 Bad Gateway."""
    mock_preprocessor = MagicMock()
    mock_preprocessor.preprocess.return_value = dummy_preprocessed_result
    mock_extractor = MagicMock()
    mock_extractor.extract_from_image.side_effect = EmptyModelResponseError("Model returned empty")

    app.dependency_overrides[get_preprocessor] = lambda: mock_preprocessor
    app.dependency_overrides[get_extractor] = lambda: mock_extractor

    files = {"file": ("paper.jpg", b"\xff\xd8\xff" + b"A"*100, "image/jpeg")}
    response = client.post("/api/v1/papers/extract", files=files)
    assert response.status_code == 502
    res = response.json()
    assert res["success"] is False
    assert res["error"] == "EmptyModelResponseError"


def test_extract_malformed_model_output_returns_502(client, dummy_preprocessed_result):
    """Verify MalformedModelOutputError maps to HTTP 502 Bad Gateway."""
    mock_preprocessor = MagicMock()
    mock_preprocessor.preprocess.return_value = dummy_preprocessed_result
    mock_extractor = MagicMock()
    mock_extractor.extract_from_image.side_effect = MalformedModelOutputError("Invalid schema JSON")

    app.dependency_overrides[get_preprocessor] = lambda: mock_preprocessor
    app.dependency_overrides[get_extractor] = lambda: mock_extractor

    files = {"file": ("paper.jpg", b"\xff\xd8\xff" + b"A"*100, "image/jpeg")}
    response = client.post("/api/v1/papers/extract", files=files)
    assert response.status_code == 502
    res = response.json()
    assert res["success"] is False
    assert res["error"] == "MalformedModelOutputError"


def test_extract_provider_api_error_returns_502_sanitized(client, dummy_preprocessed_result):
    """Verify ProviderAPIError maps to HTTP 502 and never leaks secrets."""
    secret_key = "AIzaSySecretTestKey12345"
    mock_preprocessor = MagicMock()
    mock_preprocessor.preprocess.return_value = dummy_preprocessed_result
    mock_extractor = MagicMock()
    mock_extractor.extract_from_image.side_effect = ProviderAPIError(
        f"Upstream provider failed for key={secret_key}"
    )

    app.dependency_overrides[get_preprocessor] = lambda: mock_preprocessor
    app.dependency_overrides[get_extractor] = lambda: mock_extractor

    files = {"file": ("paper.jpg", b"\xff\xd8\xff" + b"A"*100, "image/jpeg")}
    response = client.post("/api/v1/papers/extract", files=files)
    assert response.status_code == 502
    res = response.json()
    assert res["success"] is False
    assert res["error"] == "ProviderAPIError"
    # Verify no secret is leaked in HTTP response body
    assert secret_key not in response.text


def test_extract_upstream_service_unavailable_returns_503_sanitized(client, dummy_preprocessed_result):
    """Verify UpstreamServiceUnavailableError maps to HTTP 503 and never leaks secrets."""
    secret_key = "AIzaSySecretTestKey12345"
    mock_preprocessor = MagicMock()
    mock_preprocessor.preprocess.return_value = dummy_preprocessed_result
    mock_extractor = MagicMock()
    mock_extractor.extract_from_image.side_effect = UpstreamServiceUnavailableError(
        f"Upstream 503 unavailable for key={secret_key}",
        status_code=503,
    )

    app.dependency_overrides[get_preprocessor] = lambda: mock_preprocessor
    app.dependency_overrides[get_extractor] = lambda: mock_extractor

    files = {"file": ("paper.jpg", b"\xff\xd8\xff" + b"A"*100, "image/jpeg")}
    response = client.post("/api/v1/papers/extract", files=files)
    assert response.status_code == 503
    res = response.json()
    assert res["success"] is False
    assert res["error"] == "UpstreamServiceUnavailableError"
    assert "temporarily unavailable" in res["details"]
    assert secret_key not in response.text


def test_extract_gemini_config_error_returns_500_sanitized(client, dummy_preprocessed_result):
    """Verify GeminiConfigurationError maps to HTTP 500 without leaking secrets."""
    mock_preprocessor = MagicMock()
    mock_preprocessor.preprocess.return_value = dummy_preprocessed_result
    mock_extractor = MagicMock()
    mock_extractor.extract_from_image.side_effect = GeminiConfigurationError("API key missing")

    app.dependency_overrides[get_preprocessor] = lambda: mock_preprocessor
    app.dependency_overrides[get_extractor] = lambda: mock_extractor

    files = {"file": ("paper.jpg", b"\xff\xd8\xff" + b"A"*100, "image/jpeg")}
    response = client.post("/api/v1/papers/extract", files=files)
    assert response.status_code == 500
    res = response.json()
    assert res["success"] is False
    assert res["error"] == "ConfigurationError"


def test_extract_generic_error_returns_500_sanitized(dummy_preprocessed_result):
    """Verify unexpected Python exception maps to HTTP 500 without stack trace."""
    mock_preprocessor = MagicMock()
    mock_preprocessor.preprocess.side_effect = RuntimeError("Unexpected internal crash in worker")

    app.dependency_overrides[get_preprocessor] = lambda: mock_preprocessor

    client = TestClient(app, raise_server_exceptions=False)
    files = {"file": ("paper.jpg", b"\xff\xd8\xff" + b"A"*100, "image/jpeg")}
    response = client.post("/api/v1/papers/extract", files=files)
    assert response.status_code == 500
    res = response.json()
    assert res["success"] is False
    assert res["error"] == "InternalServerError"
    # Ensure raw internal exception message/trace is NOT leaked
    assert "Unexpected internal crash" not in response.text
    assert "Traceback" not in response.text
    app.dependency_overrides.clear()


# ==============================================================================
# CORS Configuration Tests
# ==============================================================================

def test_cors_headers_present(client):
    """Verify CORS preflight OPTIONS request returns appropriate headers."""
    response = client.options(
        "/api/v1/papers/extract",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert response.status_code == 200
    assert "access-control-allow-origin" in response.headers
