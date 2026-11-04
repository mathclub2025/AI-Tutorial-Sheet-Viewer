"""Unit tests for Pydantic v2 schemas and validation logic."""

import pytest
from pydantic import ValidationError
from app.schemas.extraction import (
    PaperExtractionResult,
    QuestionItem,
    SubQuestion,
    ReviewReason,
    build_gemini_compatible_schema,
    get_gemini_extraction_schema,
)
from app.schemas.api import HealthResponse, ImageMetadata, PaperExtractResponse


def test_valid_question_with_latex_math():
    """Verify that complex mathematical notations (fractions, integrals, matrices) are preserved."""
    question = QuestionItem(
        question_number="1",
        question_text=r"Evaluate the integral $\int_{0}^{\pi} \frac{\sin(x)}{1 + x^2} \, dx$ and compute $A = \begin{pmatrix} 1 & 2 \\ 3 & 4 \end{pmatrix}^2$.",
        answer=r"$A = \begin{pmatrix} 7 & 10 \\ 15 & 22 \end{pmatrix}$",
        confidence_score=0.98,
    )
    assert question.question_number == "1"
    assert r"\int_{0}^{\pi}" in question.question_text
    assert r"\begin{pmatrix}" in question.question_text
    assert question.has_explicit_answer is True
    assert question.needs_human_review is False


def test_null_answer_requirement():
    """Verify that when no answer is written, answer is None/null and has_explicit_answer is False."""
    question = QuestionItem(
        question_number="2",
        question_text=r"Find all eigenvalues of $M = \begin{pmatrix} 0 & -1 \\ 1 & 0 \end{pmatrix}$.",
        answer=None,
    )
    assert question.answer is None
    assert question.has_explicit_answer is False

    # Also test subquestion null answer
    subq = SubQuestion(
        subquestion_label="(a)",
        text=r"Find the determinant $\det(M)$.",
        answer=None,
    )
    assert subq.answer is None
    assert subq.has_explicit_answer is False


def test_human_review_flags_on_uncertainty():
    """Verify that low confidence or ambiguous associations trigger review flags."""
    question = QuestionItem(
        question_number="3",
        question_text="Solve $x^2 + 5x + 6 = 0$.",
        answer="x = -2, -3",
        confidence_score=0.60,  # Low confidence
    )
    assert question.needs_human_review is True
    assert ReviewReason.UNCERTAIN_TRANSCRIPTION.value in question.review_reasons

    # Explicit review reasons
    question2 = QuestionItem(
        question_number="4",
        question_text=r"Calculate $\lim_{x \to 0} \frac{e^x - 1}{x}$.",
        review_reasons=[ReviewReason.AMBIGUOUS_QA_ASSOCIATION.value],
    )
    assert question2.needs_human_review is True
    assert ReviewReason.AMBIGUOUS_QA_ASSOCIATION.value in question2.review_reasons


def test_extra_fields_forbidden():
    """Verify that unexpected extra fields are rejected under strict schema validation."""
    with pytest.raises(ValidationError):
        QuestionItem(
            question_number="5",
            question_text="Solve $2x = 4$.",
            extra_hallucinated_field="invalid",  # type: ignore[call-arg]
        )


def test_document_level_review_aggregation():
    """Verify that document-level PaperExtractionResult aggregates flags from nested questions."""
    q1 = QuestionItem(
        question_number="1",
        question_text="Differentiate $f(x) = x^3$.",
        answer="$f'(x) = 3x^2$",
        confidence_score=0.99,
    )
    q2 = QuestionItem(
        question_number="2",
        question_text="Is $G$ a group under multiplication?",
        answer=None,
        subquestions=[
            SubQuestion(
                subquestion_label="(a)",
                text="Check associativity.",
                needs_human_review=True,
                review_reasons=[ReviewReason.ILLEGIBLE_HANDWRITING.value],
            )
        ],
    )

    paper = PaperExtractionResult(
        paper_title="Midterm Mathematics Exam",
        questions=[q1, q2],
    )

    assert paper.total_questions_detected == 2
    assert paper.requires_human_review is True
    assert ReviewReason.ILLEGIBLE_HANDWRITING.value in paper.review_reasons


def test_api_schemas():
    """Verify API response schemas."""
    health = HealthResponse(
        status="healthy",
        version="0.1.0",
        gemini_configured=True,
    )
    assert health.status == "healthy"
    assert health.gemini_configured is True

    img_meta = ImageMetadata(
        filename="paper.jpg",
        content_type="image/jpeg",
        original_size_bytes=102400,
        dimensions={"width": 1200, "height": 1600},
    )

    res = PaperExtractResponse(
        success=True,
        data=PaperExtractionResult(questions=[]),
        image_metadata=img_meta,
        processing_time_ms=145.2,
    )
    assert res.success is True
    assert res.processing_time_ms == 145.2


