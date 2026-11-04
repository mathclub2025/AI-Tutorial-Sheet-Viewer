"""Gemini Vision Mathematical Extraction Service.

Extracts printed and handwritten mathematical questions, subquestions, options,
and explicitly written answers from preprocessed document images using the Google
Gen AI SDK. Preserves LaTeX notation and enforces strict Pydantic validation.
NEVER derives or solves missing answers.
"""

import json
import logging
import random
import re
import time
from typing import Any, Dict, List, Optional, Tuple, Union

from google import genai
from google.genai import errors, types
from pydantic import ValidationError

from app.config import settings
from app.schemas.extraction import (
    NormalizedBoundingBox,
    PaperExtractionResult,
    QuestionItem,
    RawExtractedBlock,
    ReviewReason,
    SubQuestion,
    build_gemini_compatible_schema,
    get_gemini_extraction_schema,
    reconcile_question_hierarchy,
    verify_answer_sources,
)
from app.services.preprocessor import PreprocessedImageResult

logger = logging.getLogger(__name__)

SYSTEM_INSTRUCTION = """You are a highly precise, specialized mathematical document transcription system.
Your mission is to read photographs and scans of mathematics exam papers, tutorial sheets, and answer keys, and extract questions and any explicitly written answers.

ABSOLUTE CARDINAL RULES:
1. STRICT TRANSCRIPTION ONLY - NEVER SOLVE:
   - Your function is STRICTLY optical transcription of what is physically visible on the paper.
   - NEVER solve math problems, calculate results, or complete proofs.
   - NEVER derive missing steps or write out solutions that are not physically present on the paper.
   - NEVER invent, guess, or fabricate an answer.

2. EXPLICIT ANSWERS ONLY:
   - Only set "answer" if a student, examiner, or answer key has physically written a definitive final answer or solution (e.g. written in an answer box, labeled "Ans:", circled, stated as a percentage/value, or as a concluding formula).
   - Answer-key documents: if the document contains printed or typed solution steps followed by a clear final result, capture that final result as the "answer".
   - Intermediate working steps (e.g. partial integrals, row operations, intermediate algebraic lines) are NOT answers — do not capture them as answers unless they are the stated final result.
   - If NO answer is explicitly written on the paper for a question or subquestion, you MUST set "answer": null and "has_explicit_answer": false.
   - If only partial scratch work or an incomplete scribble is present without a definitive answer, keep "answer": null and note uncertainty in "review_reasons".

3. PRESERVE MATHEMATICAL NOTATION IN LATEX:
   - Always transcribe all mathematical notation using standard LaTeX syntax.
   - Fractions: \\frac{numerator}{denominator}
   - Matrices: \\begin{pmatrix} ... \\end{pmatrix} or \\begin{bmatrix} ... \\end{bmatrix}
   - Determinants: \\begin{vmatrix} ... \\end{vmatrix}
   - Integrals: \\int_{a}^{b} f(x) \\, dx, \\iint, \\oint
   - Summations and Limits: \\sum_{i=1}^{n}, \\lim_{x \\to 0}
   - Roots: \\sqrt{x}, \\sqrt[n]{x}
   - Exponents and Subscripts: x^{2}, a_{n}, e^{-x}
   - Operators and Greek symbols: \\pm, \\times, \\div, \\alpha, \\beta, \\theta, \\le, \\ge, \\neq, \\in

4. QUESTION HIERARCHY AND SUBQUESTIONS:
   - Identify parent question numbers strictly (e.g. "1", "2", "Question 3", "Problem 4").
   - When a question has subparts using letters (e.g. (a), (b), (c)), or roman numerals (e.g. (i), (ii), (iii)), decompose them into the "subquestions" array under that parent question.
   - For further nested sub-subparts (e.g. question 5(b)(i)(a), 5(b)(i)(b)), use a composite subquestion_label such as "(i)(a)", "(i)(b)", "(ii)" to represent the nesting within the parent's subquestions list. Do NOT create deeply nested arrays — flatten nested labels into one subquestion_label string.
   - NEVER create separate top-level questions for lettered/roman subquestions like "(b)", "(ii)", or "2(b)" when their parent question is identifiable. Group all subparts under the same parent question.
   - DO NOT duplicate the first subquestion's text at the parent level:
     * If there is shared introductory text/preamble before the first subquestion, put only that shared preamble in "question_text".
     * If there is no shared preamble, set the parent "question_text" to "Question <number>" and place the subquestion text in subquestion (a) (or the first sub).
   - Associate handwritten or printed answers with the specific subquestion they answer. Do NOT duplicate subquestion answers into the parent question.
   - If multiple-choice options are present (e.g. "(A) 5  (B) 10  (C) 15  (D) 20"), include them in the corresponding question or subquestion text.
   - MULTI-PAGE AWARENESS: If a question or subquestion appears to be cut off at the end of a page, it may continue on the next page. Use "partial_or_cutoff" in review_reasons to flag it.

5. ANSWER-KEY DOCUMENTS:
   - This document may be an exam answer key containing both the printed question and its solution.
   - Printed solution lines such as "E(X) = 2/3, E(Y) = 1/3, Cov(X,Y) = 1/36, Cor(X,Y) = 1/2" directly below a question ARE the answer key solutions.
   - Capture these printed solutions as the "answer" for the corresponding question or subquestion.
   - Do not treat printed solution steps as new questions. Solution paragraphs under a numbered question belong to that question.
   - Mark allocation indicators (e.g. "(1.5 M)", "(2M)") are grading metadata — do NOT include them in question text or answers.
   - Page headers, registration number fields, faculty names, course codes, and instruction text are metadata — do NOT include them as questions.

6. ANSWER PROVENANCE AND UNCERTAINTY FLAGGING:
   - Only associate an answer with a question or subquestion if the visual layout, numbering, or placement unambiguously links them.
   - If question hierarchy or Q&A pairing is genuinely ambiguous or unclear, do NOT guess. Set "needs_human_review": true and populate "review_reasons" with ["ambiguous_qa_association"] or ["ambiguous_question_hierarchy"].
   - If handwriting or symbols are faint, messy, partially cut off, or uncertain, assign an appropriately lower confidence_score (e.g. 0.50 to 0.70), set "needs_human_review": true, and add ["uncertain_transcription"] or ["illegible_handwriting"] to "review_reasons".
   - Assign realistic confidence_score values between 0.0 and 1.0 reflecting genuine visual transcription clarity.

Strictly adhere to the output JSON schema."""

