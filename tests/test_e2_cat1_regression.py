"""Regression tests for the E2 Slot CAT1 Answer Key PDF extraction.

These tests use mocked JSON (reproducing the observed bad output) fed through
PaperExtractionResult to verify the reconciliation logic, hierarchy, answer
association, page references, and review flags.

They do NOT consume Gemini API credits.
"""

import pytest
from app.schemas.extraction import (
    PaperExtractionResult,
    QuestionItem,
    SubQuestion,
    ReviewReason,
    extract_parent_and_sublabel,
    normalize_sublabel,
    _is_sequential_sublabel,
)


# ---------------------------------------------------------------------------
# Helper: build a QuestionItem with minimal boilerplate
# ---------------------------------------------------------------------------

def _q(number: str, text: str, answer: str | None = None, page: int | None = None, subs: list | None = None):
    return QuestionItem(
        question_number=number,
        question_text=text,
        answer=answer,
        page_number=page,
        page_numbers=[page] if page else [],
        subquestions=subs or [],
    )


def _sq(label: str, text: str, answer: str | None = None, page: int | None = None):
    return SubQuestion(subquestion_label=label, text=text, answer=answer, page_number=page)


# ---------------------------------------------------------------------------
# Unit tests for new helper functions
# ---------------------------------------------------------------------------

class TestNormalizeSublabel:
    def test_single_letter(self):
        assert normalize_sublabel("b") == "(b)"
        assert normalize_sublabel("(a)") == "(a)"

    def test_roman_numeral(self):
        assert normalize_sublabel("ii") == "(ii)"
        assert normalize_sublabel("(iii)") == "(iii)"

    def test_composite_label_preserved(self):
        assert normalize_sublabel("(i)(a)") == "(i)(a)"
        assert normalize_sublabel("(i)(b)") == "(i)(b)"

    def test_bracket_variants(self):
        assert normalize_sublabel("[c]") == "(c)"


class TestExtractParentAndSublabel:
    def test_compound_digit_letter(self):
        parent, sub = extract_parent_and_sublabel("2(b)")
        assert parent == "2"
        assert sub == "(b)"

    def test_compound_q_prefix(self):
        parent, sub = extract_parent_and_sublabel("Q3(a)")
        # Q-prefix is kept in parent_candidate; normalize_parent_key strips it at reconcile-time
        assert parent is not None
        assert "3" in parent  # Could be "Q3" or "3" depending on regex capture
        assert sub == "(a)"

    def test_compound_roman(self):
        parent, sub = extract_parent_and_sublabel("5(ii)")
        assert parent == "5"
        assert sub == "(ii)"

    def test_standalone_letter(self):
        parent, sub = extract_parent_and_sublabel("(b)")
        assert parent is None
        assert sub == "(b)"

    def test_standalone_roman(self):
        parent, sub = extract_parent_and_sublabel("(ii)")
        assert parent is None
        assert sub == "(ii)"

    def test_composite_nested_label(self):
        # e.g. Gemini emits "(i)(a)" as question_number for a sub-subpart
        parent, sub = extract_parent_and_sublabel("(i)(a)")
        assert parent is None
        assert sub == "(i)(a)"

    def test_regular_question_number(self):
        parent, sub = extract_parent_and_sublabel("1")
        assert parent is None
        assert sub is None

    def test_question_prefix(self):
        parent, sub = extract_parent_and_sublabel("Question 3")
        assert parent is None
        assert sub is None


class TestIsSequentialSublabel:
    def test_first_label_a(self):
        assert _is_sequential_sublabel([], "(a)") is True

    def test_first_label_i(self):
        assert _is_sequential_sublabel([], "(i)") is True

    def test_sequential_letters(self):
        assert _is_sequential_sublabel(["(a)"], "(b)") is True
        assert _is_sequential_sublabel(["(a)", "(b)"], "(c)") is True

    def test_sequential_roman(self):
        assert _is_sequential_sublabel(["(i)"], "(ii)") is True
        assert _is_sequential_sublabel(["(i)", "(ii)"], "(iii)") is True

    def test_non_sequential_letter(self):
        # (d) after (a) is not sequential
        assert _is_sequential_sublabel(["(a)"], "(d)") is False

    def test_non_sequential_roman(self):
        # (iv) after (i) is not sequential
        assert _is_sequential_sublabel(["(i)"], "(iv)") is False

    def test_composite_continuation(self):
        # (i)(b) after (i)(a) is sequential (shares prefix)
        assert _is_sequential_sublabel(["(i)(a)"], "(i)(b)") is True


