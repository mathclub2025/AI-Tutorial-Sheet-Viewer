"""Unit tests for GeminiMathExtractor service using mocks.

Tests all extraction features without requiring network access or a live Gemini API key:
- Missing answers (null and has_explicit_answer=False)
- Explicit answers with LaTeX math notation
- Subquestions and multiple choice options
- Uncertain handwriting & ambiguous Q&A association flags
- Fallback original image selection
- Error handling: empty responses, malformed JSON, rate limits, retries, and key redaction.
"""

from unittest.mock import MagicMock
import pytest
from google.genai import errors

from app.schemas.extraction import (
    PaperExtractionResult,
    QuestionItem,
    ReviewReason,
    SubQuestion,
)
from app.services.extractor import (
    EmptyModelResponseError,
    GeminiConfigurationError,
    GeminiMathExtractor,
    MalformedModelOutputError,
    ProviderAPIError,
    RateLimitExceededError,
)
from app.services.preprocessor import PreprocessedImageResult


def create_dummy_image_result() -> PreprocessedImageResult:
    """Create a dummy PreprocessedImageResult fixture."""
    return PreprocessedImageResult(
        original_bytes=b"RAW_ORIGINAL_BYTES_12345",
        processed_bytes=b"PROCESSED_BYTES_67890",
        format="JPEG",
        mime_type="image/jpeg",
        original_dimensions=(1000, 800),
        processed_dimensions=(1000, 800),
        was_resized=False,
        exif_rotation_applied=0,
        is_preprocessed=True,
    )


