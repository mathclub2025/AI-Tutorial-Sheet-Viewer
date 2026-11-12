"""Unit and regression tests for Two-Stage Cross-Page Reconciliation Architecture.

Validates:
1. NormalizedBoundingBox validation, coordinate ordering auto-correction, and bounds enforcement.
2. RawExtractedBlock preservation throughout the extraction pipeline (raw blocks never discarded).
3. Answer hallucination protection via source_block_ids verification:
   - Verified answers remain intact.
   - Unverified answer sources flag needs_human_review=True and UNVERIFIED_ANSWER_SOURCE rather than silent deletion.
4. Stage 2 cross-page reconciliation execution:
   - LLM reconciliation succeeds and preserves page numbers, source_block_ids, and raw_blocks.
   - LLM failure/timeout triggers deterministic fallback with RECONCILIATION_FALLBACK_USED review flag.
5. Regression test suite for 6-page exam papers (CAT-1 layout pattern):
   - Exactly five top-level questions (Q1–Q5).
   - Q1(a), Q1(b).
   - Q2(a), Q2(b) with Q2(b) spanning pages 2–3.
   - Q3(a), Q3(b) with Q3(b) answers on page 4.
   - Q4(a), Q4(b).
   - Q5(a), Q5(b) with Q5(b) spanning pages 5–6.
   - Unrelated questions on the same page are not merged.
   - Question and solution continuations across page boundaries are properly merged.
"""

from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.extraction.schemas.extraction import (
    NormalizedBoundingBox,
    PaperExtractionResult,
    QuestionItem,
    RawExtractedBlock,
    ReviewReason,
    SubQuestion,
    verify_answer_sources,
)
from app.extraction.services.extractor import GeminiMathExtractor

from .test_extractor import create_dummy_image_result

# ---------------------------------------------------------------------------
# 1. Bounding Box Validation Tests
# ---------------------------------------------------------------------------

class TestNormalizedBoundingBox:
    def test_valid_bounding_box(self):
        bbox = NormalizedBoundingBox(ymin=100, xmin=50, ymax=300, xmax=400)
        assert bbox.ymin == 100
        assert bbox.xmin == 50
        assert bbox.ymax == 300
        assert bbox.xmax == 400

    def test_inverted_coordinates_auto_corrected(self):
        """Coordinate ordering ymin > ymax or xmin > xmax is automatically corrected."""
        bbox = NormalizedBoundingBox(ymin=500, xmin=400, ymax=100, xmax=50)
        assert bbox.ymin == 100
        assert bbox.ymax == 500
        assert bbox.xmin == 50
        assert bbox.xmax == 400

    def test_out_of_bounds_rejected(self):
        """Values < 0 or > 1000 raise ValidationError."""
        with pytest.raises(ValidationError):
            NormalizedBoundingBox(ymin=-10, xmin=0, ymax=100, xmax=100)
        with pytest.raises(ValidationError):
            NormalizedBoundingBox(ymin=0, xmin=0, ymax=1050, xmax=100)


# ---------------------------------------------------------------------------
# 2. Raw Block Preservation & Source Block Tracing
# ---------------------------------------------------------------------------