def assert_no_additional_properties(node, path="root"):
    """Recursively assert that additionalProperties and additional_properties do not exist."""
    if isinstance(node, dict):
        assert "additionalProperties" not in node, f"Found additionalProperties at {path}"
        assert "additional_properties" not in node, f"Found additional_properties at {path}"
        assert "$defs" not in node, f"Found dangling $defs at {path}"
        assert "$ref" not in node, f"Found un-inlined $ref at {path}"
        for key, val in node.items():
            assert_no_additional_properties(val, f"{path}.{key}")
    elif isinstance(node, list):
        for idx, item in enumerate(node):
            assert_no_additional_properties(item, f"{path}[{idx}]")


def test_gemini_schema_no_additional_properties_anywhere():
    """Verify that no additionalProperties or additional_properties keyword remains anywhere."""
    schema = get_gemini_extraction_schema()
    assert_no_additional_properties(schema)


def test_gemini_schema_nested_objects_and_arrays_retain_properties():
    """Verify that nested objects, arrays, and properties are correctly preserved."""
    schema = get_gemini_extraction_schema()

    assert schema["type"] == "object"
    props = schema["properties"]
    assert "paper_title" in props
    assert "total_questions_detected" in props
    assert "questions" in props
    assert "requires_human_review" in props
    assert "review_reasons" in props
    assert "notes" in props

    # Questions array
    questions = props["questions"]
    assert questions["type"] == "array"
    q_items = questions["items"]
    assert q_items["type"] == "object"
    q_props = q_items["properties"]

    expected_q_props = [
        "question_number",
        "question_text",
        "subquestions",
        "answer",
        "has_explicit_answer",
        "confidence_score",
        "needs_human_review",
        "review_reasons",
    ]
    for p in expected_q_props:
        assert p in q_props, f"Missing question property {p}"

    # Subquestions array
    subquestions = q_props["subquestions"]
    assert subquestions["type"] == "array"
    sq_items = subquestions["items"]
    assert sq_items["type"] == "object"
    sq_props = sq_items["properties"]

    expected_sq_props = [
        "subquestion_label",
        "text",
        "answer",
        "has_explicit_answer",
        "confidence_score",
        "needs_human_review",
        "review_reasons",
    ]
    for p in expected_sq_props:
        assert p in sq_props, f"Missing subquestion property {p}"


def test_gemini_schema_required_fields_preserved():
    """Verify that required fields for nested items are strictly preserved."""
    schema = get_gemini_extraction_schema()
    q_items = schema["properties"]["questions"]["items"]
    assert sorted(q_items["required"]) == ["question_number", "question_text"]

    sq_items = q_items["properties"]["subquestions"]["items"]
    assert sorted(sq_items["required"]) == ["subquestion_label", "text"]


def test_local_pydantic_validation_rejects_extra_fields():
    """Verify local Pydantic models reject unexpected fields under extra='forbid'."""
    # Top-level result rejects extra fields
    with pytest.raises(ValidationError):
        PaperExtractionResult.model_validate({"unexpected_field": "val", "questions": []})

    with pytest.raises(ValidationError):
        PaperExtractionResult.model_validate_json('{"hallucinated_property": 123, "questions": []}')

    # QuestionItem rejects extra fields
    with pytest.raises(ValidationError):
        QuestionItem.model_validate({
            "question_number": "1",
            "question_text": "text",
            "extra_field": "bad",
        })

    # SubQuestion rejects extra fields
    with pytest.raises(ValidationError):
        SubQuestion.model_validate({
            "subquestion_label": "(a)",
            "text": "text",
            "extra_field": "bad",
        })


def test_missing_answers_remain_null_in_validation():
    """Verify that missing answers remain None and has_explicit_answer is False."""
    json_data = """{
        "paper_title": "Test Paper",
        "total_questions_detected": 1,
        "questions": [
            {
                "question_number": "1",
                "question_text": "Find $x$ in $x+1=2$.",
                "subquestions": [
                    {
                        "subquestion_label": "(a)",
                        "text": "Simplify equation.",
                        "answer": null
                    }
                ],
                "answer": null
            }
        ]
    }"""
    result = PaperExtractionResult.model_validate_json(json_data)
    assert result.questions[0].answer is None
    assert result.questions[0].has_explicit_answer is False
    assert result.questions[0].subquestions[0].answer is None
    assert result.questions[0].subquestions[0].has_explicit_answer is False

    # Also test empty string gets normalized to None
    empty_str_json = """{
        "questions": [
            {
                "question_number": "2",
                "question_text": "Solve $y=3$.",
                "answer": "   "
            }
        ]
    }"""
    result_empty = PaperExtractionResult.model_validate_json(empty_str_json)
    assert result_empty.questions[0].answer is None
    assert result_empty.questions[0].has_explicit_answer is False