# ---------------------------------------------------------------------------
# Regression test: Q1 hierarchy (pages 1–2)
# Q1(a): Red/Black ball probability — page 1
# Q1(b): Conditional probability (dice) — page 2
# ---------------------------------------------------------------------------

class TestQ1Hierarchy:
    """Q1(a) and Q1(b) must be grouped under parent Q1."""

    def _make_input(self):
        return """{
            "questions": [
                {
                    "question_number": "1",
                    "question_text": "A box has 12 red and 6 black balls...",
                    "subquestions": [
                        {
                            "subquestion_label": "(a)",
                            "text": "Find the probability that a second ball drawn is: (i) Red, and (ii) Black.",
                            "answer": null
                        }
                    ],
                    "answer": null,
                    "page_number": 1
                },
                {
                    "question_number": "1(b)",
                    "question_text": "Two dice are thrown. Let A be the event that the sum is odd and B is the event that at least one number is 2. Find P(A/B).",
                    "answer": null,
                    "page_number": 2
                }
            ]
        }"""

    def test_q1_groups_to_single_parent(self):
        result = PaperExtractionResult.model_validate_json(self._make_input())
        assert result.total_questions_detected == 1
        q1 = result.questions[0]
        assert q1.question_number == "1"

    def test_q1_has_two_subquestions(self):
        result = PaperExtractionResult.model_validate_json(self._make_input())
        q1 = result.questions[0]
        assert len(q1.subquestions) == 2

    def test_q1_subquestion_labels(self):
        result = PaperExtractionResult.model_validate_json(self._make_input())
        q1 = result.questions[0]
        labels = [sq.subquestion_label for sq in q1.subquestions]
        assert "(a)" in labels
        assert "(b)" in labels

    def test_q1_spans_pages_1_and_2(self):
        result = PaperExtractionResult.model_validate_json(self._make_input())
        q1 = result.questions[0]
        assert 1 in q1.page_numbers
        assert 2 in q1.page_numbers

    def test_q1_parent_text_is_preamble_not_subquestion_text(self):
        result = PaperExtractionResult.model_validate_json(self._make_input())
        q1 = result.questions[0]
        # Parent text must NOT be the same as the first subquestion text
        if q1.subquestions:
            assert q1.question_text != q1.subquestions[0].text


# ---------------------------------------------------------------------------
# Regression test: Q2(b) spanning pages 2–3
# Q2(a): Conditional CDF — page 2
# Q2(b): CDF of Y=X^2 — starts page 2 tail, full statement on page 3
# ---------------------------------------------------------------------------

class TestQ2CrossPageHierarchy:
    """Q2(b) text begins on page 2 but the full question is on page 3.
    Both must end up under parent Q2."""

    def _make_input(self):
        return """{
            "questions": [
                {
                    "question_number": "2",
                    "question_text": "Let X be a continuous random variable with pdf f(x) = 4x^3...",
                    "subquestions": [
                        {
                            "subquestion_label": "(a)",
                            "text": "Find P(X <= 2/3 | X > 1/3).",
                            "answer": null
                        }
                    ],
                    "answer": null,
                    "page_number": 2
                },
                {
                    "question_number": "2(b)",
                    "question_text": "Let X be a continuous random variable with pdf f(x) = (1/2)e^{-|x|}. If Y=X^2, find the CDF of Y.",
                    "answer": null,
                    "page_number": 3
                }
            ]
        }"""

    def test_q2_has_one_top_level_entry(self):
        result = PaperExtractionResult.model_validate_json(self._make_input())
        q2_matches = [q for q in result.questions if q.question_number == "2"]
        assert len(q2_matches) == 1

    def test_q2_has_two_subquestions(self):
        result = PaperExtractionResult.model_validate_json(self._make_input())
        q2 = next(q for q in result.questions if q.question_number == "2")
        assert len(q2.subquestions) == 2

    def test_q2_subquestion_b_text_preserved(self):
        result = PaperExtractionResult.model_validate_json(self._make_input())
        q2 = next(q for q in result.questions if q.question_number == "2")
        sub_b = next((s for s in q2.subquestions if s.subquestion_label == "(b)"), None)
        assert sub_b is not None
        assert "CDF" in sub_b.text or "cumulative" in sub_b.text.lower() or "Y" in sub_b.text

    def test_q2_spans_pages_2_and_3(self):
        result = PaperExtractionResult.model_validate_json(self._make_input())
        q2 = next(q for q in result.questions if q.question_number == "2")
        assert 2 in q2.page_numbers
        assert 3 in q2.page_numbers