class TestRawBlockPreservationAndProvenance:
    def test_raw_blocks_preserved_in_paper_extraction_result(self):
        raw_b1 = RawExtractedBlock(
            block_id="p1_b1",
            page_number=1,
            block_type="question",
            raw_label="1",
            text="Find $\\int x dx$.",
            explicit_answer="$\\frac{x^2}{2} + C$",
            has_explicit_answer=True,
            bounding_box=NormalizedBoundingBox(ymin=50, xmin=100, ymax=150, xmax=800),
        )
        q1 = QuestionItem(
            question_number="1",
            question_text="Find $\\int x dx$.",
            answer="$\\frac{x^2}{2} + C$",
            has_explicit_answer=True,
            page_number=1,
            source_block_ids=["p1_b1"],
        )
        result = PaperExtractionResult(
            questions=[q1],
            raw_blocks=[raw_b1],
        )
        assert len(result.raw_blocks) == 1
        assert result.raw_blocks[0].block_id == "p1_b1"
        assert result.questions[0].source_block_ids == ["p1_b1"]

    def test_verified_answer_passes_without_review_flag(self):
        raw_b1 = RawExtractedBlock(
            block_id="p1_b1",
            page_number=1,
            text="Evaluate $2 + 2$. Answer is 4.",
            explicit_answer="4",
            has_explicit_answer=True,
        )
        q1 = QuestionItem(
            question_number="1",
            question_text="Evaluate $2 + 2$.",
            answer="4",
            has_explicit_answer=True,
            source_block_ids=["p1_b1"],
        )
        verify_answer_sources([q1], [raw_b1])
        assert q1.needs_human_review is False
        assert ReviewReason.UNVERIFIED_ANSWER_SOURCE.value not in q1.review_reasons

    def test_unverified_answer_source_flags_human_review(self):
        """Answer that has no supporting evidence in referenced raw blocks is flagged for human review."""
        raw_b1 = RawExtractedBlock(
            block_id="p1_b1",
            page_number=1,
            text="Prove the Riemann Hypothesis.",
            explicit_answer=None,
            has_explicit_answer=False,
        )
        # Model claims answer is "True", but raw block contains no answer
        q1 = QuestionItem(
            question_number="1",
            question_text="Prove the Riemann Hypothesis.",
            answer="True",
            has_explicit_answer=True,
            source_block_ids=["p1_b1"],
        )
        verify_answer_sources([q1], [raw_b1])
        assert q1.needs_human_review is True
        assert ReviewReason.UNVERIFIED_ANSWER_SOURCE.value in q1.review_reasons
        # Notice answer was NOT silently erased; evidence provenance was flagged for human auditor
        assert q1.answer == "True"

    def test_missing_source_block_ids_flags_human_review(self):
        """Answer with empty source_block_ids is flagged for human review."""
        raw_b1 = RawExtractedBlock(
            block_id="p1_b1",
            page_number=1,
            text="Solve $x^2 = 9$.",
            explicit_answer="\\pm 3",
            has_explicit_answer=True,
        )
        q1 = QuestionItem(
            question_number="1",
            question_text="Solve $x^2 = 9$.",
            answer="\\pm 3",
            has_explicit_answer=True,
            source_block_ids=[],  # Missing source block reference
        )
        verify_answer_sources([q1], [raw_b1])
        assert q1.needs_human_review is True
        assert ReviewReason.UNVERIFIED_ANSWER_SOURCE.value in q1.review_reasons

    def test_dangling_source_block_references_rejected(self):
        """Dangling source_block_ids that do not exist in raw_blocks are stripped/pruned."""
        raw_b1 = RawExtractedBlock(
            block_id="p1_b1",
            page_number=1,
            text="Real block text.",
            explicit_answer="42",
            has_explicit_answer=True,
        )
        q1 = QuestionItem(
            question_number="1",
            question_text="Sample question.",
            answer="42",
            has_explicit_answer=True,
            source_block_ids=["p1_b1", "p99_nonexistent_hallucinated_block"],
        )
        result = PaperExtractionResult(
            questions=[q1],
            raw_blocks=[raw_b1],
        )
        # Dangling reference was pruned
        assert result.questions[0].source_block_ids == ["p1_b1"]

    def test_multiple_answers_in_one_solution_block(self):
        """Multiple explicit answers in a single solution block are verified for their subquestions."""
        sol_block = RawExtractedBlock(
            block_id="p4_sol_q3",
            page_number=4,
            block_type="solution_text",
            text="E(X) = 1/3, E(Y) = 2/3. Therefore Cov(X,Y) = 1/36. Next part: Cor(X,Y) = 1/2.",
            explicit_answer="Cov(X,Y) = 1/36, Cor(X,Y) = 1/2",
            has_explicit_answer=True,
        )
        sq_cov = SubQuestion(
            subquestion_label="(i)",
            text="Find covariance.",
            answer="1/36",
            has_explicit_answer=True,
            source_block_ids=["p4_sol_q3"],
        )
        sq_cor = SubQuestion(
            subquestion_label="(ii)",
            text="Find correlation.",
            answer="1/2",
            has_explicit_answer=True,
            source_block_ids=["p4_sol_q3"],
        )
        q3 = QuestionItem(
            question_number="3",
            question_text="Bivariate random variables.",
            subquestions=[sq_cov, sq_cor],
            source_block_ids=["p4_sol_q3"],
        )
        verify_answer_sources([q3], [sol_block])
        assert sq_cov.needs_human_review is False
        assert sq_cor.needs_human_review is False

    def test_continuation_ii_grouped_under_parent(self):
        """Continuation label '(ii)' attaches to preceding parent with roman subquestions, not as top-level."""
        q5 = QuestionItem(
            question_number="5",
            question_text="Applied statistics problem.",
            subquestions=[
                SubQuestion(subquestion_label="(a)", text="Part a."),
                SubQuestion(subquestion_label="(b)(i)(a)", text="First part."),
            ],
            page_number=5,
        )
        # Page 6 brings '(ii)' as continuation
        q_cont = QuestionItem(
            question_number="(ii)",
            question_text="Expected days waiting time.",
            answer="8 days",
            has_explicit_answer=True,
            page_number=6,
        )
        result = PaperExtractionResult(questions=[q5, q_cont])
        # Exactly 1 top-level question (5); (ii) is NOT an orphaned question!
        assert len(result.questions) == 1
        assert result.questions[0].question_number == "5"
        assert len(result.questions[0].subquestions) == 3
        assert any(sq.answer == "8 days" for sq in result.questions[0].subquestions)