class TestGeminiMathExtractor:
    """Test suite for GeminiMathExtractor with mocked GenAI client."""

    def test_missing_api_key_raises_configuration_error(self, monkeypatch):
        """Verify extractor raises GeminiConfigurationError when no key is set."""
        monkeypatch.setattr("app.config.settings.GEMINI_API_KEY", "")
        extractor = GeminiMathExtractor(api_key="")
        dummy_img = create_dummy_image_result()

        with pytest.raises(GeminiConfigurationError, match="GEMINI_API_KEY is not configured"):
            extractor.extract_from_image(dummy_img)

    def test_extraction_when_no_answers_are_written(self):
        """Verify extraction where questions exist but no answers are written on paper."""
        mock_response = MagicMock()
        mock_response.text = """{
            "paper_title": "Calculus Exam I",
            "total_questions_detected": 1,
            "questions": [
                {
                    "question_number": "1",
                    "question_text": "Evaluate the definite integral $\\\\int_{0}^{1} x^2 \\\\, dx$.",
                    "subquestions": [],
                    "answer": null,
                    "has_explicit_answer": false,
                    "confidence_score": 0.99,
                    "needs_human_review": false,
                    "review_reasons": []
                }
            ],
            "requires_human_review": false,
            "review_reasons": [],
            "notes": "Unanswered exam paper"
        }"""

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        extractor = GeminiMathExtractor(api_key="mock_key", client=mock_client)
        result = extractor.extract_from_image(create_dummy_image_result())

        assert isinstance(result, PaperExtractionResult)
        assert result.paper_title == "Calculus Exam I"
        assert len(result.questions) == 1

        q = result.questions[0]
        assert q.question_number == "1"
        assert r"\int_{0}^{1} x^2 \, dx" in q.question_text
        assert q.answer is None
        assert q.has_explicit_answer is False
        assert q.needs_human_review is False

    def test_extraction_with_explicitly_written_answer(self):
        """Verify that written answers are properly extracted and preserved in LaTeX."""
        mock_response = MagicMock()
        mock_response.text = """{
            "paper_title": "Linear Algebra Quiz",
            "total_questions_detected": 1,
            "questions": [
                {
                    "question_number": "2",
                    "question_text": "Compute the determinant of matrix $M = \\\\begin{pmatrix} 2 & 1 \\\\\\\\ 4 & 3 \\\\end{pmatrix}$.",
                    "subquestions": [],
                    "answer": "$\\\\det(M) = 2(3) - 1(4) = 2$",
                    "has_explicit_answer": true,
                    "confidence_score": 0.97,
                    "needs_human_review": false,
                    "review_reasons": []
                }
            ],
            "requires_human_review": false,
            "review_reasons": []
        }"""

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        extractor = GeminiMathExtractor(api_key="mock_key", client=mock_client)
        result = extractor.extract_from_image(create_dummy_image_result())

        q = result.questions[0]
        assert q.has_explicit_answer is True
        assert q.answer == r"$\det(M) = 2(3) - 1(4) = 2$"
        assert r"\begin{pmatrix}" in q.question_text

    def test_subquestions_and_options_extraction(self):
        """Verify multi-part subquestions and multiple-choice options are captured."""
        mock_response = MagicMock()
        mock_response.text = """{
            "paper_title": "Maths Tripos Part IA",
            "total_questions_detected": 1,
            "questions": [
                {
                    "question_number": "3",
                    "question_text": "Consider the polynomial $P(x) = x^3 - 3x + 1$. Choose the correct number of real roots: (A) 1  (B) 2  (C) 3  (D) None",
                    "subquestions": [
                        {
                            "subquestion_label": "(a)",
                            "text": "Find $P'(x)$ and determine all local extrema.",
                            "answer": "$P'(x) = 3x^2 - 3$; extrema at $x = \\\\pm 1$",
                            "has_explicit_answer": true,
                            "confidence_score": 0.95,
                            "needs_human_review": false,
                            "review_reasons": []
                        },
                        {
                            "subquestion_label": "(b)",
                            "text": "Deduce the number of real roots.",
                            "answer": null,
                            "has_explicit_answer": false,
                            "confidence_score": 0.95,
                            "needs_human_review": false,
                            "review_reasons": []
                        }
                    ],
                    "answer": "(C) 3",
                    "has_explicit_answer": true,
                    "confidence_score": 0.95,
                    "needs_human_review": false,
                    "review_reasons": []
                }
            ],
            "requires_human_review": false,
            "review_reasons": []
        }"""

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        extractor = GeminiMathExtractor(api_key="mock_key", client=mock_client)
        result = extractor.extract_from_image(create_dummy_image_result())

        q = result.questions[0]
        assert "(A) 1" in q.question_text
        assert len(q.subquestions) == 2
        assert q.subquestions[0].subquestion_label == "(a)"
        assert q.subquestions[0].has_explicit_answer is True
        assert q.subquestions[1].subquestion_label == "(b)"
        assert q.subquestions[1].has_explicit_answer is False
        assert q.subquestions[1].answer is None

    def test_uncertain_handwriting_triggers_review_flag(self):
        """Verify low confidence or uncertain handwriting sets needs_human_review."""
        mock_response = MagicMock()
        mock_response.text = """{
            "paper_title": "Student Worksheet",
            "total_questions_detected": 1,
            "questions": [
                {
                    "question_number": "4",
                    "question_text": "Solve for $y$: $\\\\frac{dy}{dx} = ky$.",
                    "subquestions": [],
                    "answer": "$y = C e^{kx}$ (?)",
                    "has_explicit_answer": true,
                    "confidence_score": 0.55,
                    "needs_human_review": true,
                    "review_reasons": ["uncertain_transcription", "illegible_handwriting"]
                }
            ],
            "requires_human_review": true,
            "review_reasons": ["uncertain_transcription", "illegible_handwriting"]
        }"""

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        extractor = GeminiMathExtractor(api_key="mock_key", client=mock_client)
        result = extractor.extract_from_image(create_dummy_image_result())

        assert result.requires_human_review is True
        assert ReviewReason.UNCERTAIN_TRANSCRIPTION.value in result.review_reasons
        assert result.questions[0].needs_human_review is True
        assert result.questions[0].confidence_score == 0.55

    def test_ambiguous_qa_association_flagged(self):
        """Verify ambiguous question-answer pairings flag the document for human review."""
        mock_response = MagicMock()
        mock_response.text = """{
            "paper_title": "Scrap Paper",
            "total_questions_detected": 1,
            "questions": [
                {
                    "question_number": "5",
                    "question_text": "Find the limit $\\\\lim_{n \\\\to \\\\infty} \\\\left(1 + \\\\frac{1}{n}\\\\right)^n$.",
                    "subquestions": [],
                    "answer": "$e$",
                    "has_explicit_answer": true,
                    "confidence_score": 0.85,
                    "needs_human_review": true,
                    "review_reasons": ["ambiguous_qa_association"]
                }
            ],
            "requires_human_review": true,
            "review_reasons": ["ambiguous_qa_association"]
        }"""

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        extractor = GeminiMathExtractor(api_key="mock_key", client=mock_client)
        result = extractor.extract_from_image(create_dummy_image_result())

        assert result.requires_human_review is True
        assert ReviewReason.AMBIGUOUS_QA_ASSOCIATION.value in result.questions[0].review_reasons

    def test_fallback_original_image_selection(self):
        """Verify use_fallback_original=True sends original_bytes rather than processed_bytes."""
        dummy_img = create_dummy_image_result()
        mock_response = MagicMock()
        mock_response.text = """{
            "paper_title": null,
            "total_questions_detected": 0,
            "questions": [],
            "requires_human_review": false,
            "review_reasons": []
        }"""

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        extractor = GeminiMathExtractor(api_key="mock_key", client=mock_client)
        extractor.extract_from_image(dummy_img, use_fallback_original=True)

        # Inspect what was passed to generate_content
        call_args = mock_client.models.generate_content.call_args
        contents = call_args.kwargs["contents"]
        image_part = contents[0]

        # The data in image_part must match dummy_img.original_bytes
        assert image_part.inline_data.data == dummy_img.original_bytes

    def test_empty_model_response_raises_error(self):
        """Verify empty model response raises EmptyModelResponseError."""
        mock_response = MagicMock()
        mock_response.text = "   "

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        extractor = GeminiMathExtractor(api_key="mock_key", client=mock_client)
        with pytest.raises(EmptyModelResponseError, match="empty response"):
            extractor.extract_from_image(create_dummy_image_result())

    def test_malformed_json_raises_error(self):
        """Verify unparseable non-JSON text raises MalformedModelOutputError."""
        mock_response = MagicMock()
        mock_response.text = "I am an AI and here is the math paper: Question 1 is 5."

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        extractor = GeminiMathExtractor(api_key="mock_key", client=mock_client)
        with pytest.raises(MalformedModelOutputError):
            extractor.extract_from_image(create_dummy_image_result())

    def test_schema_invalid_json_raises_error(self):
        """Verify JSON violating Pydantic schema (extra fields forbidden) raises MalformedModelOutputError."""
        mock_response = MagicMock()
        mock_response.text = """{
            "paper_title": "Test",
            "total_questions_detected": 0,
            "questions": [],
            "requires_human_review": false,
            "review_reasons": [],
            "extra_unauthorized_key": "hallucination"
        }"""

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        extractor = GeminiMathExtractor(api_key="mock_key", client=mock_client)
        with pytest.raises(MalformedModelOutputError, match="failed schema validation"):
            extractor.extract_from_image(create_dummy_image_result())

    def test_bounded_retries_on_rate_limit(self, monkeypatch):
        """Verify transient 429 errors trigger bounded retries before succeeding."""
        # Suppress sleep during test
        monkeypatch.setattr("time.sleep", lambda s: None)

        mock_success = MagicMock()
        mock_success.text = """{
            "paper_title": "Quiz",
            "total_questions_detected": 0,
            "questions": [],
            "requires_human_review": false,
            "review_reasons": []
        }"""

        # First call raises 429, second call succeeds
        rate_err = errors.APIError(code=429, response_json={"error": "Resource exhausted"})
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = [rate_err, mock_success]

        extractor = GeminiMathExtractor(api_key="mock_key", client=mock_client, max_retries=2)
        result = extractor.extract_from_image(create_dummy_image_result())

        assert result.paper_title == "Quiz"
        assert mock_client.models.generate_content.call_count == 2

    def test_rate_limit_exceeded_after_max_retries(self, monkeypatch):
        """Verify exhausting retries on 429 raises RateLimitExceededError."""
        monkeypatch.setattr("time.sleep", lambda s: None)

        rate_err = errors.APIError(code=429, response_json={"error": "Rate limit exceeded"})
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = rate_err

        extractor = GeminiMathExtractor(api_key="mock_key", client=mock_client, max_retries=2)
        with pytest.raises(RateLimitExceededError):
            extractor.extract_from_image(create_dummy_image_result())

        # 1 initial attempt + 2 retries = 3 calls
        assert mock_client.models.generate_content.call_count == 3

    def test_api_key_redacted_from_error_messages(self, monkeypatch):
        """Verify API keys are never exposed in exception strings."""
        secret_key = "AIzaSySecretTestKey1234567890ABCDE"
        provider_err = errors.APIError(
            code=403,
            response_json={"message": f"Invalid key={secret_key} forbidden access"},
        )

        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = provider_err

        extractor = GeminiMathExtractor(api_key=secret_key, client=mock_client)
        with pytest.raises(ProviderAPIError) as exc_info:
            extractor.extract_from_image(create_dummy_image_result())

        # Secret key MUST NOT be present in exception string
        assert secret_key not in str(exc_info.value)
        assert "[REDACTED" in str(exc_info.value)

    def test_extractor_passes_compatible_schema_without_additional_properties(self):
        """Verify that extractor passes a dict schema to GenerateContentConfig with no additionalProperties."""
        mock_response = MagicMock()
        mock_response.text = '{"paper_title": null, "total_questions_detected": 0, "questions": [], "requires_human_review": false, "review_reasons": []}'

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        extractor = GeminiMathExtractor(api_key="mock_key", client=mock_client)
        extractor.extract_from_image(create_dummy_image_result())

        # Inspect the config passed to generate_content
        call_kwargs = mock_client.models.generate_content.call_args.kwargs
        config = call_kwargs["config"]
        assert config.response_mime_type == "application/json"

        # Verify response_schema is a dict and not a raw Pydantic class
        assert isinstance(config.response_schema, dict)

        # Verify no additionalProperties exists anywhere in the schema passed to Gemini
        def check_no_additional_props(node):
            if isinstance(node, dict):
                assert "additionalProperties" not in node
                assert "additional_properties" not in node
                for v in node.values():
                    check_no_additional_props(v)
            elif isinstance(node, list):
                for x in node:
                    check_no_additional_props(x)

        check_no_additional_props(config.response_schema)

    def test_extractor_reconciles_question_hierarchy_from_model_output(self):
        """Verify GeminiMathExtractor properly reconciles compound Q2(b) output into parent Question 2."""
        mock_response = MagicMock()
        mock_response.text = """{
            "paper_title": "Probability Test",
            "total_questions_detected": 2,
            "questions": [
                {
                    "question_number": "2",
                    "question_text": "Find conditional probability P(X > 1 | X > 0.5).",
                    "subquestions": [
                        {
                            "subquestion_label": "(a)",
                            "text": "Find conditional probability P(X > 1 | X > 0.5).",
                            "answer": "3/16",
                            "has_explicit_answer": true,
                            "confidence_score": 0.95,
                            "needs_human_review": false,
                            "review_reasons": []
                        }
                    ],
                    "answer": "3/16",
                    "has_explicit_answer": true,
                    "confidence_score": 0.95,
                    "needs_human_review": false,
                    "review_reasons": []
                },
                {
                    "question_number": "2(b)",
                    "question_text": "Find CDF of Y = X^2.",
                    "subquestions": [],
                    "answer": "F_Y(y) = \\\\sqrt{y}/2",
                    "has_explicit_answer": true,
                    "confidence_score": 0.93,
                    "needs_human_review": false,
                    "review_reasons": []
                }
            ],
            "requires_human_review": false,
            "review_reasons": []
        }"""

        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response

        extractor = GeminiMathExtractor(api_key="mock_key", client=mock_client)
        result = extractor.extract_from_image(create_dummy_image_result())

        assert isinstance(result, PaperExtractionResult)
        assert result.total_questions_detected == 1
        assert len(result.questions) == 1

        parent = result.questions[0]
        assert parent.question_number == "2"
        assert parent.question_text == "Question 2"
        assert parent.answer is None
        assert parent.has_explicit_answer is False

        assert len(parent.subquestions) == 2
        assert parent.subquestions[0].subquestion_label == "(a)"
        assert parent.subquestions[0].answer == "3/16"
        assert parent.subquestions[1].subquestion_label == "(b)"
        assert parent.subquestions[1].answer == r"F_Y(y) = \sqrt{y}/2"

