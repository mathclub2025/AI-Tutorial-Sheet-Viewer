"""Unit tests for Gemini extractor reliability, exponential backoff, jitter, and fallback.

Validates:
1. Primary model succeeds immediately without fallback.
2. Bounded retries on transient errors (503, 500, 502, 504) on primary model before recovery.
3. Fallback model attempted at most once upon exhausting primary retries during outages.
4. Permanent 4xx errors (400, 401, 403) abort immediately without retry or fallback.
5. 429 rate limit errors retry with backoff and raise RateLimitExceededError if exhausted.
6. Model not found (404) immediately transitions to fallback model.
7. Retry-After header and RetryInfo extraction and enforcement.
8. Bounded exponential backoff with jitter calculation.
9. Maximum total retry duration budget enforcement.
10. Automatic Function Calling (AFC) disabled in configuration.
11. Secret API keys redacted in all upstream error messages.
"""

from unittest.mock import MagicMock
import pytest
from google.genai import errors, types

from app.schemas.extraction import PaperExtractionResult
from app.services.extractor import (
    ExtractionTimeoutError,
    GeminiMathExtractor,
    ProviderAPIError,
    RateLimitExceededError,
    UpstreamServiceUnavailableError,
)
from app.services.preprocessor import PreprocessedImageResult


def create_dummy_image_result() -> PreprocessedImageResult:
    """Create a dummy PreprocessedImageResult for testing."""
    return PreprocessedImageResult(
        original_bytes=b"DUMMY_ORIGINAL_BYTES_12345",
        processed_bytes=b"DUMMY_PROCESSED_BYTES_67890",
        format="JPEG",
        mime_type="image/jpeg",
        original_dimensions=(1000, 800),
        processed_dimensions=(1000, 800),
        was_resized=False,
        exif_rotation_applied=0,
        is_preprocessed=True,
    )


def create_dummy_success_response(title: str = "Test Paper") -> MagicMock:
    """Create a mock model response with valid minimal JSON."""
    mock_resp = MagicMock()
    mock_resp.text = f"""{{
        "paper_title": "{title}",
        "total_questions_detected": 1,
        "questions": [
            {{
                "question_number": "1",
                "question_text": "Find $x$ if $2x + 1 = 5$.",
                "subquestions": [],
                "answer": "$x = 2$",
                "has_explicit_answer": true,
                "confidence_score": 0.98,
                "needs_human_review": false,
                "review_reasons": []
            }}
        ],
        "requires_human_review": false,
        "review_reasons": []
    }}"""
    return mock_resp