def test_q2_subquestions_hierarchy_regression():
    """Regression test representing the exact observed Q2(a), Q2(b) issue.

    Observed problem:
    - Question number 2 contains subquestion a, duplicating the parent question text.
    - Subquestion b is incorrectly returned as an independent top-level question '2(b)'.

    Expected output:
    - Parent question: 2
      - Subquestion a: conditional probability question, answer 3/16
      - Subquestion b: CDF of Y = X^2, answer F_Y(y) = ...
    - Parent question text does not duplicate subquestion a's text.
    - Parent answer is null (subquestion answers are preserved at subquestion level).
    """
    raw_json = """{
        "paper_title": "Probability & Statistics Exam",
        "total_questions_detected": 2,
        "questions": [
            {
                "question_number": "2",
                "question_text": "Find the conditional probability $P(X > 1 \\\\mid X > 0.5)$ for the given continuous random variable.",
                "subquestions": [
                    {
                        "subquestion_label": "(a)",
                        "text": "Find the conditional probability $P(X > 1 \\\\mid X > 0.5)$ for the given continuous random variable.",
                        "answer": "3/16",
                        "has_explicit_answer": true,
                        "confidence_score": 0.95
                    }
                ],
                "answer": "3/16",
                "has_explicit_answer": true,
                "confidence_score": 0.95
            },
            {
                "question_number": "2(b)",
                "question_text": "Find the cumulative distribution function (CDF) of $Y = X^2$.",
                "subquestions": [],
                "answer": "$F_Y(y) = \\\\frac{\\\\sqrt{y}}{2}, \\\\quad 0 \\\\le y \\\\le 4$",
                "has_explicit_answer": true,
                "confidence_score": 0.92
            }
        ]
    }"""
    result = PaperExtractionResult.model_validate_json(raw_json)

    # 1. Total top-level questions should now be 1
    assert result.total_questions_detected == 1
    assert len(result.questions) == 1

    q2 = result.questions[0]
    assert q2.question_number == "2"

    # 2. Parent text must not duplicate subquestion (a)'s text
    assert q2.question_text == "Question 2"

    # 3. Parent answer must be null, preserved on subquestions
    assert q2.answer is None
    assert q2.has_explicit_answer is False

    # 4. Both subquestions are preserved under parent 2
    assert len(q2.subquestions) == 2

    sq_a = q2.subquestions[0]
    assert sq_a.subquestion_label == "(a)"
    assert "$P(X > 1 \\mid X > 0.5)$" in sq_a.text
    assert sq_a.answer == "3/16"
    assert sq_a.has_explicit_answer is True

    sq_b = q2.subquestions[1]
    assert sq_b.subquestion_label == "(b)"
    assert "(CDF) of $Y = X^2$" in sq_b.text
    assert sq_b.answer == r"$F_Y(y) = \frac{\sqrt{y}}{2}, \quad 0 \le y \le 4$"
    assert sq_b.has_explicit_answer is True


def test_standalone_subquestion_grouped_under_preceding_parent():
    """Verify standalone subquestion '(b)' or 'b' groups under preceding parent Question 2."""
    raw_json = """{
        "questions": [
            {
                "question_number": "2",
                "question_text": "Let $X$ have density $f(x) = 2x$. (a) Find $E[X]$.",
                "subquestions": [
                    {
                        "subquestion_label": "(a)",
                        "text": "Find $E[X]$.",
                        "answer": "2/3"
                    }
                ]
            },
            {
                "question_number": "(b)",
                "question_text": "Find $Var(X)$.",
                "answer": "1/18"
            }
        ]
    }"""
    result = PaperExtractionResult.model_validate_json(raw_json)
    assert result.total_questions_detected == 1
    q2 = result.questions[0]
    assert q2.question_number == "2"
    # Shared preamble is preserved
    assert "Let $X$ have density $f(x) = 2x$." in q2.question_text
    assert len(q2.subquestions) == 2
    assert q2.subquestions[0].subquestion_label == "(a)"
    assert q2.subquestions[0].answer == "2/3"
    assert q2.subquestions[1].subquestion_label == "(b)"
    assert q2.subquestions[1].answer == "1/18"


def test_ambiguous_hierarchy_flags_human_review():
    """Verify ambiguous subquestion with no identifiable parent is flagged for human review."""
    raw_json = """{
        "questions": [
            {
                "question_number": "(c)",
                "question_text": "Calculate the residual sum of squares.",
                "answer": "12.4"
            }
        ]
    }"""
    result = PaperExtractionResult.model_validate_json(raw_json)
    assert result.total_questions_detected == 1
    q = result.questions[0]
    assert q.needs_human_review is True
    assert ReviewReason.AMBIGUOUS_QUESTION_HIERARCHY.value in q.review_reasons
    assert result.requires_human_review is True
    assert ReviewReason.AMBIGUOUS_QUESTION_HIERARCHY.value in result.review_reasons