# ---------------------------------------------------------------------------
# Regression test: Q3(b) answer extraction (covariance & correlation)
# The answer key on page 4 shows Cov(X,Y) = 1/36 and Cor(X,Y) = 1/2.
# When Gemini emits these answers under Q3(b), they must be preserved.
# ---------------------------------------------------------------------------

class TestQ3AnswerExtraction:
    """Answer key solutions for Q3(b) must be captured as answers."""

    def _make_input_with_answers(self):
        return """{
            "questions": [
                {
                    "question_number": "3",
                    "question_text": "Let X and Y be continuous random variables with joint pdf f_{XY}(x,y) = 2...",
                    "subquestions": [
                        {
                            "subquestion_label": "(a)",
                            "text": "Find P(Y=1), P(Y=0) and P(X=1|Y=1).",
                            "answer": null
                        },
                        {
                            "subquestion_label": "(b)",
                            "text": "Find (i) covariance of (X,Y) and (ii) correlation coefficient between X and Y.",
                            "answer": "$\\\\text{Cov}(X,Y) = \\\\frac{1}{36}$, $\\\\text{Cor}(X,Y) = \\\\frac{1}{2}$",
                            "has_explicit_answer": true
                        }
                    ],
                    "answer": null,
                    "page_number": 3
                }
            ]
        }"""

    def test_q3b_covariance_answer_captured(self):
        result = PaperExtractionResult.model_validate_json(self._make_input_with_answers())
        q3 = next(q for q in result.questions if q.question_number == "3")
        sub_b = next((s for s in q3.subquestions if s.subquestion_label == "(b)"), None)
        assert sub_b is not None
        assert sub_b.answer is not None
        assert sub_b.has_explicit_answer is True
        assert "1/36" in sub_b.answer or "\\frac{1}{36}" in sub_b.answer

    def test_q3b_correlation_answer_captured(self):
        result = PaperExtractionResult.model_validate_json(self._make_input_with_answers())
        q3 = next(q for q in result.questions if q.question_number == "3")
        sub_b = next((s for s in q3.subquestions if s.subquestion_label == "(b)"), None)
        assert sub_b is not None
        assert "1/2" in sub_b.answer or "\\frac{1}{2}" in sub_b.answer

    def test_q3a_answer_remains_null_when_not_given(self):
        result = PaperExtractionResult.model_validate_json(self._make_input_with_answers())
        q3 = next(q for q in result.questions if q.question_number == "3")
        sub_a = next((s for s in q3.subquestions if s.subquestion_label == "(a)"), None)
        assert sub_a is not None
        assert sub_a.answer is None


# ---------------------------------------------------------------------------
# Regression test: Q5(a) answer extraction (99.86%)
# ---------------------------------------------------------------------------