# ---------------------------------------------------------------------------
# 3. Stage 2 Reconciliation & Fallback Tests
# ---------------------------------------------------------------------------

class TestStage2ReconciliationFlow:
    def test_stage2_llm_reconciliation_success(self):
        """Verify Stage 2 LLM cross-page reconciliation parses and preserves blocks."""
        mock_stage1_resp = MagicMock()
        mock_stage1_resp.text = """{
            "paper_title": "CAT-1 Math",
            "total_questions_detected": 1,
            "questions": [
                {
                    "question_number": "2",
                    "question_text": "Let X be uniform (0, 4).",
                    "subquestions": [
                        {"subquestion_label": "(a)", "text": "Find E[X].", "answer": "2", "has_explicit_answer": true}
                    ],
                    "answer": null,
                    "has_explicit_answer": false
                }
            ],
            "raw_blocks": [],
            "requires_human_review": false,
            "review_reasons": []
        }"""

        # Stage 2 reconciles Question 2 and Question 2(b) spanning pages 2 and 3
        mock_stage2_resp = MagicMock()
        mock_stage2_resp.text = """{
            "paper_title": "CAT-1 Math",
            "total_questions_detected": 1,
            "questions": [
                {
                    "question_number": "2",
                    "question_text": "Let X be uniform (0, 4).",
                    "subquestions": [
                        {"subquestion_label": "(a)", "text": "Find E[X].", "answer": "2", "has_explicit_answer": true, "page_number": 2, "source_block_ids": ["p2_q2_a"]},
                        {"subquestion_label": "(b)", "text": "Find CDF of Y = X^2.", "answer": "F_Y(y) = \\\\sqrt{y}/2", "has_explicit_answer": true, "page_number": 3, "source_block_ids": ["p3_q2_b"]}
                    ],
                    "answer": null,
                    "has_explicit_answer": false,
                    "page_number": 2,
                    "page_numbers": [2, 3],
                    "source_block_ids": ["p2_q2", "p3_q2_b"],
                    "confidence_score": 0.95,
                    "needs_human_review": false,
                    "review_reasons": []
                }
            ],
            "requires_human_review": false,
            "review_reasons": []
        }"""
        mock_stage2_resp.usage_metadata = MagicMock(prompt_token_count=1200, candidates_token_count=450, total_token_count=1650)

        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = [
            mock_stage1_resp,  # Page 1
            mock_stage1_resp,  # Page 2
            mock_stage2_resp,  # Stage 2 reconciliation
        ]

        extractor = GeminiMathExtractor(api_key="mock_key", client=mock_client)
        pages = [(2, create_dummy_image_result()), (3, create_dummy_image_result())]
        result = extractor.extract_from_pdf_pages(pages, use_reconciliation_model=True)

        assert isinstance(result, PaperExtractionResult)
        assert result.total_questions_detected == 1
        q2 = result.questions[0]
        assert q2.question_number == "2"
        assert len(q2.subquestions) == 2
        assert q2.page_numbers == [2, 3]
        assert len(result.raw_blocks) > 0  # Raw blocks preserved!

    def test_stage2_reconciliation_fallback_on_error(self):
        """When Stage 2 LLM fails or times out, deterministic fallback runs and flags review."""
        mock_page1 = MagicMock()
        mock_page1.text = """{
            "questions": [
                {
                    "question_number": "1",
                    "question_text": "Find limit.",
                    "subquestions": [{"subquestion_label": "(a)", "text": "Part a", "answer": "0", "has_explicit_answer": true}],
                    "answer": null,
                    "has_explicit_answer": false
                }
            ],
            "raw_blocks": [],
            "requires_human_review": false,
            "review_reasons": []
        }"""
        mock_page2 = MagicMock()
        mock_page2.text = """{
            "questions": [
                {
                    "question_number": "1(b)",
                    "question_text": "Part b continuing limit.",
                    "subquestions": [],
                    "answer": "1",
                    "has_explicit_answer": true
                }
            ],
            "raw_blocks": [],
            "requires_human_review": false,
            "review_reasons": []
        }"""

        # Stage 2 call raises a timeout/API exception
        mock_client = MagicMock()
        mock_client.models.generate_content.side_effect = [
            mock_page1,
            mock_page2,
            TimeoutError("Stage 2 reconciliation timed out after 30s"),
        ]

        extractor = GeminiMathExtractor(api_key="mock_key", client=mock_client)
        pages = [(1, create_dummy_image_result()), (2, create_dummy_image_result())]
        result = extractor.extract_from_pdf_pages(pages, use_reconciliation_model=True)

        # Fallback executed: Q1 and Q1(b) merged deterministically
        assert len(result.questions) == 1
        q = result.questions[0]
        assert q.question_number == "1"
        assert len(q.subquestions) == 2
        assert q.page_numbers == [1, 2]

        # Review flag added because reconciliation fallback was used
        assert result.requires_human_review is True
        assert ReviewReason.RECONCILIATION_FALLBACK_USED.value in result.review_reasons
        assert ReviewReason.RECONCILIATION_FALLBACK_USED.value in q.review_reasons