USER_PROMPT = """Analyze this mathematical paper image.
Extract all visible questions, subquestions, and explicitly written answers.

KEY RULES:
- Group subparts (a), (b), (c) or (i), (ii), (iii) under their parent question number. Never emit standalone top-level items for sub-parts.
- For nested sub-subparts like (i)(a), (i)(b), use composite labels such as "(i)(a)" as the subquestion_label.
- If this page contains solution text under a question (answer-key style), capture the final stated result as the answer for that question or subquestion. Do not treat solution paragraphs as new questions.
- If a question appears cut off at page boundary, set review_reasons=["partial_or_cutoff"].
- Preserve all mathematical notation in standard LaTeX.
- Do NOT solve or complete any unanswered questions.
- If no answer is written for a question or subquestion, set "answer" to null and "has_explicit_answer" to false.
- If approximate bounding box coordinates [ymin, xmin, ymax, xmax] (0-1000) are reliable, include them; otherwise omit or set to null.
- Ignore page headers, metadata, mark allocations (e.g. "7 marks", "(1.5 M)"), faculty names, course codes, and registration fields."""

RECONCILIATION_SYSTEM_INSTRUCTION = """You are a mathematical exam paper cross-page hierarchy reconciler.
You receive structured raw extracted question and answer blocks across consecutive pages of an exam paper or answer key.

YOUR TASKS:
1. CROSS-PAGE CONTINUATION DETECTION & ANSWER-KEY HANDLING:
   - Identify questions or solutions that continue across page boundaries (e.g. Question 2(b) starting at the bottom of Page 2 and continuing onto Page 3, or Question 5(b) continuing onto Page 6).
   - If a solution block at the top of page N continues an unanswered question from page N-1 (e.g. Question 3(b) asked at the bottom of Page 3 with its solution block at the top of Page 4), associate that solution with that preceding question (Question 3(b)), NOT with the new question that begins below it (e.g. Question 4).
   - Do NOT merge unrelated questions simply because they appear on consecutive pages. Numbered questions (e.g. 1, 2, 3, 4, 5) are distinct top-level questions unless their numbers explicitly match.
   - Accurately populate the 'page_numbers' array (e.g. [2, 3] for Question 2; [3, 4] for Question 3; [5, 6] for Question 5).

2. QUESTION HIERARCHY & NESTED SUBQUESTIONS:
   - Group subquestions (a, b, c, i, ii, iii) under their proper parent question numbers (1, 2, 3, etc.).
   - Never create independent top-level items for lettered or numbered subparts when their parent is identifiable.
   - For Question 5(b) with nested parts like (i)(a), (i)(b), and (ii), reconstruct them under parent Question 5 with composite labels "(a)", "(b)(i)(a)" (or "(i)(a)"), "(b)(i)(b)" (or "(i)(b)"), and "(b)(ii)" (or "(ii)").
   - Never interpret a continuation label such as "(ii)" as a new top-level question.

3. ANSWER PROVENANCE & SOURCE BLOCK INTEGRITY:
   - Every extracted answer MUST have a traceable source block.
   - Every item in 'source_block_ids' MUST EXACTLY MATCH an existing input block ID (e.g. 'p1_b1', 'p2_q2a'). NEVER generate synthetic or hallucinated block IDs.
   - If a raw solution block contains multiple explicit answers (e.g. "Cov(X,Y) = 1/36" and "Cor(X,Y) = 1/2"), associate each specific answer with the matching subquestion.
   - NEVER invent, compute, or complete missing answers. If no answer is present in the blocks, keep answer null and has_explicit_answer false.

4. UNCERTAINTY FLAGGING:
   - If question hierarchy or Q&A pairing is genuinely ambiguous across page boundaries, set needs_human_review=true and add specific reasons in review_reasons (e.g. "ambiguous_question_hierarchy", "ambiguous_qa_association", "unverified_answer_source").

5. MATHEMATICAL NOTATION:
   - Preserve all standard LaTeX notation exactly.

Strictly adhere to the output JSON schema."""