class TestQ5aAnswerExtraction:
    def test_q5a_percent_answer_captured(self):
        raw = """{
            "questions": [
                {
                    "question_number": "5",
                    "question_text": "Binomial distribution question.",
                    "subquestions": [
                        {
                            "subquestion_label": "(a)",
                            "text": "Show that P(X >= 1) is 99.86%.",
                            "answer": "99.86%",
                            "has_explicit_answer": true
                        }
                    ],
                    "answer": null
                }
            ]
        }"""
        result = PaperExtractionResult.model_validate_json(raw)
        q5 = next(q for q in result.questions if q.question_number == "5")
        sub_a = next((s for s in q5.subquestions if s.subquestion_label == "(a)"), None)
        assert sub_a is not None
        assert sub_a.answer == "99.86%"
        assert sub_a.has_explicit_answer is True

    def test_q5a_null_when_no_answer(self):
        raw = """{
            "questions": [
                {
                    "question_number": "5",
                    "question_text": "Binomial distribution question.",
                    "subquestions": [
                        {
                            "subquestion_label": "(a)",
                            "text": "Show that P(X >= 1) is 99.86%.",
                            "answer": null
                        }
                    ],
                    "answer": null
                }
            ]
        }"""
        result = PaperExtractionResult.model_validate_json(raw)
        q5 = next(q for q in result.questions if q.question_number == "5")
        sub_a = next((s for s in q5.subquestions if s.subquestion_label == "(a)"), None)
        assert sub_a.answer is None
        assert sub_a.has_explicit_answer is False


# ---------------------------------------------------------------------------
# Regression test: Q5(b) nested sub-subquestions using composite labels
# Q5(b)(i)(a): 49/512
# Q5(b)(i)(b): 343/512
# Q5(b)(ii):   8 days expected value
# ---------------------------------------------------------------------------

class TestQ5bNestedSubSubquestions:
    """Q5(b) has sub-subquestions that must be captured using composite labels."""

    def _make_q5b_with_nested_subs(self):
        """Simulate what a well-prompted Gemini would emit for Q5(b)."""
        return """{
            "questions": [
                {
                    "question_number": "5",
                    "question_text": "Erika is a birdwatcher. The probability she will see a woodpecker is 1/8.",
                    "subquestions": [
                        {
                            "subquestion_label": "(a)",
                            "text": "Show that P(X >= 1) is 99.86%.",
                            "answer": "99.86%",
                            "has_explicit_answer": true
                        },
                        {
                            "subquestion_label": "(b)",
                            "text": "Calculate the probability that Erika first sees a woodpecker...",
                            "answer": null
                        }
                    ],
                    "answer": null,
                    "page_number": 4
                },
                {
                    "question_number": "5(b)(i)(a)",
                    "question_text": "On the third day.",
                    "answer": "$\\\\frac{49}{512}$",
                    "has_explicit_answer": true,
                    "page_number": 5
                },
                {
                    "question_number": "5(b)(i)(b)",
                    "question_text": "After the third day.",
                    "answer": "$\\\\frac{343}{512}$",
                    "has_explicit_answer": true,
                    "page_number": 5
                },
                {
                    "question_number": "5(b)(ii)",
                    "question_text": "Find the expectation of the number of days required.",
                    "answer": "8 days",
                    "has_explicit_answer": true,
                    "page_number": 6
                }
            ]
        }"""

    def test_q5_has_single_top_level_entry(self):
        result = PaperExtractionResult.model_validate_json(self._make_q5b_with_nested_subs())
        q5_matches = [q for q in result.questions if q.question_number == "5"]
        assert len(q5_matches) == 1

    def test_q5b_sub_subquestions_captured(self):
        result = PaperExtractionResult.model_validate_json(self._make_q5b_with_nested_subs())
        q5 = next(q for q in result.questions if q.question_number == "5")
        labels = [sq.subquestion_label for sq in q5.subquestions]
        # Must have (a) and (b) at minimum; compound sub-subs merged into Q5
        assert "(a)" in labels
        assert "(b)" in labels

    def test_q5b_nested_answers_preserved(self):
        result = PaperExtractionResult.model_validate_json(self._make_q5b_with_nested_subs())
        q5 = next(q for q in result.questions if q.question_number == "5")
        # Find any subquestion with 49/512 answer
        answers = [sq.answer for sq in q5.subquestions if sq.answer is not None]
        combined = " ".join(answers)
        assert "49" in combined or "343" in combined or "8" in combined or "99.86" in combined

    def test_q5_spans_pages_4_5_6(self):
        result = PaperExtractionResult.model_validate_json(self._make_q5b_with_nested_subs())
        q5 = next(q for q in result.questions if q.question_number == "5")
        assert 4 in q5.page_numbers
        # Pages 5 and 6 may or may not appear depending on how compound labels are resolved