class TestGeminiExtractorReliability:
    """Test suite for Gemini upstream reliability, fallback, and retry strategies."""

    def test_primary_model_succeeds_immediately(self):
        """Verify that when primary model succeeds, no retries or fallbacks occur."""
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = create_dummy_success_response()

        extractor = GeminiMathExtractor(
            api_key="mock_key",
            model="gemini-3.1-flash-lite",
            fallback_model="gemini-2.5-flash",
            max_retries=2,
            client=mock_client,
        )

        result = extractor.extract_from_image(create_dummy_image_result())

        assert isinstance(result, PaperExtractionResult)
        assert result.paper_title == "Test Paper"
        assert mock_client.models.generate_content.call_count == 1
        call_kwargs = mock_client.models.generate_content.call_args.kwargs
        assert call_kwargs["model"] == "gemini-3.1-flash-lite"

    def test_primary_503_recovers_after_retry(self, monkeypatch):
        """Verify transient 503 triggers bounded retries on primary model then succeeds."""
        monkeypatch.setattr("time.sleep", lambda s: None)

        err_503 = errors.APIError(code=503, response_json={"error": "Service Unavailable"})
        mock_success = create_dummy_success_response("Recovered Paper")

        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = [err_503, mock_success]

        extractor = GeminiMathExtractor(
            api_key="mock_key",
            model="gemini-3.1-flash-lite",
            fallback_model="gemini-2.5-flash",
            max_retries=2,
            client=mock_client,
        )

        result = extractor.extract_from_image(create_dummy_image_result())

        assert result.paper_title == "Recovered Paper"
        assert mock_client.models.generate_content.call_count == 2
        # Both calls were on the primary model
        for call in mock_client.models.generate_content.call_args_list:
            assert call.kwargs["model"] == "gemini-3.1-flash-lite"

    def test_primary_and_fallback_both_503_raises_upstream_unavailable(self, monkeypatch):
        """Verify exhausting primary retries triggers ONE fallback, which on 503 raises UpstreamServiceUnavailableError."""
        monkeypatch.setattr("time.sleep", lambda s: None)

        err_503 = errors.APIError(code=503, response_json={"error": "The service is temporarily overloaded"})
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = err_503

        extractor = GeminiMathExtractor(
            api_key="mock_key",
            model="gemini-3.1-flash-lite",
            fallback_model="gemini-2.5-flash",
            max_retries=1,  # 1 initial + 1 retry = 2 attempts per model
            client=mock_client,
        )

        with pytest.raises(UpstreamServiceUnavailableError) as exc_info:
            extractor.extract_from_image(create_dummy_image_result())

        assert exc_info.value.status_code == 503
        assert "temporarily unavailable" in str(exc_info.value).lower()

        # Total calls = (1 initial + 1 retry) on primary + (1 initial + 1 retry) on fallback = 4
        assert mock_client.models.generate_content.call_count == 4
        calls = mock_client.models.generate_content.call_args_list
        assert calls[0].kwargs["model"] == "gemini-3.1-flash-lite"
        assert calls[1].kwargs["model"] == "gemini-3.1-flash-lite"
        assert calls[2].kwargs["model"] == "gemini-2.5-flash"
        assert calls[3].kwargs["model"] == "gemini-2.5-flash"

    def test_permanent_4xx_aborts_immediately_without_retries(self, monkeypatch):
        """Verify permanent 400/401/403 errors are never retried and never switch to fallback."""
        mock_sleep = MagicMock()
        monkeypatch.setattr("time.sleep", mock_sleep)

        # 400: Invalid Argument / schema mismatch
        err_400 = errors.APIError(code=400, response_json={"error": "Invalid argument: bad schema"})
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = err_400

        extractor = GeminiMathExtractor(
            api_key="mock_key",
            model="gemini-3.1-flash-lite",
            fallback_model="gemini-2.5-flash",
            max_retries=2,
            client=mock_client,
        )

        with pytest.raises(ProviderAPIError) as exc_info:
            extractor.extract_from_image(create_dummy_image_result())

        assert exc_info.value.status_code == 400
        # Exactly 1 call was made — NO retries, NO fallback attempt
        assert mock_client.models.generate_content.call_count == 1
        assert mock_sleep.call_count == 0

    def test_invalid_api_key_403_aborts_immediately(self, monkeypatch):
        """Verify 403 / unauthenticated errors abort immediately."""
        mock_sleep = MagicMock()
        monkeypatch.setattr("time.sleep", mock_sleep)

        err_403 = errors.APIError(code=403, response_json={"error": "API key not valid. Please pass a valid API key."})
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = err_403

        extractor = GeminiMathExtractor(
            api_key="mock_key",
            model="gemini-3.1-flash-lite",
            fallback_model="gemini-2.5-flash",
            max_retries=2,
            client=mock_client,
        )

        with pytest.raises(ProviderAPIError) as exc_info:
            extractor.extract_from_image(create_dummy_image_result())

        assert exc_info.value.status_code == 403
        assert mock_client.models.generate_content.call_count == 1
        assert mock_sleep.call_count == 0

    def test_transient_429_rate_limit_retries_and_succeeds(self, monkeypatch):
        """Verify transient 429 rate limit retries with backoff and recovers."""
        monkeypatch.setattr("time.sleep", lambda s: None)

        err_429 = errors.APIError(code=429, response_json={"error": "Resource exhausted: quota exceeded"})
        mock_success = create_dummy_success_response("Recovered 429")

        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = [err_429, mock_success]

        extractor = GeminiMathExtractor(
            api_key="mock_key",
            model="gemini-3.1-flash-lite",
            max_retries=2,
            client=mock_client,
        )

        result = extractor.extract_from_image(create_dummy_image_result())
        assert result.paper_title == "Recovered 429"
        assert mock_client.models.generate_content.call_count == 2

    def test_transient_429_exhausted_raises_rate_limit_error(self, monkeypatch):
        """Verify exhausting retries on 429 raises RateLimitExceededError and does not loop."""
        monkeypatch.setattr("time.sleep", lambda s: None)

        err_429 = errors.APIError(code=429, response_json={"error": "Resource exhausted: quota exceeded"})
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = err_429

        extractor = GeminiMathExtractor(
            api_key="mock_key",
            model="gemini-3.1-flash-lite",
            fallback_model="gemini-2.5-flash",
            max_retries=2,
            client=mock_client,
        )

        with pytest.raises(RateLimitExceededError):
            extractor.extract_from_image(create_dummy_image_result())

        # 1 initial + 2 retries = 3 calls on the primary model; no fallback cascading
        assert mock_client.models.generate_content.call_count == 3
        for call in mock_client.models.generate_content.call_args_list:
            assert call.kwargs["model"] == "gemini-3.1-flash-lite"

    def test_model_404_transitions_to_fallback(self):
        """Verify 404 (model not found) immediately switches to fallback model."""
        err_404 = errors.APIError(code=404, response_json={"error": "models/deprecated-model is not found"})
        mock_success = create_dummy_success_response("Fallback Success")

        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = [err_404, mock_success]

        extractor = GeminiMathExtractor(
            api_key="mock_key",
            model="deprecated-model",
            fallback_model="gemini-2.5-flash",
            max_retries=2,
            client=mock_client,
        )

        result = extractor.extract_from_image(create_dummy_image_result())
        assert result.paper_title == "Fallback Success"
        assert mock_client.models.generate_content.call_count == 2
        calls = mock_client.models.generate_content.call_args_list
        assert calls[0].kwargs["model"] == "deprecated-model"
        assert calls[1].kwargs["model"] == "gemini-2.5-flash"

    def test_retry_after_extraction_variants(self):
        """Verify Retry-After is correctly parsed from headers, RetryInfo, and messages."""
        extractor = GeminiMathExtractor(api_key="mock_key")

        # 1. From response headers (numeric seconds)
        class MockErrWithHeaders(Exception):
            response = MagicMock(headers={"retry-after": "5.5"})

        assert extractor._extract_retry_after(MockErrWithHeaders()) == 5.5

        # 2. From response_json RPC RetryInfo
        class MockErrWithRetryInfo(Exception):
            response_json = {
                "error": {
                    "code": 429,
                    "details": [
                        {
                            "@type": "type.googleapis.com/google.rpc.RetryInfo",
                            "retryDelay": "8.0s",
                        }
                    ],
                }
            }

        assert extractor._extract_retry_after(MockErrWithRetryInfo()) == 8.0

        # 3. From error message text regex
        err_msg = Exception("Resource exhausted, please retry after 3.2s")
        assert extractor._extract_retry_after(err_msg) == 3.2

        # 4. None when no retry-after information is present
        assert extractor._extract_retry_after(Exception("Generic error")) is None

    def test_backoff_delay_calculation_with_jitter(self):
        """Verify backoff delay uses bounded exponential growth with jitter."""
        extractor = GeminiMathExtractor(
            api_key="mock_key",
            base_retry_delay=1.0,
            max_retry_delay=8.0,
        )

        # Attempt 1: exp_delay = 1.0 -> jitter between [0.5, 1.0]
        for _ in range(20):
            delay = extractor._calculate_backoff_delay(retry_num=1)
            assert 0.5 <= delay <= 1.0

        # Attempt 2: exp_delay = 2.0 -> jitter between [1.0, 2.0]
        for _ in range(20):
            delay = extractor._calculate_backoff_delay(retry_num=2)
            assert 1.0 <= delay <= 2.0

        # Attempt 5: exp_delay = min(8.0, 16.0) = 8.0 -> jitter between [4.0, 8.0]
        for _ in range(20):
            delay = extractor._calculate_backoff_delay(retry_num=5)
            assert 4.0 <= delay <= 8.0

        # With explicit Retry-After of 3.0s: capped at max_delay, includes small jitter
        for _ in range(20):
            delay = extractor._calculate_backoff_delay(retry_num=1, retry_after=3.0)
            assert 3.0 <= delay <= 3.5

    def test_total_retry_duration_budget_exhaustion(self, monkeypatch):
        """Verify exceeding total retry duration budget raises UpstreamServiceUnavailableError/Timeout."""
        monkeypatch.setattr("time.sleep", lambda s: None)

        err_503 = errors.APIError(code=503, response_json={"error": "Service Unavailable"})
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = err_503

        # Configure an almost-zero budget so first retry exceeds budget
        extractor = GeminiMathExtractor(
            api_key="mock_key",
            model="gemini-3.1-flash-lite",
            max_retries=5,
            max_total_retry_duration=0.001,
            client=mock_client,
        )

        # Force monotonic time to jump on second check
        real_monotonic = [0.0, 0.05, 0.1, 0.2]
        time_iter = iter(real_monotonic)
        monkeypatch.setattr("time.monotonic", lambda: next(time_iter, 10.0))

        with pytest.raises((UpstreamServiceUnavailableError, ExtractionTimeoutError)):
            extractor.extract_from_image(create_dummy_image_result())

    def test_automatic_function_calling_disabled_in_config(self):
        """Verify Automatic Function Calling is explicitly disabled to avoid AFC warning."""
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = create_dummy_success_response()

        extractor = GeminiMathExtractor(
            api_key="mock_key",
            client=mock_client,
        )

        extractor.extract_from_image(create_dummy_image_result())

        call_kwargs = mock_client.models.generate_content.call_args.kwargs
        config = call_kwargs["config"]

        # automatic_function_calling must be configured with disable=True
        assert config.automatic_function_calling is not None
        assert config.automatic_function_calling.disable is True

    def test_api_key_sanitized_in_upstream_unavailable_error(self, monkeypatch):
        """Verify API keys are redacted when UpstreamServiceUnavailableError is raised."""
        monkeypatch.setattr("time.sleep", lambda s: None)

        secret_key = "AIzaSySuperSecretKey9988776655"
        err_503 = errors.APIError(
            code=503,
            response_json={"error": f"Service unavailable for key={secret_key}"},
        )
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = err_503

        extractor = GeminiMathExtractor(
            api_key=secret_key,
            model="gemini-3.1-flash-lite",
            fallback_model=None,
            max_retries=1,
            client=mock_client,
        )

        with pytest.raises(UpstreamServiceUnavailableError) as exc_info:
            extractor.extract_from_image(create_dummy_image_result())

        err_str = str(exc_info.value)
        assert secret_key not in err_str
        assert "[REDACTED" in err_str