RECONCILIATION_USER_PROMPT = """Reconcile the following page-level extracted mathematical blocks across consecutive pages.
Resolve cross-page question continuations, group subparts under parent questions, and preserve all explicit answers.
Populate source_block_ids and page_numbers for each question and subquestion.
Do NOT invent answers or modify mathematical notation."""


class ExtractorError(Exception):
    """Base exception for all extractor failures."""
    pass


class GeminiConfigurationError(ExtractorError):
    """Raised when the Gemini API key is missing or invalid."""
    pass


class EmptyModelResponseError(ExtractorError):
    """Raised when Gemini returns an empty or null response."""
    pass


class MalformedModelOutputError(ExtractorError):
    """Raised when Gemini returns unparseable or schema-invalid output."""

    def __init__(self, message: str, raw_output: Optional[str] = None) -> None:
        super().__init__(message)
        self.raw_output = raw_output


class RateLimitExceededError(ExtractorError):
    """Raised when API rate limits (429) persist after bounded retries."""
    pass


class ExtractionTimeoutError(ExtractorError):
    """Raised when Gemini request exceeds the configured timeout."""
    pass


class ProviderAPIError(ExtractorError):
    """Raised when upstream Gemini API encounters an error without exposing secrets."""

    def __init__(self, message: str, status_code: Optional[int] = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class UpstreamServiceUnavailableError(ProviderAPIError):
    """Raised when upstream Gemini API is temporarily unavailable (500, 502, 503, 504)."""

    def __init__(self, message: str, status_code: int = 503) -> None:
        super().__init__(message, status_code=status_code)


class GeminiMathExtractor:
    """Service for extracting mathematical questions and visible answers using Gemini Vision."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        fallback_model: Optional[str] = None,
        reconciliation_model: Optional[str] = None,
        reconciliation_timeout: Optional[float] = None,
        reconciliation_chunk_pages: Optional[int] = None,
        max_retries: Optional[int] = None,
        base_retry_delay: Optional[float] = None,
        max_retry_delay: Optional[float] = None,
        max_total_retry_duration: Optional[float] = None,
        timeout_seconds: float = 60.0,
        client: Optional[genai.Client] = None,
        response_schema: Optional[Union[type[PaperExtractionResult], Dict[str, Any]]] = None,
    ) -> None:
        self.api_key = api_key if api_key is not None else settings.GEMINI_API_KEY
        self.model = model or settings.GEMINI_MODEL

        # Configurable primary model and at most one verified fallback model
        fb = fallback_model if fallback_model is not None else getattr(settings, "GEMINI_FALLBACK_MODEL", None)
        if fb and str(fb).strip().lower() in ("none", "null", ""):
            fb = None
        self.fallback_model = fb if fb and fb != self.model else None

        # Stage 2 Cross-page reconciliation configuration
        self.reconciliation_model = (
            reconciliation_model
            if reconciliation_model is not None
            else getattr(settings, "GEMINI_RECONCILIATION_MODEL", "gemini-3.5-flash")
        )
        self.reconciliation_timeout = (
            reconciliation_timeout
            if reconciliation_timeout is not None
            else getattr(settings, "GEMINI_RECONCILIATION_TIMEOUT_SECONDS", 30.0)
        )
        self.reconciliation_chunk_pages = (
            reconciliation_chunk_pages
            if reconciliation_chunk_pages is not None
            else getattr(settings, "GEMINI_RECONCILIATION_CHUNK_PAGES", 10)
        )

        self.max_retries = (
            max_retries if max_retries is not None else getattr(settings, "GEMINI_MAX_RETRIES", 2)
        )
        self.base_retry_delay = (
            base_retry_delay
            if base_retry_delay is not None
            else getattr(settings, "GEMINI_BASE_RETRY_DELAY_SECONDS", 1.0)
        )
        self.max_retry_delay = (
            max_retry_delay
            if max_retry_delay is not None
            else getattr(settings, "GEMINI_MAX_RETRY_DELAY_SECONDS", 8.0)
        )
        self.max_total_retry_duration = (
            max_total_retry_duration
            if max_total_retry_duration is not None
            else getattr(settings, "GEMINI_MAX_TOTAL_RETRY_DURATION_SECONDS", 25.0)
        )
        self.timeout_seconds = timeout_seconds

        if response_schema is not None:
            self.response_schema = build_gemini_compatible_schema(response_schema)
        else:
            self.response_schema = get_gemini_extraction_schema()

        if client is not None:
            self._client = client
        elif self.api_key and self.api_key.strip():
            self._client = genai.Client(api_key=self.api_key.strip())
        else:
            self._client = None

    def _ensure_client(self) -> genai.Client:
        """Validate configuration and return active genai.Client instance."""
        if self._client is not None:
            return self._client
        if not self.api_key or not self.api_key.strip():
            raise GeminiConfigurationError(
                "GEMINI_API_KEY is not configured. Please set the GEMINI_API_KEY environment variable."
            )
        self._client = genai.Client(api_key=self.api_key.strip())
        return self._client

    def _sanitize(self, message: str) -> str:
        """Sanitize error messages to prevent leaking API keys or secrets."""
        if not message:
            return ""
        if self.api_key and len(self.api_key) > 5:
            message = message.replace(self.api_key, "[REDACTED_API_KEY]")
        # Redact Google API key signature pattern (AIzaSy...)
        message = re.sub(r"AIza[0-9A-Za-z\-_]{35}", "[REDACTED_API_KEY]", message)
        message = re.sub(r"key=[A-Za-z0-9_\-]+", "key=[REDACTED]", message)
        return message

    def _clean_json_text(self, text: str) -> str:
        """Strip markdown code fence formatting if present."""
        cleaned = text.strip()
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
        return cleaned

    def _repair_truncated_json(self, text: str) -> str:
        """Attempt to repair a JSON string that was truncated mid-stream.

        When Gemini hits its output token limit the response JSON is cut off mid-token.
        We close open strings and arrays/objects so that Pydantic can at least parse
        whatever was successfully emitted.  This is a best-effort approach — if the
        truncation occurred inside a critical required field the validation step will
        still fail, but we avoid losing all extracted data when only the last item is
        clipped.
        """
        s = text.rstrip()
        if not s:
            return s

        # Close any unterminated string — find whether we're inside a string
        in_string = False
        escape_next = False
        for ch in s:
            if escape_next:
                escape_next = False
                continue
            if ch == "\\":
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string

        if in_string:
            # Truncated inside a string value — close it
            s = s + '"'

        # Count and close open brackets
        depth_curly = 0
        depth_square = 0
        in_str = False
        esc = False
        for ch in s:
            if esc:
                esc = False
                continue
            if ch == "\\":
                esc = True
                continue
            if ch == '"':
                in_str = not in_str
                continue
            if in_str:
                continue
            if ch == "{":
                depth_curly += 1
            elif ch == "}":
                depth_curly = max(0, depth_curly - 1)
            elif ch == "[":
                depth_square += 1
            elif ch == "]":
                depth_square = max(0, depth_square - 1)

        # Close open arrays first (innermost), then objects
        s = s + ("]" * depth_square) + ("}" * depth_curly)
        return s

    def extract_from_image(
        self,
        image_result: PreprocessedImageResult,
        use_fallback_original: bool = False,
    ) -> PaperExtractionResult:
        """Extract mathematical content from preprocessed image with structured validation.

        Parameters:
            image_result: The PreprocessedImageResult from ImagePreprocessor.
            use_fallback_original: If True, passes unmodified original_bytes instead of processed_bytes.

        Returns:
            Validated PaperExtractionResult adhering strictly to domain schema.
        """
        client = self._ensure_client()
        image_bytes = image_result.get_effective_bytes(use_original=use_fallback_original)
        mime_type = image_result.mime_type

        # Prepare multimodal request parts
        image_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=self.response_schema,
            system_instruction=SYSTEM_INSTRUCTION,
            temperature=0.1,  # Low temperature for factual transcription fidelity
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

        raw_response_text = self._call_with_bounded_retries(
            client=client,
            contents=[image_part, USER_PROMPT],
            config=config,
        )

        if not raw_response_text or not raw_response_text.strip():
            raise EmptyModelResponseError(
                "Gemini returned an empty response. No content was generated."
            )

        cleaned_json = self._clean_json_text(raw_response_text)

        try:
            validated_result = PaperExtractionResult.model_validate_json(cleaned_json)
        except (ValidationError, Exception) as first_err:
            # Attempt to repair truncated JSON (e.g. response hit output token limit)
            repaired_json = self._repair_truncated_json(cleaned_json)
            if repaired_json != cleaned_json:
                try:
                    validated_result = PaperExtractionResult.model_validate_json(repaired_json)
                    logger.warning(
                        "Gemini response was truncated and auto-repaired. "
                        "Some questions from this page may be incomplete."
                    )
                except (ValidationError, Exception) as repair_err:
                    raise MalformedModelOutputError(
                        f"Model response failed schema validation (repair also failed): {repair_err}",
                        raw_output=cleaned_json,
                    ) from repair_err
            elif isinstance(first_err, ValidationError):
                raise MalformedModelOutputError(
                    f"Model response failed schema validation: {first_err}",
                    raw_output=cleaned_json,
                ) from first_err
            else:
                raise MalformedModelOutputError(
                    f"Failed to parse JSON response from model: {first_err}",
                    raw_output=cleaned_json,
                ) from first_err

        # Ensure page numbers and source_block_ids are tagged if not already present
        if not validated_result.raw_blocks:
            synthesized_blocks = []
            for q in validated_result.questions:
                b_id = f"p1_q{q.question_number}"
                if not q.source_block_ids:
                    object.__setattr__(q, "source_block_ids", [b_id])
                synthesized_blocks.append(
                    RawExtractedBlock(
                        block_id=b_id,
                        page_number=1,
                        block_type="question",
                        raw_label=q.question_number,
                        text=q.question_text,
                        explicit_answer=q.answer,
                        has_explicit_answer=q.has_explicit_answer,
                        bounding_box=q.bounding_box,
                        confidence_score=q.confidence_score,
                        review_reasons=q.review_reasons,
                    )
                )
                for sq in q.subquestions:
                    sq_b_id = f"{b_id}_{sq.subquestion_label.strip('()')}"
                    if not sq.source_block_ids:
                        object.__setattr__(sq, "source_block_ids", [sq_b_id])
                    synthesized_blocks.append(
                        RawExtractedBlock(
                            block_id=sq_b_id,
                            page_number=1,
                            block_type="subquestion",
                            raw_label=sq.subquestion_label,
                            text=sq.text,
                            explicit_answer=sq.answer,
                            has_explicit_answer=sq.has_explicit_answer,
                            bounding_box=sq.bounding_box,
                            confidence_score=sq.confidence_score,
                            review_reasons=sq.review_reasons,
                        )
                    )
            object.__setattr__(validated_result, "raw_blocks", synthesized_blocks)

        for q in validated_result.questions:
            if q.page_number is None:
                object.__setattr__(q, "page_number", 1)
            if not q.page_numbers:
                object.__setattr__(q, "page_numbers", [1])
            for sq in q.subquestions:
                if sq.page_number is None:
                    object.__setattr__(sq, "page_number", 1)

        return validated_result

    def extract_from_pdf_pages(
        self,
        pages: List[Tuple[int, PreprocessedImageResult]],
        use_fallback_original: bool = False,
        use_reconciliation_model: bool = True,
    ) -> PaperExtractionResult:
        """Extract mathematical content from multiple preprocessed PDF pages.

        Parameters:
            pages: List of (page_number, PreprocessedImageResult) tuples.
            use_fallback_original: Whether to pass raw original image bytes.
            use_reconciliation_model: Whether to use Stage 2 cross-page LLM reconciliation.

        Returns:
            Aggregated and hierarchy-reconciled PaperExtractionResult preserving page numbers.
        """
        if not pages:
            return PaperExtractionResult(total_pages_detected=1, questions=[], raw_blocks=[])

        if len(pages) == 1:
            page_num, image_result = pages[0]
            result = self.extract_from_image(
                image_result=image_result,
                use_fallback_original=use_fallback_original,
            )
            for q in result.questions:
                object.__setattr__(q, "page_number", page_num)
                object.__setattr__(q, "page_numbers", [page_num])
                for sq in q.subquestions:
                    object.__setattr__(sq, "page_number", page_num)
            for b in result.raw_blocks:
                object.__setattr__(b, "page_number", page_num)
            object.__setattr__(result, "total_pages_detected", 1)
            return result

        # Multi-page PDF extraction across consecutive pages
        all_questions: List[QuestionItem] = []
        all_raw_blocks: List[RawExtractedBlock] = []
        paper_title: Optional[str] = None
        notes_parts: List[str] = []
        doc_review_reasons: List[str] = []
        requires_review = False

        for page_num, image_result in pages:
            page_result = self.extract_from_image(
                image_result=image_result,
                use_fallback_original=use_fallback_original,
            )
            if not paper_title and page_result.paper_title:
                paper_title = page_result.paper_title
            if page_result.notes:
                notes_parts.append(f"Page {page_num}: {page_result.notes}")
            if page_result.requires_human_review:
                requires_review = True
            doc_review_reasons.extend(page_result.review_reasons)

            for q in page_result.questions:
                object.__setattr__(q, "page_number", page_num)
                object.__setattr__(q, "page_numbers", [page_num])
                q_b_id = f"p{page_num}_q{q.question_number}"
                if not q.source_block_ids:
                    object.__setattr__(q, "source_block_ids", [q_b_id])
                else:
                    prefixed = [
                        bid if bid.startswith(f"p{page_num}_") else f"p{page_num}_{bid}"
                        for bid in q.source_block_ids
                    ]
                    object.__setattr__(q, "source_block_ids", prefixed)

                for sq in q.subquestions:
                    object.__setattr__(sq, "page_number", page_num)
                    sq_b_id = f"p{page_num}_q{q.question_number}_{sq.subquestion_label.strip('()')}"
                    if not sq.source_block_ids:
                        object.__setattr__(sq, "source_block_ids", [sq_b_id])
                    else:
                        prefixed = [
                            bid if bid.startswith(f"p{page_num}_") else f"p{page_num}_{bid}"
                            for bid in sq.source_block_ids
                        ]
                        object.__setattr__(sq, "source_block_ids", prefixed)

                all_questions.append(q)

            for b in page_result.raw_blocks:
                b_id = b.block_id if b.block_id.startswith(f"p{page_num}_") else f"p{page_num}_{b.block_id}"
                object.__setattr__(b, "block_id", b_id)
                object.__setattr__(b, "page_number", page_num)
                all_raw_blocks.append(b)

        combined_notes = " | ".join(notes_parts) if notes_parts else None

        # Stage 2: Cross-Page Reconciliation
        return self._reconcile_cross_page(
            all_questions=all_questions,
            all_raw_blocks=all_raw_blocks,
            pages_count=len(pages),
            paper_title=paper_title,
            notes=combined_notes,
            use_reconciliation_model=use_reconciliation_model,
        )

    def _reconcile_cross_page(
        self,
        all_questions: List[QuestionItem],
        all_raw_blocks: List[RawExtractedBlock],
        pages_count: int,
        paper_title: Optional[str] = None,
        notes: Optional[str] = None,
        use_reconciliation_model: bool = True,
    ) -> PaperExtractionResult:
        """Stage 2: Reconcile question hierarchy and associate answers across consecutive pages."""
        if not use_reconciliation_model:
            reconciled_qs = reconcile_question_hierarchy(all_questions)
            verify_answer_sources(reconciled_qs, all_raw_blocks)
            return PaperExtractionResult(
                paper_title=paper_title,
                total_pages_detected=pages_count,
                questions=reconciled_qs,
                raw_blocks=all_raw_blocks,
                reconciliation_mode="deterministic_fallback",
                notes=notes,
            )

        client = None
        try:
            client = self._ensure_client()
        except Exception:
            client = None

        if client is None:
            reconciled_qs = reconcile_question_hierarchy(all_questions)
            verify_answer_sources(reconciled_qs, all_raw_blocks)
            return PaperExtractionResult(
                paper_title=paper_title,
                total_pages_detected=pages_count,
                questions=reconciled_qs,
                raw_blocks=all_raw_blocks,
                reconciliation_mode="deterministic_fallback",
                notes=notes,
            )

        pages_payload = []
        for p in range(1, pages_count + 1):
            p_blocks = [
                {
                    "block_id": b.block_id,
                    "block_type": b.block_type,
                    "raw_label": b.raw_label,
                    "text": b.text,
                    "explicit_answer": b.explicit_answer,
                    "has_explicit_answer": b.has_explicit_answer,
                    "bounding_box": b.bounding_box.model_dump() if b.bounding_box else None,
                }
                for b in all_raw_blocks
                if b.page_number == p
            ]
            pages_payload.append({
                "page_number": p,
                "blocks": p_blocks,
            })

        reconcile_input_json = json.dumps(
            {
                "paper_title": paper_title,
                "total_pages": pages_count,
                "pages": pages_payload,
            },
            indent=2,
        )

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=self.response_schema,
            system_instruction=RECONCILIATION_SYSTEM_INSTRUCTION,
            temperature=0.1,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )

        t_start = time.perf_counter()
        try:
            response = client.models.generate_content(
                model=self.reconciliation_model,
                contents=[RECONCILIATION_USER_PROMPT, reconcile_input_json],
                config=config,
            )
            t_elapsed_ms = (time.perf_counter() - t_start) * 1000.0

            usage = getattr(response, "usage_metadata", None)
            if usage:
                logger.info(
                    "Stage 2 Cross-Page Reconciliation (Model: %s) took %.2fms | Tokens: prompt=%s, candidates=%s, total=%s",
                    self.reconciliation_model,
                    t_elapsed_ms,
                    getattr(usage, "prompt_token_count", None),
                    getattr(usage, "candidates_token_count", None),
                    getattr(usage, "total_token_count", None),
                )
            else:
                logger.info(
                    "Stage 2 Cross-Page Reconciliation (Model: %s) took %.2fms",
                    self.reconciliation_model,
                    t_elapsed_ms,
                )

            raw_text = getattr(response, "text", None)
            if not raw_text or not isinstance(raw_text, str) or not raw_text.strip():
                raise EmptyModelResponseError("Reconciler returned empty response")

            cleaned_json = self._clean_json_text(raw_text)
            reconciled_result = PaperExtractionResult.model_validate_json(cleaned_json)

            object.__setattr__(reconciled_result, "reconciliation_mode", "gemini_cross_page")
            object.__setattr__(reconciled_result, "raw_blocks", all_raw_blocks)
            if paper_title and not reconciled_result.paper_title:
                object.__setattr__(reconciled_result, "paper_title", paper_title)
            object.__setattr__(reconciled_result, "total_pages_detected", pages_count)

            verify_answer_sources(reconciled_result.questions, all_raw_blocks)
            return reconciled_result

        except Exception as exc:
            logger.warning(
                "Stage 2 cross-page reconciliation failed (%s). Falling back to deterministic reconciler with human review flags.",
                exc,
            )
            fallback_qs = reconcile_question_hierarchy(all_questions)

            for q in fallback_qs:
                if len(q.page_numbers) > 1 or any(sq.page_number != q.page_number for sq in q.subquestions if sq.page_number and q.page_number):
                    object.__setattr__(q, "needs_human_review", True)
                    reasons = list(q.review_reasons)
                    if ReviewReason.RECONCILIATION_FALLBACK_USED.value not in reasons:
                        reasons.append(ReviewReason.RECONCILIATION_FALLBACK_USED.value)
                    object.__setattr__(q, "review_reasons", reasons)

            verify_answer_sources(fallback_qs, all_raw_blocks)

            fallback_notes = f"{notes or ''} [Reconciliation fallback used: {exc}]".strip()
            return PaperExtractionResult(
                paper_title=paper_title,
                total_pages_detected=pages_count,
                questions=fallback_qs,
                raw_blocks=all_raw_blocks,
                reconciliation_mode="deterministic_fallback",
                requires_human_review=True,
                review_reasons=[ReviewReason.RECONCILIATION_FALLBACK_USED.value],
                notes=fallback_notes,
            )

    def _extract_retry_after(self, err: Exception) -> Optional[float]:
        """Extract Retry-After delay in seconds from error response if available."""
        # 1. Check response headers
        response = getattr(err, "response", None)
        headers = getattr(response, "headers", None) or getattr(err, "headers", None)
        if headers and hasattr(headers, "get"):
            val = headers.get("retry-after") or headers.get("Retry-After")
            if val:
                try:
                    return float(val)
                except (ValueError, TypeError):
                    try:
                        from email.utils import parsedate_to_datetime
                        import datetime
                        dt = parsedate_to_datetime(str(val))
                        now = datetime.datetime.now(datetime.timezone.utc)
                        diff = (dt - now).total_seconds()
                        if diff > 0:
                            return diff
                    except Exception:
                        pass

        # 2. Check response_json for Google RPC RetryInfo
        response_json = getattr(err, "response_json", None)
        if isinstance(response_json, dict):
            error_dict = response_json.get("error", {})
            details = error_dict.get("details", []) if isinstance(error_dict, dict) else []
            if isinstance(details, list):
                for d in details:
                    if isinstance(d, dict) and "RetryInfo" in d.get("@type", ""):
                        retry_delay = d.get("retryDelay")
                        if isinstance(retry_delay, str) and retry_delay.endswith("s"):
                            try:
                                return float(retry_delay[:-1])
                            except ValueError:
                                pass
                        elif isinstance(retry_delay, (int, float)):
                            return float(retry_delay)

        # 3. Check error string for "retry after X seconds" or "retry in X.Xs"
        msg = str(err)
        m = re.search(r"retry\s+(?:after|in)\s+([0-9]+(?:\.[0-9]+)?)\s*s", msg, re.I)
        if m:
            try:
                return float(m.group(1))
            except ValueError:
                pass

        return None

    def _calculate_backoff_delay(self, retry_num: int, retry_after: Optional[float] = None) -> float:
        """Calculate backoff delay with jitter, respecting Retry-After when available."""
        if retry_after is not None and retry_after > 0:
            delay = min(retry_after, self.max_retry_delay)
            # Add small random jitter (0 to 10% of delay, max 0.5s)
            jitter = random.uniform(0.0, min(0.5, delay * 0.1))
            return delay + jitter

        exp_delay = min(self.max_retry_delay, self.base_retry_delay * (2 ** (retry_num - 1)))
        # Bounded exponential backoff with full jitter (50% to 100% of exp_delay)
        return random.uniform(0.5 * exp_delay, exp_delay)

    def _classify_error(self, err: Exception) -> Tuple[Optional[int], bool, bool]:
        """Classify an exception into (status_code, is_transient, is_permanent).

        Transient: 429, 500, 502, 503, 504, timeouts, connection issues.
        Permanent: 400 (bad request/invalid schema), 401 (unauthorized), 403 (forbidden).
        Model Not Found: 404 (non-transient on that model, candidate for fallback model).
        """
        status_code = getattr(err, "code", None)
        err_msg = str(err).lower()

        # Check explicit HTTP status codes
        if status_code is not None:
            if status_code in (400, 401, 403):
                return status_code, False, True
            if status_code in (429, 500, 502, 503, 504):
                return status_code, True, False
            if status_code == 404:
                return 404, False, False

        # Check error message text for key patterns
        if "api key" in err_msg or "unauthenticated" in err_msg or "permission denied" in err_msg:
            return 403 if "permission" in err_msg else 401, False, True

        if "invalid argument" in err_msg or "bad request" in err_msg:
            return 400, False, True

        if "resource_exhausted" in err_msg or "429" in err_msg:
            return 429, True, False

        if "503" in err_msg or "service unavailable" in err_msg:
            return 503, True, False

        if "504" in err_msg or "gateway timeout" in err_msg or "timed out" in err_msg or "timeout" in err_msg:
            return 504, True, False

        if "502" in err_msg or "bad gateway" in err_msg:
            return 502, True, False

        if "500" in err_msg or "internal error" in err_msg:
            return 500, True, False

        if "not found" in err_msg or "is not supported" in err_msg:
            return 404, False, False

        # TimeoutError
        if isinstance(err, TimeoutError):
            return 504, True, False

        # Default: treat unknown APIError as provider error
        if isinstance(err, errors.APIError):
            return status_code, False, False

        return status_code, False, False

    def _call_with_bounded_retries(
        self,
        client: genai.Client,
        contents: list,
        config: types.GenerateContentConfig,
    ) -> str:
        """Execute model request with bounded retries and at most one verified fallback."""
        candidate_models = [self.model]
        if self.fallback_model and self.fallback_model != self.model:
            candidate_models.append(self.fallback_model)

        model_idx = 0
        retries_on_model = 0
        start_time = time.monotonic()
        last_status_code: Optional[int] = None

        while True:
            current_model = candidate_models[model_idx]
            elapsed = time.monotonic() - start_time

            if elapsed >= self.max_total_retry_duration:
                logger.warning(
                    "Total retry duration budget exhausted (%.2fs >= %.2fs) on model %s.",
                    elapsed,
                    self.max_total_retry_duration,
                    current_model,
                )
                if last_status_code == 429:
                    raise RateLimitExceededError(self._sanitize("Gemini API rate limit exceeded (429)."))
                if last_status_code in (500, 502, 503, 504):
                    raise UpstreamServiceUnavailableError(
                        self._sanitize(f"Upstream Gemini API is temporarily unavailable ({last_status_code})."),
                        status_code=last_status_code,
                    )
                raise ExtractionTimeoutError("Gemini extraction retry budget exhausted.")

            try:
                response = client.models.generate_content(
                    model=current_model,
                    contents=contents,
                    config=config,
                )
                if response.text is not None:
                    return response.text
                return ""

            except Exception as err:
                status_code, is_transient, is_permanent = self._classify_error(err)
                last_status_code = status_code

                # 1. Permanent 4xx errors (400, 401, 403, invalid key) -> DO NOT RETRY
                if is_permanent:
                    logger.error(
                        "Permanent error (%s) on model %s. Retries aborted: %s",
                        status_code,
                        current_model,
                        self._sanitize(str(err)),
                    )
                    raise ProviderAPIError(
                        self._sanitize(f"Gemini API returned error ({status_code}): {err}"),
                        status_code=status_code,
                    ) from err

                # 2. Model Not Found (404) -> switch to verified fallback model if available
                if status_code == 404:
                    if model_idx + 1 < len(candidate_models):
                        model_idx += 1
                        retries_on_model = 0
                        logger.warning(
                            "Model %s not found (404). Switching to verified fallback model %s...",
                            candidate_models[model_idx - 1],
                            candidate_models[model_idx],
                        )
                        continue
                    else:
                        raise ProviderAPIError(
                            self._sanitize(f"Gemini model not found ({current_model}): {err}"),
                            status_code=404,
                        ) from err

                # 3. Transient errors (429, 500, 502, 503, 504, timeouts)
                if is_transient:
                    # Can we retry on the current model?
                    if retries_on_model < self.max_retries:
                        retries_on_model += 1
                        retry_after = self._extract_retry_after(err)
                        delay = self._calculate_backoff_delay(retries_on_model, retry_after)

                        elapsed = time.monotonic() - start_time
                        remaining = self.max_total_retry_duration - elapsed
                        if remaining <= 0:
                            logger.warning("Retry budget reached before sleep on model %s.", current_model)
                            if status_code == 429:
                                raise RateLimitExceededError(self._sanitize("Gemini API rate limit exceeded (429)."))
                            if status_code in (500, 502, 503, 504):
                                raise UpstreamServiceUnavailableError(
                                    self._sanitize(f"Upstream Gemini API is temporarily unavailable ({status_code})."),
                                    status_code=status_code,
                                )
                            raise ExtractionTimeoutError("Extraction retry budget exhausted.")

                        sleep_time = min(delay, remaining)
                        logger.warning(
                            "Transient Gemini error (%s) on model %s (attempt %d/%d). Retrying in %.2fs (retry_after=%s)...",
                            status_code,
                            current_model,
                            retries_on_model,
                            self.max_retries,
                            sleep_time,
                            f"{retry_after:.1f}s" if retry_after is not None else "None",
                        )
                        time.sleep(sleep_time)
                        continue

                    # Retries on current model are exhausted
                    if status_code == 429:
                        logger.error("Rate limit retries exhausted on model %s.", current_model)
                        raise RateLimitExceededError(self._sanitize("Gemini API rate limit exceeded (429).")) from err

                    # For 500/502/503/504: switch to fallback model if available (at most one)
                    if model_idx + 1 < len(candidate_models):
                        model_idx += 1
                        retries_on_model = 0
                        logger.warning(
                            "Primary model %s failed (%s) after retries. Attempting fallback model %s...",
                            candidate_models[model_idx - 1],
                            status_code,
                            candidate_models[model_idx],
                        )
                        continue
                    else:
                        # All models exhausted!
                        logger.error(
                            "All candidate models exhausted. Last error was %s on model %s.",
                            status_code,
                            current_model,
                        )
                        raise UpstreamServiceUnavailableError(
                            self._sanitize(f"Upstream Gemini API is temporarily unavailable ({status_code}): {err}"),
                            status_code=status_code or 503,
                        ) from err

                # Unknown/unhandled error
                logger.error("Unhandled Gemini error on model %s: %s", current_model, self._sanitize(str(err)))
                raise ProviderAPIError(
                    self._sanitize(f"Gemini API returned error ({status_code}): {err}"),
                    status_code=status_code,
                ) from err