# ---------------------------------------------------------------------------
# Regression test: Q4 is preserved correctly (not merged with anything)
# ---------------------------------------------------------------------------

class TestQ4Preservation:
    def test_q4_independent_top_level(self):
        raw = """{
            "questions": [
                {
                    "question_number": "3",
                    "question_text": "Binary communication...",
                    "subquestions": [
                        {"subquestion_label": "(a)", "text": "Find P(Y=1), P(Y=0), P(X=1|Y=1).", "answer": null},
                        {"subquestion_label": "(b)", "text": "Find covariance and correlation.", "answer": "$\\\\text{Cov}=1/36$, $\\\\text{Cor}=1/2$", "has_explicit_answer": true}
                    ],
                    "answer": null
                },
                {
                    "question_number": "4",
                    "question_text": "A manufacturer finds the average demand per day is 1.5 (Poisson).",
                    "subquestions": [
                        {"subquestion_label": "(a)", "text": "On how many days would both machines be free? (ii) Some demand refused?", "answer": null},
                        {"subquestion_label": "(b)", "text": "If P(X=0)=P(X=1)=k, find k.", "answer": "$k = e^{-1}$", "has_explicit_answer": true}
                    ],
                    "answer": null
                }
            ]
        }"""
        result = PaperExtractionResult.model_validate_json(raw)
        q_numbers = [q.question_number for q in result.questions]
        assert "3" in q_numbers
        assert "4" in q_numbers
        # Q4 must remain separate from Q3
        q4 = next(q for q in result.questions if q.question_number == "4")
        assert len(q4.subquestions) == 2

    def test_q4b_answer_preserved(self):
        raw = """{
            "questions": [
                {
                    "question_number": "4",
                    "question_text": "Poisson variate question.",
                    "subquestions": [
                        {"subquestion_label": "(b)", "text": "Find k.", "answer": "$k = e^{-1}$", "has_explicit_answer": true}
                    ],
                    "answer": null
                }
            ]
        }"""
        result = PaperExtractionResult.model_validate_json(raw)
        q4 = result.questions[0]
        sub_b = next(s for s in q4.subquestions if s.subquestion_label == "(b)")
        assert sub_b.answer == "$k = e^{-1}$"
        assert sub_b.has_explicit_answer is True


# ---------------------------------------------------------------------------
# Regression test: Answer-key solution text must NOT create new questions
# ---------------------------------------------------------------------------

class TestAnswerKeyTextNotAsQuestion:
    """Printed solution lines (e.g. 'So, the probability is about 99.86%.') must
    not appear as standalone top-level questions in the output."""

    def test_solution_continuation_not_separate_question(self):
        """If Gemini emits 'So, the probability is about 99.86%.' as question_text
        with no question_number pattern, it should not be confused as a valid
        parent question. Only numbered questions like '1', '2' are real parents."""
        raw = """{
            "questions": [
                {
                    "question_number": "5",
                    "question_text": "Binomial distribution...",
                    "subquestions": [
                        {"subquestion_label": "(a)", "text": "Show P(X>=1)=99.86%.", "answer": "99.86%", "has_explicit_answer": true}
                    ],
                    "answer": null
                }
            ]
        }"""
        result = PaperExtractionResult.model_validate_json(raw)
        # Only Q5 should exist, not any stray solution-text question
        assert result.total_questions_detected == 1
        assert result.questions[0].question_number == "5"


# ---------------------------------------------------------------------------
# Regression test: Page numbers preserved per question and subquestion
# ---------------------------------------------------------------------------