# ---------------------------------------------------------------------------
# 4. Multi-Page Exam Paper Regression Test (CAT-1 6-Page Layout)
# ---------------------------------------------------------------------------

class TestSixPageExamPaperRegression:
    """Full 6-page regression test representing the CAT-1 answer-key document structure.

    Expected layout:
    - Exactly 5 top-level questions (Q1–Q5).
    - Q1(a), Q1(b) across pages 1–2.
    - Q2(a), Q2(b) across pages 2–3.
    - Q3(a), Q3(b) with Q3(b) covariance & correlation answers on page 4.
    - Q4(a), Q4(b) on page 4.
    - Q5(a), Q5(b) with nested subparts across pages 5–6.
    - Unrelated questions on the same page remain separate.
    """

    def test_six_page_hierarchy_and_answer_association(self):
        # Page 1: Q1(a) prompt & solution
        raw_p1 = [
            RawExtractedBlock(block_id="p1_q1a", page_number=1, block_type="question", raw_label="1(a)", text="Determine k for joint pdf.", explicit_answer="k = 1/4", has_explicit_answer=True)
        ]
        q_p1 = [
            QuestionItem(question_number="1", question_text="Joint probability question", subquestions=[
                SubQuestion(subquestion_label="(a)", text="Determine k.", answer="k = 1/4", has_explicit_answer=True, page_number=1, source_block_ids=["p1_q1a"])
            ], page_number=1, source_block_ids=["p1_q1a"])
        ]

        # Page 2: Q1(b) continuation + Q2(a)
        raw_p2 = [
            RawExtractedBlock(block_id="p2_q1b", page_number=2, block_type="subquestion", raw_label="1(b)", text="Find marginal distribution.", explicit_answer="f_X(x) = 2x", has_explicit_answer=True),
            RawExtractedBlock(block_id="p2_q2a", page_number=2, block_type="question", raw_label="2(a)", text="Find conditional probability P(X>1 | X>0.5).", explicit_answer="3/16", has_explicit_answer=True),
        ]
        q_p2 = [
            QuestionItem(question_number="1(b)", question_text="Find marginal distribution.", answer="f_X(x) = 2x", has_explicit_answer=True, page_number=2, source_block_ids=["p2_q1b"]),
            QuestionItem(question_number="2", question_text="Probability problem 2", subquestions=[
                SubQuestion(subquestion_label="(a)", text="Conditional probability", answer="3/16", has_explicit_answer=True, page_number=2, source_block_ids=["p2_q2a"])
            ], page_number=2, source_block_ids=["p2_q2a"]),
        ]

        # Page 3: Q2(b) solution continuation
        raw_p3 = [
            RawExtractedBlock(block_id="p3_q2b", page_number=3, block_type="subquestion", raw_label="2(b)", text="CDF of Y = X^2.", explicit_answer="F_Y(y) = \\sqrt{y}/2", has_explicit_answer=True)
        ]
        q_p3 = [
            QuestionItem(question_number="2(b)", question_text="CDF of Y = X^2.", answer="F_Y(y) = \\sqrt{y}/2", has_explicit_answer=True, page_number=3, source_block_ids=["p3_q2b"])
        ]

        # Page 4: Q3(a), Q3(b) answers + Q4(a), Q4(b)
        raw_p4 = [
            RawExtractedBlock(block_id="p4_q3a", page_number=4, block_type="subquestion", raw_label="3(a)", text="Mean of X and Y.", explicit_answer=None, has_explicit_answer=False),
            RawExtractedBlock(block_id="p4_q3b", page_number=4, block_type="subquestion", raw_label="3(b)", text="Covariance and correlation.", explicit_answer="Cov(X,Y) = 1/36, Cor(X,Y) = 1/2", has_explicit_answer=True),
            RawExtractedBlock(block_id="p4_q4a", page_number=4, block_type="subquestion", raw_label="4(a)", text="Define Markov Chain.", explicit_answer=None, has_explicit_answer=False),
            RawExtractedBlock(block_id="p4_q4b", page_number=4, block_type="subquestion", raw_label="4(b)", text="Stationary distribution.", explicit_answer="\\pi = [0.4, 0.6]", has_explicit_answer=True),
        ]
        q_p4 = [
            QuestionItem(question_number="3", question_text="Bivariate random variables", subquestions=[
                SubQuestion(subquestion_label="(a)", text="Mean of X and Y.", answer=None, page_number=4, source_block_ids=["p4_q3a"]),
                SubQuestion(subquestion_label="(b)", text="Covariance and correlation.", answer="Cov(X,Y) = 1/36, Cor(X,Y) = 1/2", has_explicit_answer=True, page_number=4, source_block_ids=["p4_q3b"]),
            ], page_number=4, source_block_ids=["p4_q3a", "p4_q3b"]),
            QuestionItem(question_number="4", question_text="Stochastic processes", subquestions=[
                SubQuestion(subquestion_label="(a)", text="Define Markov Chain.", answer=None, page_number=4, source_block_ids=["p4_q4a"]),
                SubQuestion(subquestion_label="(b)", text="Stationary distribution.", answer="\\pi = [0.4, 0.6]", has_explicit_answer=True, page_number=4, source_block_ids=["p4_q4b"]),
            ], page_number=4, source_block_ids=["p4_q4a", "p4_q4b"]),
        ]

        # Page 5: Q5(a) + Q5(b)(i)
        raw_p5 = [
            RawExtractedBlock(block_id="p5_q5a", page_number=5, block_type="subquestion", raw_label="5(a)", text="Normal distribution percentage.", explicit_answer="99.86%", has_explicit_answer=True),
            RawExtractedBlock(block_id="p5_q5bi", page_number=5, block_type="subquestion", raw_label="5(b)(i)(a)", text="Poisson process probability.", explicit_answer="49/512", has_explicit_answer=True),
        ]
        q_p5 = [
            QuestionItem(question_number="5", question_text="Applied statistics", subquestions=[
                SubQuestion(subquestion_label="(a)", text="Normal distribution percentage.", answer="99.86%", has_explicit_answer=True, page_number=5, source_block_ids=["p5_q5a"]),
                SubQuestion(subquestion_label="(i)(a)", text="Poisson process probability.", answer="49/512", has_explicit_answer=True, page_number=5, source_block_ids=["p5_q5bi"]),
            ], page_number=5, source_block_ids=["p5_q5a", "p5_q5bi"])
        ]

        # Page 6: Q5(b)(ii) continuation
        raw_p6 = [
            RawExtractedBlock(block_id="p6_q5bii", page_number=6, block_type="subquestion", raw_label="5(b)(ii)", text="Expected waiting time in days.", explicit_answer="8 days", has_explicit_answer=True)
        ]
        q_p6 = [
            QuestionItem(question_number="5(b)(ii)", question_text="Expected waiting time in days.", answer="8 days", has_explicit_answer=True, page_number=6, source_block_ids=["p6_q5bii"])
        ]

        all_raw_blocks = raw_p1 + raw_p2 + raw_p3 + raw_p4 + raw_p5 + raw_p6
        all_questions = q_p1 + q_p2 + q_p3 + q_p4 + q_p5 + q_p6

        # Assemble and reconcile across all 6 pages
        result = PaperExtractionResult(
            total_pages_detected=6,
            questions=all_questions,
            raw_blocks=all_raw_blocks,
        )

        # 1. Exactly 5 top-level questions
        assert len(result.questions) == 5
        assert [q.question_number for q in result.questions] == ["1", "2", "3", "4", "5"]

        # 2. Q1 has (a) and (b), spans pages [1, 2]
        q1 = result.questions[0]
        assert len(q1.subquestions) == 2
        assert q1.subquestions[0].subquestion_label == "(a)"
        assert q1.subquestions[1].subquestion_label == "(b)"
        assert q1.page_numbers == [1, 2]

        # 3. Q2 has (a) and (b), spans pages [2, 3]
        q2 = result.questions[1]
        assert len(q2.subquestions) == 2
        assert q2.subquestions[0].subquestion_label == "(a)"
        assert q2.subquestions[1].subquestion_label == "(b)"
        assert q2.subquestions[1].answer == r"F_Y(y) = \sqrt{y}/2"
        assert q2.page_numbers == [2, 3]

        # 4. Q3 has covariance and correlation answers on page 4
        q3 = result.questions[2]
        assert q3.subquestions[0].answer is None  # Unanswered remains null!
        assert "Cov(X,Y) = 1/36" in q3.subquestions[1].answer
        assert q3.page_number == 4

        # 5. Q4 is an independent top-level question on page 4 (not merged with Q3)
        q4 = result.questions[3]
        assert q4.question_number == "4"
        assert len(q4.subquestions) == 2
        assert q4.subquestions[1].answer == r"\pi = [0.4, 0.6]"

        # 6. Q5 spans pages [5, 6] with nested answers preserved
        q5 = result.questions[4]
        assert q5.page_numbers == [5, 6]
        q5_subs = {sq.subquestion_label: sq.answer for sq in q5.subquestions}
        assert q5_subs["(a)"] == "99.86%"
        assert q5_subs["(i)(a)"] == "49/512"
        assert q5_subs["(b)(ii)"] == "8 days"

        # 7. Raw blocks preserved
        assert len(result.raw_blocks) == len(all_raw_blocks)