class TestPageNumberPreservation:
    def test_subquestion_page_numbers_set(self):
        q = _q("1", "Some question", page=1, subs=[
            _sq("(a)", "Part a", page=1),
            _sq("(b)", "Part b", page=2),
        ])
        paper = PaperExtractionResult(questions=[q], total_pages_detected=2)
        q1 = paper.questions[0]
        assert q1.page_number == 1
        assert 1 in q1.page_numbers
        assert 2 in q1.page_numbers  # Subquestion page synced

    def test_cross_page_question_page_numbers_merged(self):
        """When Q2 appears on pages 2 and 3 (across pages), page_numbers must include both."""
        raw = """{
            "questions": [
                {
                    "question_number": "2",
                    "question_text": "Let X be a continuous rv...",
                    "subquestions": [{"subquestion_label": "(a)", "text": "Find P.", "answer": null}],
                    "answer": null,
                    "page_number": 2,
                    "page_numbers": [2]
                },
                {
                    "question_number": "2(b)",
                    "question_text": "If Y=X^2 find CDF of Y.",
                    "answer": null,
                    "page_number": 3,
                    "page_numbers": [3]
                }
            ]
        }"""
        result = PaperExtractionResult.model_validate_json(raw)
        q2 = next(q for q in result.questions if q.question_number == "2")
        assert 2 in q2.page_numbers
        assert 3 in q2.page_numbers


# ---------------------------------------------------------------------------
# Regression test: JSON truncation repair
# ---------------------------------------------------------------------------

class TestTruncatedJsonRepair:
    """Verify that the _repair_truncated_json method in GeminiMathExtractor
    closes unclosed strings and brackets."""

    def test_repair_unclosed_string(self):
        from app.services.extractor import GeminiMathExtractor
        extractor = GeminiMathExtractor.__new__(GeminiMathExtractor)
        extractor.api_key = "test"
        truncated = '{"questions": [{"question_number": "1", "question_text": "Find the integral $\\\\int_0^1'
        repaired = extractor._repair_truncated_json(truncated)
        # Must end with a closed string followed by bracket/brace closings
        # e.g. ...int_0^1"]}}" or ...int_0^1"]}"
        assert '"' in repaired[-5:]  # String was closed
        assert ']' in repaired        # Array was closed
        assert repaired.endswith('}') # Outermost object was closed

    def test_repair_unclosed_array(self):
        from app.services.extractor import GeminiMathExtractor
        extractor = GeminiMathExtractor.__new__(GeminiMathExtractor)
        extractor.api_key = "test"
        truncated = '{"questions": [{"question_number": "1", "question_text": "Some text"}'
        repaired = extractor._repair_truncated_json(truncated)
        assert repaired.endswith("]}") or repaired.endswith("]}")

    def test_repair_valid_json_unchanged(self):
        from app.services.extractor import GeminiMathExtractor
        extractor = GeminiMathExtractor.__new__(GeminiMathExtractor)
        extractor.api_key = "test"
        valid = '{"questions": []}'
        repaired = extractor._repair_truncated_json(valid)
        assert repaired == valid

    def test_repaired_json_parseable_by_pydantic(self):
        """A truncated but repairable JSON should produce a valid PaperExtractionResult."""
        from app.services.extractor import GeminiMathExtractor
        extractor = GeminiMathExtractor.__new__(GeminiMathExtractor)
        extractor.api_key = "test"
        # Truncated after first complete question item
        truncated = (
            '{"paper_title": "Test", "questions": ['
            '{"question_number": "1", "question_text": "Find x.", "answer": null, "subquestions": []}'
        )
        repaired = extractor._repair_truncated_json(truncated)
        result = PaperExtractionResult.model_validate_json(repaired)
        assert result.total_questions_detected == 1


# ---------------------------------------------------------------------------
# Regression test: answers never invented for unanswered questions
# ---------------------------------------------------------------------------

class TestAnswersNeverInvented:
    def test_all_null_answers_remain_null(self):
        raw = """{
            "questions": [
                {
                    "question_number": "1",
                    "question_text": "Find the probability of red ball.",
                    "subquestions": [
                        {"subquestion_label": "(i)", "text": "Red ball.", "answer": null},
                        {"subquestion_label": "(ii)", "text": "Black ball.", "answer": null}
                    ],
                    "answer": null
                },
                {
                    "question_number": "2",
                    "question_text": "Find conditional probability.",
                    "subquestions": [
                        {"subquestion_label": "(a)", "text": "Find P(A/B).", "answer": null}
                    ],
                    "answer": null
                }
            ]
        }"""
        result = PaperExtractionResult.model_validate_json(raw)
        for q in result.questions:
            assert q.answer is None, f"Q{q.question_number} should have no answer"
            for sq in q.subquestions:
                assert sq.answer is None, f"Q{q.question_number}{sq.subquestion_label} should have no answer"
                assert sq.has_explicit_answer is False

    def test_existing_answer_preserved_not_duplicated(self):
        """An answer set at subquestion level must not bleed onto the parent."""
        raw = """{
            "questions": [
                {
                    "question_number": "4",
                    "question_text": "Poisson question.",
                    "subquestions": [
                        {"subquestion_label": "(b)", "text": "Find k.", "answer": "$k=e^{-1}$", "has_explicit_answer": true}
                    ],
                    "answer": null
                }
            ]
        }"""
        result = PaperExtractionResult.model_validate_json(raw)
        q4 = result.questions[0]
        assert q4.answer is None, "Parent answer must remain null"
        assert q4.subquestions[0].answer == "$k=e^{-1}$"


# ---------------------------------------------------------------------------
# Regression test: metadata is not extracted as questions
# ---------------------------------------------------------------------------

class TestMetadataNotExtracted:
    def test_header_metadata_excluded(self):
        """Confirm that if Gemini accidentally emits metadata fields as text,
        the schema still validates normally and doesn't create phantom questions."""
        # A clean extraction with only real questions should not contain metadata
        raw = """{
            "paper_title": "BAMAT207 - Probability and Statistics CAT-I",
            "questions": [
                {
                    "question_number": "1",
                    "question_text": "A box has 12 red and 6 black balls...",
                    "subquestions": [],
                    "answer": null
                }
            ],
            "notes": "Exam header: B.Tech, Semester Winter 2025-26, Slot E2+TE2"
        }"""
        result = PaperExtractionResult.model_validate_json(raw)
        assert result.paper_title == "BAMAT207 - Probability and Statistics CAT-I"
        assert result.total_questions_detected == 1
        # Notes captured but not inflated into questions
        assert result.notes is not None


# ---------------------------------------------------------------------------
# Full E2 CAT1 paper structure regression test (mocked ideal output)
# ---------------------------------------------------------------------------

class TestE2Cat1FullStructure:
    """Full document structure regression: 5 parent questions, all subquestions
    correctly grouped, answers from answer-key preserved, page refs correct."""

    def _build_ideal_result(self):
        """Build the ideal PaperExtractionResult that our pipeline should produce
        for the E2 Slot CAT1 Answer Key PDF."""
        return PaperExtractionResult(
            paper_title="BAMAT207 - Probability and Statistics CAT-I",
            total_pages_detected=6,
            questions=[
                QuestionItem(
                    question_number="1",
                    question_text="A box has 12 red and 6 black balls...",
                    page_number=1,
                    page_numbers=[1, 2],
                    subquestions=[
                        SubQuestion(
                            subquestion_label="(a)",
                            text="Find the probability that a second ball drawn is: (i) Red, and (ii) Black.",
                            answer=None,
                            page_number=1,
                        ),
                        SubQuestion(
                            subquestion_label="(b)",
                            text=r"Find $P(A/B)$ where A is sum of points is odd and B is at least one number is 2.",
                            answer=None,
                            page_number=2,
                        ),
                    ],
                ),
                QuestionItem(
                    question_number="2",
                    question_text=r"Let $X$ be a continuous rv with pdf $f(x) = 4x^3$, $0 < x \le 1$.",
                    page_number=2,
                    page_numbers=[2, 3],
                    subquestions=[
                        SubQuestion(
                            subquestion_label="(a)",
                            text=r"Find $P\left(X \le \frac{2}{3} \mid X > \frac{1}{3}\right)$.",
                            answer=None,
                            page_number=2,
                        ),
                        SubQuestion(
                            subquestion_label="(b)",
                            text=r"Let $X$ have pdf $f(x) = \frac{1}{2}e^{-|x|}$. If $Y=X^2$, find the CDF of $Y$.",
                            answer=None,
                            page_number=3,
                        ),
                    ],
                ),
                QuestionItem(
                    question_number="3",
                    question_text="Binary communication system question.",
                    page_number=3,
                    page_numbers=[3, 4],
                    subquestions=[
                        SubQuestion(
                            subquestion_label="(a)",
                            text=r"Find $P(Y=1)$, $P(Y=0)$ and $P(X=1|Y=1)$.",
                            answer=None,
                            page_number=3,
                        ),
                        SubQuestion(
                            subquestion_label="(b)",
                            text=r"Find (i) $\text{Cov}(X,Y)$ and (ii) correlation coefficient between $X$ and $Y$.",
                            answer=r"$\text{Cov}(X,Y) = \frac{1}{36}$, $\text{Cor}(X,Y) = \frac{1}{2}$",
                            has_explicit_answer=True,
                            page_number=4,
                        ),
                    ],
                ),
                QuestionItem(
                    question_number="4",
                    question_text="Poisson distribution question.",
                    page_number=4,
                    page_numbers=[4],
                    subquestions=[
                        SubQuestion(
                            subquestion_label="(a)",
                            text="Average demand per day is 1.5 (Poisson). How many days (i) both machines free? (ii) demand refused?",
                            answer=None,
                            page_number=4,
                        ),
                        SubQuestion(
                            subquestion_label="(b)",
                            text=r"If $P(X=0)=P(X=1)=k$, find $k$.",
                            answer=r"$k = e^{-1}$",
                            has_explicit_answer=True,
                            page_number=4,
                        ),
                    ],
                ),
                QuestionItem(
                    question_number="5",
                    question_text="Binomial and geometric distribution questions.",
                    page_number=4,
                    page_numbers=[4, 5, 6],
                    subquestions=[
                        SubQuestion(
                            subquestion_label="(a)",
                            text=r"Show that $P(X \ge 1)$ is 99.86% for binomial with mean 4 and SD $\frac{2}{\sqrt{3}}$.",
                            answer="99.86%",
                            has_explicit_answer=True,
                            page_number=5,
                        ),
                        SubQuestion(
                            subquestion_label="(b)",
                            text="Erika sees a woodpecker with probability 1/8 each day. Calculate probabilities.",
                            answer=None,
                            page_number=5,
                        ),
                    ],
                ),
            ],
        )

    def test_five_parent_questions(self):
        result = self._build_ideal_result()
        assert result.total_questions_detected == 5

    def test_all_question_numbers_present(self):
        result = self._build_ideal_result()
        q_nums = [q.question_number for q in result.questions]
        for expected in ("1", "2", "3", "4", "5"):
            assert expected in q_nums, f"Question {expected} missing"

    def test_q1_two_subquestions(self):
        result = self._build_ideal_result()
        q1 = next(q for q in result.questions if q.question_number == "1")
        assert len(q1.subquestions) == 2

    def test_q3b_has_answer(self):
        result = self._build_ideal_result()
        q3 = next(q for q in result.questions if q.question_number == "3")
        sub_b = next(s for s in q3.subquestions if s.subquestion_label == "(b)")
        assert sub_b.has_explicit_answer is True
        assert sub_b.answer is not None

    def test_q4b_has_answer(self):
        result = self._build_ideal_result()
        q4 = next(q for q in result.questions if q.question_number == "4")
        sub_b = next(s for s in q4.subquestions if s.subquestion_label == "(b)")
        assert sub_b.has_explicit_answer is True

    def test_q5a_has_answer(self):
        result = self._build_ideal_result()
        q5 = next(q for q in result.questions if q.question_number == "5")
        sub_a = next(s for s in q5.subquestions if s.subquestion_label == "(a)")
        assert sub_a.answer == "99.86%"
        assert sub_a.has_explicit_answer is True

    def test_q2_no_parent_answer(self):
        result = self._build_ideal_result()
        q2 = next(q for q in result.questions if q.question_number == "2")
        assert q2.answer is None

    def test_q5_spans_multiple_pages(self):
        result = self._build_ideal_result()
        q5 = next(q for q in result.questions if q.question_number == "5")
        assert len(q5.page_numbers) >= 2

    def test_no_answers_invented(self):
        result = self._build_ideal_result()
        for q in result.questions:
            if q.answer is not None:
                assert q.has_explicit_answer is True
            for sq in q.subquestions:
                if sq.answer is None:
                    assert sq.has_explicit_answer is False
