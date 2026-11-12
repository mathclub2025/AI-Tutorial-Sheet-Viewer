"""Pydantic v2 schemas for mathematical paper extraction."""

import copy
import re
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ReviewReason(str, Enum):
    """Standardized reasons for flagging an item for human review."""

    UNCERTAIN_TRANSCRIPTION = "uncertain_transcription"
    AMBIGUOUS_QA_ASSOCIATION = "ambiguous_qa_association"
    ILLEGIBLE_HANDWRITING = "illegible_handwriting"
    POOR_IMAGE_QUALITY = "poor_image_quality"
    PARTIAL_OR_CUTOFF = "partial_or_cutoff"
    COMPLEX_LAYOUT = "complex_layout"
    AMBIGUOUS_QUESTION_HIERARCHY = "ambiguous_question_hierarchy"
    UNVERIFIED_ANSWER_SOURCE = "unverified_answer_source"
    RECONCILIATION_FALLBACK_USED = "reconciliation_fallback_used"
    OTHER = "other"


class NormalizedBoundingBox(BaseModel):
    """Normalized bounding box coordinates [0, 1000] following Gemini Vision conventions."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    ymin: int = Field(ge=0, le=1000, description="Top edge (0-1000)")
    xmin: int = Field(ge=0, le=1000, description="Left edge (0-1000)")
    ymax: int = Field(ge=0, le=1000, description="Bottom edge (0-1000)")
    xmax: int = Field(ge=0, le=1000, description="Right edge (0-1000)")

    @model_validator(mode="after")
    def validate_coordinate_ordering(self) -> "NormalizedBoundingBox":
        """Validate and guarantee valid coordinate ordering: ymin <= ymax and xmin <= xmax."""
        y1, y2 = self.ymin, self.ymax
        if y1 > y2:
            object.__setattr__(self, "ymin", y2)
            object.__setattr__(self, "ymax", y1)
        x1, x2 = self.xmin, self.xmax
        if x1 > x2:
            object.__setattr__(self, "xmin", x2)
            object.__setattr__(self, "xmax", x1)
        return self


class RawExtractedBlock(BaseModel):
    """Preserved raw block extracted from an individual page prior to cross-page reconciliation."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    block_id: str = Field(description="Unique block identifier within document, e.g. 'p1_b1'")
    page_number: int = Field(ge=1, description="1-based page number")
    block_type: str = Field(
        default="question",
        description="'question_prompt', 'subquestion', 'solution_text', 'final_answer', or 'continuation'",
    )
    raw_label: Optional[str] = Field(
        default=None,
        description="Explicit question or subpart label, e.g. '1', '(a)', '2(b)'",
    )
    text: str = Field(description="Raw transcribed mathematical text in LaTeX")
    explicit_answer: Optional[str] = Field(
        default=None,
        description="Explicitly stated final answer if present in block",
    )
    has_explicit_answer: bool = Field(default=False)
    bounding_box: Optional[NormalizedBoundingBox] = Field(default=None)
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0)
    review_reasons: List[str] = Field(default_factory=list)


class SubQuestion(BaseModel):
    """Schema representing an individual subquestion under a main question."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    subquestion_label: str = Field(
        ...,
        description="Subquestion identifier such as '(a)', '(b)', 'i', 'ii', or 'part 1'.",
        min_length=1,
    )
    text: str = Field(
        ...,
        description="The transcribed subquestion text, preserving mathematical notation in LaTeX formatting (e.g. fractions, matrices, integrals, superscripts/subscripts).",
        min_length=1,
    )
    answer: Optional[str] = Field(
        default=None,
        description="The answer explicitly written on the paper. MUST BE null if not visibly written. NEVER solve or fabricate.",
    )
    has_explicit_answer: bool = Field(
        default=False,
        description="Whether an explicit answer was visibly written on the paper for this subquestion.",
    )
    confidence_score: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Model confidence score between 0.0 and 1.0 regarding transcription fidelity.",
    )
    page_number: Optional[int] = Field(
        default=None,
        ge=1,
        description="1-based original document page number where this subquestion appears.",
    )
    bounding_box: Optional[NormalizedBoundingBox] = Field(
        default=None,
        description="Optional normalized bounding box [ymin, xmin, ymax, xmax] in [0, 1000].",
    )
    source_block_ids: List[str] = Field(
        default_factory=list,
        description="List of raw block identifiers that contributed to this subquestion.",
    )
    needs_human_review: bool = Field(
        default=False,
        description="Flag set to True if transcription is uncertain or Q&A pairing is ambiguous.",
    )
    review_reasons: List[str] = Field(
        default_factory=list,
        description="List of specific reasons why human review is required.",
    )

    @model_validator(mode="after")
    def validate_answer_consistency_and_review(self) -> "SubQuestion":
        """Ensure answer presence consistency and review flag synchronization."""
        # Answer consistency
        if self.answer is None or not self.answer.strip():
            object.__setattr__(self, "answer", None)
            object.__setattr__(self, "has_explicit_answer", False)
        else:
            object.__setattr__(self, "has_explicit_answer", True)

        # Review flag consistency
        reasons = list(self.review_reasons)
        needs_review = self.needs_human_review

        if reasons and not needs_review:
            needs_review = True
        elif needs_review and not reasons:
            reasons.append(ReviewReason.UNCERTAIN_TRANSCRIPTION.value)

        # Low confidence auto-flagging
        if self.confidence_score < 0.75:
            needs_review = True
            if ReviewReason.UNCERTAIN_TRANSCRIPTION.value not in reasons:
                reasons.append(ReviewReason.UNCERTAIN_TRANSCRIPTION.value)

        object.__setattr__(self, "needs_human_review", needs_review)
        object.__setattr__(self, "review_reasons", reasons)
        return self


class QuestionItem(BaseModel):
    """Schema representing a top-level question extracted from the paper."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    question_number: str = Field(
        ...,
        description="Question identifier or numbering (e.g. '1', 'Q2', 'Problem 3', 'Section A - 1').",
        min_length=1,
    )
    question_text: str = Field(
        ...,
        description="The full question prompt text, preserving all mathematical notation (LaTeX matrices, integrals, fractions, exponents, etc.).",
        min_length=1,
    )
    subquestions: List[SubQuestion] = Field(
        default_factory=list,
        description="Optional list of subquestions if this question is subdivided.",
    )
    answer: Optional[str] = Field(
        default=None,
        description="The answer explicitly written on the paper. MUST BE null if not visibly written. NEVER solve or compute.",
    )
    has_explicit_answer: bool = Field(
        default=False,
        description="Whether an explicit answer was visibly written on the paper for this question.",
    )
    confidence_score: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence score between 0.0 and 1.0 for the transcription and association accuracy.",
    )
    page_number: Optional[int] = Field(
        default=None,
        ge=1,
        description="1-based primary page number where this question appears.",
    )
    page_numbers: List[int] = Field(
        default_factory=list,
        description="List of 1-based page numbers this question spans.",
    )
    bounding_box: Optional[NormalizedBoundingBox] = Field(
        default=None,
        description="Optional normalized bounding box [ymin, xmin, ymax, xmax] in [0, 1000].",
    )
    source_block_ids: List[str] = Field(
        default_factory=list,
        description="List of raw block identifiers that contributed to this question.",
    )
    needs_human_review: bool = Field(
        default=False,
        description="Flag indicating if this question requires manual human verification.",
    )
    review_reasons: List[str] = Field(
        default_factory=list,
        description="Specific reasons requiring human review.",
    )

    @model_validator(mode="after")
    def validate_answer_consistency_and_review(self) -> "QuestionItem":
        """Ensure answer presence consistency and review flag synchronization."""
        # Answer consistency
        if self.answer is None or not self.answer.strip():
            object.__setattr__(self, "answer", None)
            object.__setattr__(self, "has_explicit_answer", False)
        else:
            object.__setattr__(self, "has_explicit_answer", True)

        reasons = list(self.review_reasons)
        needs_review = self.needs_human_review

        # Review flag consistency
        if reasons and not needs_review:
            needs_review = True
        elif needs_review and not reasons:
            reasons.append(ReviewReason.UNCERTAIN_TRANSCRIPTION.value)

        # Low confidence auto-flagging
        if self.confidence_score < 0.75:
            needs_review = True
            if ReviewReason.UNCERTAIN_TRANSCRIPTION.value not in reasons:
                reasons.append(ReviewReason.UNCERTAIN_TRANSCRIPTION.value)

        # Bubble up subquestion review flags
        if any(sq.needs_human_review for sq in self.subquestions):
            needs_review = True
            if "subquestion_requires_review" not in reasons:
                reasons.append("subquestion_requires_review")

        # Synchronize page_number and page_numbers
        pages = set(self.page_numbers)
        if self.page_number is not None:
            pages.add(self.page_number)
        for sq in self.subquestions:
            if sq.page_number is not None:
                pages.add(sq.page_number)
        if pages:
            sorted_pages = sorted(list(pages))
            object.__setattr__(self, "page_numbers", sorted_pages)
            if self.page_number is None:
                object.__setattr__(self, "page_number", sorted_pages[0])

        object.__setattr__(self, "needs_human_review", needs_review)
        object.__setattr__(self, "review_reasons", reasons)
        return self


def normalize_sublabel(label: str) -> str:
    """Normalize subquestion label to standard format.

    Handles single labels like 'b' -> '(b)', '(a)' -> '(a)',
    and composite nested labels like '(i)(a)' -> '(i)(a)' (preserved as-is).
    """
    clean = label.strip()
    # Composite labels like (i)(a), (i)(b) — preserve as-is
    if re.match(r"^(\([a-zA-Z0-9]+\)){2,}$", clean):
        return clean
    if clean.startswith("(") and clean.endswith(")"):
        return clean
    if clean.startswith("[") and clean.endswith("]"):
        return f"({clean[1:-1].strip()})"
    return f"({clean})"


def normalize_parent_key(q_num: str) -> str:
    """Normalize question identifier for comparison by stripping common prefixes and continuation suffixes."""
    clean = re.sub(r"^(?:Question|Problem|Q|Part|Section)\s*", "", q_num.strip(), flags=re.I)
    clean = re.sub(r"\s*[\(\[]?(?:continued|cont\.?|contd\.?)[\)\]]?\s*$", "", clean, flags=re.I)
    return clean.strip().lower()


def extract_parent_and_sublabel(q_num: str) -> Tuple[Optional[str], Optional[str]]:
    """Check if question_number represents a compound parent+sublabel or standalone sublabel.

    Returns:
        (parent_number, sublabel) if compound (e.g. ('2', '(b)') for '2(b)')
        (None, sublabel) if standalone sublabel (e.g. (None, '(b)') for '(b)' or 'b')
        (None, None) if normal top-level question (e.g. '1', 'Question 2')
    """
    clean = q_num.strip()

    # 0. Composite nested label like "(i)(a)", "(i)(b)" — these are already a sublabel string
    #    representing a flattened sub-subquestion; treat as standalone sublabel.
    if re.match(r"^(\([a-zA-Z0-9]+\)){2,}$", clean):
        return None, clean  # Will attach to last reconciled parent

    # 1. Compound pattern like '2(b)', '2[b]', '2.b', '2-b', '2b', 'Q2(b)', 'Question 2(b)'
    #    Also handles '5(b)(i)', '5b(i)(a)' (compound with nested suffix)
    m = re.match(
        r"^(?P<prefix>.*?)(?P<parent>\d+|[A-Z]\d*)\s*[\.\-\_]?\s*[\(\[]?(?P<sublabel>[a-zA-Z]|[ivxlcdmIVXLCDM]+)[\)\]]?(?P<rest>[\(\[][a-zA-Z0-9]+[\)\]])*$",
        clean,
    )
    if m:
        parent_num = m.group("parent")
        prefix = m.group("prefix").strip()
        sublabel = m.group("sublabel")
        rest = m.group("rest") or ""
        if not sublabel.isdigit():
            full_parent = f"{prefix} {parent_num}".strip() if prefix else parent_num
            # Include any further nested suffixes in the sublabel
            composite = normalize_sublabel(sublabel)
            if rest:
                composite = composite + rest
            return full_parent, composite

    # 2. Standalone subquestion label like '(b)', 'b', 'b)', '(ii)', '(i)(a)'
    #    Guard: must be a single letter OR short roman numeral (≤4 chars) — NOT a full word
    m_sub = re.match(r"^[\(\[]?(?P<sublabel>[a-zA-Z]|[ivxlcdmIVXLCDM]+)[\)\]\.]?$", clean)
    if m_sub:
        sublabel = m_sub.group("sublabel")
        if not sublabel.isdigit() and len(sublabel) <= 4:
            # Avoid treating regular question numbers like 'a' as sub-labels for
            # top-level questions like 'A1', 'B2' by checking context — here we
            # simply normalize and let the reconciler handle placement.
            return None, normalize_sublabel(sublabel)

    return None, None


def deduplicate_parent_text(parent_text: str, first_sub_text: str, parent_num: str) -> str:
    """Ensure parent question text does not duplicate the first subquestion text.

    If parent text matches or contains only the first subquestion, returns a clean
    parent title ('Question {parent_num}'). If a distinct preamble exists, keeps only
    the preamble.
    """
    p_clean = parent_text.strip()
    s_clean = first_sub_text.strip()

    fallback = f"Question {parent_num}" if not parent_num.lower().startswith("question") else parent_num

    if not p_clean or p_clean == s_clean:
        return fallback

    if p_clean.endswith(s_clean):
        prefix = p_clean[:-len(s_clean)].strip()
        cleaned_prefix = re.sub(r"[\(\[]?[a-zA-Z0-9]+[\)\]]?[\:\.\-]?\s*$", "", prefix).strip()
        if cleaned_prefix:
            return cleaned_prefix
        return fallback

    sub_sample = s_clean[:min(35, len(s_clean))]
    if len(sub_sample) >= 10 and sub_sample in p_clean:
        idx = p_clean.find(sub_sample)
        prefix = p_clean[:idx].strip()
        cleaned_prefix = re.sub(r"[\(\[]?[a-zA-Z0-9]+[\)\]]?[\:\.\-]?\s*$", "", prefix).strip()
        if cleaned_prefix:
            return cleaned_prefix
        return fallback

    return p_clean


def _is_sequential_sublabel(existing_labels: List[str], new_label: str) -> bool:
    """Return True if new_label is a plausible sequential continuation of existing sublabels.

    E.g. if existing_labels end with '(a)', then '(b)' is sequential.
    If ending with '(ii)', then '(ii)' continuation or '(iii)' would be sequential.
    Also accepts composite labels like '(i)(a)', '(i)(b)' as continuations of '(i)(a)'.
    Detects roman continuations (e.g. '(ii)') even when preceding labels are composite (e.g. '(i)(a)').
    """
    if not existing_labels:
        # First sublabel: (a), (i), or composite are always plausible starts
        clean = new_label.strip("()").lower()
        return clean in ("a", "i", "1") or re.match(r"^(\([a-zA-Z0-9]+\)){2,}$", new_label) is not None

    _roman = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6, "vii": 7, "viii": 8, "ix": 9, "x": 10}
    new_clean = new_label.strip("()").lower()

    # 1. Composite labels: check prefix matches
    if re.match(r"^(\([a-zA-Z0-9]+\)){2,}$", new_label):
        return any(
            new_label.startswith(e.rstrip(")").rsplit("(", 1)[0]) or e in new_label
            for e in existing_labels
        )

    # 2. Roman numeral check: (i) → (ii), (ii) → (iii), etc.
    # Also inspects composite existing labels like (i)(a) or (b)(i)(a) for containing roman numerals
    if new_clean in _roman:
        new_roman_val = _roman[new_clean]
        for e in reversed(existing_labels):
            e_clean = e.strip("()").lower()
            if e_clean in _roman:
                return new_roman_val == _roman[e_clean] + 1 or new_roman_val == _roman[e_clean]
            # Search for roman numerals in composite label parts (e.g. "(b)(i)(a)" -> "i")
            m_roman = re.findall(r"\b(i|ii|iii|iv|v|vi|vii|viii|ix|x)\b", e.lower())
            if m_roman:
                prev_roman_val = _roman.get(m_roman[-1])
                if prev_roman_val is not None:
                    return new_roman_val == prev_roman_val + 1 or new_roman_val == prev_roman_val

    # 3. Letter sequence: (a) → (b), (b) → (c), etc.
    last = existing_labels[-1]
    last_clean = last.strip("()").lower()

    if len(last_clean) == 1 and len(new_clean) == 1 and last_clean.isalpha() and new_clean.isalpha():
        return ord(new_clean) == ord(last_clean) + 1 or new_clean == last_clean

    # Also check if last was a composite starting with a letter, e.g. "(a)(i)" -> new "(b)"
    m_let = re.match(r"^\(?([a-z])\)?", last.lower())
    if m_let and len(new_clean) == 1 and new_clean.isalpha():
        prev_let = m_let.group(1)
        return ord(new_clean) == ord(prev_let) + 1 or new_clean == prev_let

    return False


def _attach_as_subquestion(
    parent: "QuestionItem",
    sublabel: str,
    q: "QuestionItem",
    promote_parent_text_if_empty: bool = True,
) -> None:
    """Attach question q as a SubQuestion under parent with the given sublabel.

    Handles:
    - Promoting parent question_text to a placeholder if it was empty/duplicated.
    - Syncing page_numbers.
    - Deduplication by label.
    """
    new_sq = SubQuestion(
        subquestion_label=sublabel,
        text=q.question_text,
        answer=q.answer,
        has_explicit_answer=q.has_explicit_answer,
        confidence_score=q.confidence_score,
        page_number=q.page_number,
        bounding_box=q.bounding_box,
        source_block_ids=list(q.source_block_ids),
        needs_human_review=q.needs_human_review,
        review_reasons=q.review_reasons,
    )

    if promote_parent_text_if_empty and not parent.subquestions:
        # First subquestion being added: preserve any preamble text in parent
        parent.subquestions.append(
            SubQuestion(
                subquestion_label="(a)",
                text=parent.question_text,
                answer=parent.answer,
                has_explicit_answer=parent.has_explicit_answer,
                confidence_score=parent.confidence_score,
                page_number=parent.page_number,
                bounding_box=parent.bounding_box,
                source_block_ids=list(parent.source_block_ids),
                needs_human_review=parent.needs_human_review,
                review_reasons=parent.review_reasons,
            )
        )
        parent.question_text = (
            f"Question {parent.question_number}"
            if not parent.question_number.lower().startswith("question")
            else parent.question_number
        )

    # Sync page numbers
    parent_pages = set(parent.page_numbers)
    if parent.page_number:
        parent_pages.add(parent.page_number)
    if q.page_number:
        parent_pages.add(q.page_number)
    parent_pages.update(q.page_numbers)
    if parent_pages:
        sorted_pages = sorted(list(parent_pages))
        object.__setattr__(parent, "page_numbers", sorted_pages)
        object.__setattr__(parent, "page_number", sorted_pages[0])

    # Sync source block IDs on parent
    merged_blocks = list(dict.fromkeys(parent.source_block_ids + q.source_block_ids))
    object.__setattr__(parent, "source_block_ids", merged_blocks)

    # Deduplicate by label — prefer version with an answer
    existing_idx = next(
        (i for i, sq in enumerate(parent.subquestions) if sq.subquestion_label.lower() == sublabel.lower()),
        None,
    )
    if existing_idx is None:
        parent.subquestions.append(new_sq)
    else:
        if parent.subquestions[existing_idx].answer is None and new_sq.answer is not None:
            merged_sq_blocks = list(
                dict.fromkeys(parent.subquestions[existing_idx].source_block_ids + new_sq.source_block_ids)
            )
            object.__setattr__(new_sq, "source_block_ids", merged_sq_blocks)
            parent.subquestions[existing_idx] = new_sq


# ---------------------------------------------------------------------------
# Solution / placeholder detection helpers for reconcile_question_hierarchy
# ---------------------------------------------------------------------------

_SOLUTION_PREFIX_PATTERNS = re.compile(
    r"^(sol\b|sol\.|solution\b|solution:|working:|let\s+[a-z]_[a-z0-9]|p\([a-z]_[0-9])",
    re.IGNORECASE,
)
_ASSIGNMENT_PATTERN = re.compile(
    r"p\s*\(\s*[a-z]_[0-9]\s*\)\s*=",
    re.IGNORECASE,
)


def _is_solution_or_working_text(text: str) -> bool:
    """Return True if text looks like solution working rather than a question continuation.

    Heuristics:
    - Starts with 'Sol.', 'Solution', 'Working:', 'Let R_i', etc.
    - Contains assignment patterns like P(R_1) = ...
    """
    stripped = text.strip()
    if _SOLUTION_PREFIX_PATTERNS.match(stripped):
        return True
    if _ASSIGNMENT_PATTERN.search(stripped):
        return True
    return False


def _is_placeholder_question_text(text: str) -> bool:
    """Return True if text is a generic placeholder like 'Question 1' or 'Q1'."""
    stripped = text.strip()
    return bool(re.match(r"^(question\s*\d+|q\d+)$", stripped, re.IGNORECASE))


def reconcile_question_hierarchy(raw_questions: List[QuestionItem]) -> List[QuestionItem]:
    """Reconciles question hierarchy by grouping subparts under parent questions.

    1. Detects compound question numbers (e.g. '2(b)', '2b') or standalone sublabels (e.g. '(b)').
    2. Groups them under their matching parent question.
    3. Preserves all answers at the subquestion level.
    4. Removes duplicated subquestion text from parent question_text.
    5. Flags genuinely ambiguous hierarchy with needs_human_review=True.
    6. Handles composite nested labels like '(i)(a)', '(i)(b)' for sub-subquestions.
    7. Guards against attaching standalone labels to unrelated parents using sequential heuristic.
    """
    if not raw_questions:
        return []

    reconciled: List[QuestionItem] = []

    for q in raw_questions:
        parent_candidate, sublabel_candidate = extract_parent_and_sublabel(q.question_number)

        # Case 1: Compound label like '2(b)', 'Q2(b)', '5(b)(i)(a)'
        if parent_candidate and sublabel_candidate:
            cand_key = normalize_parent_key(parent_candidate)
            matching_parent = next(
                (p for p in reversed(reconciled) if normalize_parent_key(p.question_number) == cand_key),
                None,
            )

            if matching_parent:
                _attach_as_subquestion(matching_parent, sublabel_candidate, q)
                continue
            else:
                # Parent not yet seen; create it if this is a first subquestion (a)/(i)
                if sublabel_candidate.lower() in ("(a)", "(i)", "(1)"):
                    new_sq = SubQuestion(
                        subquestion_label=sublabel_candidate,
                        text=q.question_text,
                        answer=q.answer,
                        has_explicit_answer=q.has_explicit_answer,
                        confidence_score=q.confidence_score,
                        needs_human_review=q.needs_human_review,
                        review_reasons=q.review_reasons,
                    )
                    parent_q = QuestionItem(
                        question_number=parent_candidate,
                        question_text=(
                            f"Question {parent_candidate}"
                            if not parent_candidate.lower().startswith("question")
                            else parent_candidate
                        ),
                        subquestions=[new_sq],
                        answer=None,
                        has_explicit_answer=False,
                        confidence_score=q.confidence_score,
                        needs_human_review=q.needs_human_review,
                        review_reasons=q.review_reasons,
                    )
                    reconciled.append(parent_q)
                    continue
                else:
                    # Orphaned compound label — flag for review
                    reasons = list(q.review_reasons)
                    if ReviewReason.AMBIGUOUS_QUESTION_HIERARCHY.value not in reasons:
                        reasons.append(ReviewReason.AMBIGUOUS_QUESTION_HIERARCHY.value)
                    q_flagged = QuestionItem(
                        question_number=q.question_number,
                        question_text=q.question_text,
                        subquestions=q.subquestions,
                        answer=q.answer,
                        confidence_score=min(q.confidence_score, 0.70),
                        needs_human_review=True,
                        review_reasons=reasons,
                    )
                    reconciled.append(q_flagged)
                    continue

        # Case 2: Standalone sublabel like '(b)', '(ii)', composite '(i)(a)'
        elif sublabel_candidate and not parent_candidate:
            if reconciled:
                last_parent = reconciled[-1]
                existing_labels = [sq.subquestion_label for sq in last_parent.subquestions]

                # Guard: only attach if the label is a plausible sequential continuation
                # This prevents e.g. a standalone "(ii)" from being swallowed into an
                # unrelated previous question that happens to end with "(i)".
                is_sequential = _is_sequential_sublabel(existing_labels, sublabel_candidate)

                if is_sequential or not existing_labels:
                    # Maintain composite nesting prefix if preceding sublabels were grouped under (b)
                    effective_sublabel = sublabel_candidate
                    if (
                        sublabel_candidate.lower() in ("(ii)", "(iii)", "(iv)", "(i)", "(i)(a)", "(i)(b)")
                        and any(e.lower().startswith("(b)") for e in existing_labels)
                        and not sublabel_candidate.lower().startswith("(b)")
                    ):
                        effective_sublabel = f"(b){sublabel_candidate}"

                    _attach_as_subquestion(last_parent, effective_sublabel, q)
                    continue
                else:
                    # Label doesn't follow sequentially — flag as ambiguous rather than
                    # silently attaching to the wrong parent.
                    reasons = list(q.review_reasons)
                    if ReviewReason.AMBIGUOUS_QUESTION_HIERARCHY.value not in reasons:
                        reasons.append(ReviewReason.AMBIGUOUS_QUESTION_HIERARCHY.value)
                    q_flagged = QuestionItem(
                        question_number=q.question_number,
                        question_text=q.question_text,
                        subquestions=q.subquestions,
                        answer=q.answer,
                        confidence_score=min(q.confidence_score, 0.70),
                        page_number=q.page_number,
                        page_numbers=q.page_numbers,
                        needs_human_review=True,
                        review_reasons=reasons,
                    )
                    reconciled.append(q_flagged)
                    continue

            # No previous parent exists — flag as ambiguous
            reasons = list(q.review_reasons)
            if ReviewReason.AMBIGUOUS_QUESTION_HIERARCHY.value not in reasons:
                reasons.append(ReviewReason.AMBIGUOUS_QUESTION_HIERARCHY.value)
            q_flagged = QuestionItem(
                question_number=q.question_number,
                question_text=q.question_text,
                subquestions=q.subquestions,
                answer=q.answer,
                confidence_score=min(q.confidence_score, 0.70),
                page_number=q.page_number,
                page_numbers=q.page_numbers,
                needs_human_review=True,
                review_reasons=reasons,
            )
            reconciled.append(q_flagged)
            continue

        # Case 3: Regular top-level question — merge if same number already exists (cross-page)
        cand_key = normalize_parent_key(q.question_number)
        matching_parent = next(
            (p for p in reversed(reconciled) if normalize_parent_key(p.question_number) == cand_key),
            None,
        )
        if matching_parent:
            # Question continues from a previous page
            all_pages = set(matching_parent.page_numbers)
            if matching_parent.page_number:
                all_pages.add(matching_parent.page_number)
            if q.page_number:
                all_pages.add(q.page_number)
            all_pages.update(q.page_numbers)
            if all_pages:
                sorted_pages = sorted(list(all_pages))
                object.__setattr__(matching_parent, "page_numbers", sorted_pages)
                object.__setattr__(matching_parent, "page_number", sorted_pages[0])

            # Merge source block IDs
            merged_ids = list(dict.fromkeys(matching_parent.source_block_ids + q.source_block_ids))
            object.__setattr__(matching_parent, "source_block_ids", merged_ids)

            # Merge subquestions
            for sq in q.subquestions:
                existing_sq = next(
                    (s for s in matching_parent.subquestions if s.subquestion_label.lower() == sq.subquestion_label.lower()),
                    None,
                )
                if existing_sq is None:
                    matching_parent.subquestions.append(sq)
                else:
                    if existing_sq.answer is None and sq.answer is not None:
                        idx = matching_parent.subquestions.index(existing_sq)
                        merged_sq_ids = list(dict.fromkeys(existing_sq.source_block_ids + sq.source_block_ids))
                        object.__setattr__(sq, "source_block_ids", merged_sq_ids)
                        matching_parent.subquestions[idx] = sq

            # Append continuation text if distinct and NOT solution/working text.
            # This prevents solution working like "Sol. Let R_i..." from polluting
            # the parent question_text when a question continues across pages.
            if q.question_text and q.question_text.strip() != matching_parent.question_text.strip():
                continuation_text = q.question_text.strip()
                is_solution_text = _is_solution_or_working_text(continuation_text)
                is_placeholder_parent = _is_placeholder_question_text(matching_parent.question_text)
                should_append = (not is_solution_text) or is_placeholder_parent
                if should_append and continuation_text not in matching_parent.question_text:
                    object.__setattr__(
                        matching_parent,
                        "question_text",
                        f"{matching_parent.question_text} {continuation_text}".strip(),
                    )

            # Merge answer if parent has none
            if matching_parent.answer is None and q.answer is not None:
                object.__setattr__(matching_parent, "answer", q.answer)
                object.__setattr__(matching_parent, "has_explicit_answer", q.has_explicit_answer)

            # Merge review flags
            if q.needs_human_review:
                object.__setattr__(matching_parent, "needs_human_review", True)
                merged_reasons = sorted(list(set(matching_parent.review_reasons + q.review_reasons)))
                object.__setattr__(matching_parent, "review_reasons", merged_reasons)
            continue

        reconciled.append(q)

    # Post-processing pass: deduplicate parent texts & clear duplicated parent answers
    for p in reconciled:
        if p.subquestions:
            first_sq = p.subquestions[0]
            cleaned_text = deduplicate_parent_text(p.question_text, first_sq.text, p.question_number)
            if cleaned_text != p.question_text:
                object.__setattr__(p, "question_text", cleaned_text)

            # If parent duplicated first subquestion's answer, clear parent answer to avoid duplication
            if p.answer is not None and first_sq.answer is not None and p.answer.strip() == first_sq.answer.strip():
                object.__setattr__(p, "answer", None)
                object.__setattr__(p, "has_explicit_answer", False)

    return reconciled


def verify_answer_sources(
    questions: List[QuestionItem],
    raw_blocks: List[RawExtractedBlock],
) -> None:
    """Verify that every explicit answer traces back to evidence in raw_blocks via source_block_ids.

    If verification is uncertain (e.g. no valid source_block_ids or referenced blocks contain no
    explicit answer evidence), flags the item with needs_human_review=True and UNVERIFIED_ANSWER_SOURCE
    rather than silently accepting or deleting the answer.
    """
    if not raw_blocks:
        return

    block_map = {b.block_id: b for b in raw_blocks}

    def check_item(item: Union[QuestionItem, SubQuestion]) -> None:
        if not item.has_explicit_answer or not item.answer or not item.answer.strip():
            return

        reasons = list(item.review_reasons)
        needs_review = item.needs_human_review

        # If item has no valid source_block_ids, evidence is missing
        if not item.source_block_ids:
            needs_review = True
            if ReviewReason.UNVERIFIED_ANSWER_SOURCE.value not in reasons:
                reasons.append(ReviewReason.UNVERIFIED_ANSWER_SOURCE.value)
            object.__setattr__(item, "needs_human_review", needs_review)
            object.__setattr__(item, "review_reasons", reasons)
            return

        has_evidence = False
        ans_str = item.answer.strip().lower()
        clean_ans = re.sub(r"[^0-9a-zA-Z]", "", ans_str)

        for b_id in item.source_block_ids:
            blk = block_map.get(b_id)
            if not blk:
                continue

            # 1. Block explicitly states an answer that matches
            if blk.has_explicit_answer and blk.explicit_answer and blk.explicit_answer.strip():
                blk_ans = blk.explicit_answer.strip().lower()
                clean_blk_ans = re.sub(r"[^0-9a-zA-Z]", "", blk_ans)
                if clean_ans in clean_blk_ans or clean_blk_ans in clean_ans:
                    has_evidence = True
                    break

            # 2. Block is a solution/answer block and contains the answer with assignment/equality context
            blk_text = blk.text.lower()
            is_solution = (
                blk.block_type in ("solution", "solution_text", "final_answer", "answer", "continuation")
                or "solution" in blk_text
                or "ans" in blk_text
                or "=" in blk_text
                or "%" in blk_text
            )
            if is_solution:
                if ans_str in blk_text:
                    has_evidence = True
                    break
                clean_blk = re.sub(r"[^0-9a-zA-Z]", "", blk_text)
                if len(clean_ans) >= 2 and clean_ans in clean_blk:
                    has_evidence = True
                    break

        if not has_evidence:
            needs_review = True
            if ReviewReason.UNVERIFIED_ANSWER_SOURCE.value not in reasons:
                reasons.append(ReviewReason.UNVERIFIED_ANSWER_SOURCE.value)
            object.__setattr__(item, "needs_human_review", needs_review)
            object.__setattr__(item, "review_reasons", reasons)

    for q in questions:
        check_item(q)
        for sq in q.subquestions:
            check_item(sq)


class PaperExtractionResult(BaseModel):
    """Schema representing the complete validated output extracted from a mathematics paper."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)

    paper_title: Optional[str] = Field(
        default=None,
        description="Title, header, exam title, or course code if visible on the paper.",
    )
    total_pages_detected: int = Field(
        default=1,
        ge=1,
        description="Total count of document pages processed.",
    )
    total_questions_detected: int = Field(
        default=0,
        ge=0,
        description="Total count of top-level questions detected on the document.",
    )
    questions: List[QuestionItem] = Field(
        default_factory=list,
        description="List of extracted questions with preserved mathematical notation.",
    )
    raw_blocks: List[RawExtractedBlock] = Field(
        default_factory=list,
        description="Complete list of raw, unmerged extracted blocks from all pages.",
    )
    reconciliation_mode: str = Field(
        default="stage1_direct",
        description="Execution mode: 'stage1_direct', 'gemini_cross_page', or 'deterministic_fallback'.",
    )
    requires_human_review: bool = Field(
        default=False,
        description="Document-level flag indicating if any question/subquestion needs human review.",
    )
    review_reasons: List[str] = Field(
        default_factory=list,
        description="Aggregate review reasons across all questions or document-level ambiguities.",
    )
    notes: Optional[str] = Field(
        default=None,
        description="Optional model observations regarding handwriting legibility, image artifacts, or layout.",
    )

    @model_validator(mode="after")
    def sync_counts_and_review_flags(self) -> "PaperExtractionResult":
        """Synchronize question counts, reconcile hierarchy, and aggregate review flags."""
        # 1. Reconcile question hierarchy (e.g. merge 2(b) or (b) into parent question 2).
        # Skip re-reconciliation when Stage 2 LLM has already built the hierarchy
        # (reconciliation_mode == "gemini_cross_page"), to avoid destroying the LLM output.
        if self.reconciliation_mode != "gemini_cross_page":
            reconciled = reconcile_question_hierarchy(self.questions)
            object.__setattr__(self, "questions", reconciled)
        object.__setattr__(self, "total_questions_detected", len(self.questions))

        # 2. Reject dangling / nonexistent source_block_ids
        if self.raw_blocks:
            valid_bids = {b.block_id for b in self.raw_blocks}
            for q in self.questions:
                valid_q_bids = [bid for bid in q.source_block_ids if bid in valid_bids]
                object.__setattr__(q, "source_block_ids", valid_q_bids)
                for sq in q.subquestions:
                    valid_sq_bids = [bid for bid in sq.source_block_ids if bid in valid_bids]
                    object.__setattr__(sq, "source_block_ids", valid_sq_bids)

            # 3. Verify answer sources against valid raw blocks
            verify_answer_sources(self.questions, self.raw_blocks)

        # If any question needs review, document-level flag is True
        any_question_needs_review = any(q.needs_human_review for q in self.questions)
        requires_review = self.requires_human_review or any_question_needs_review

        # Aggregate unique review reasons
        aggregated_reasons = set(self.review_reasons)
        for q in self.questions:
            aggregated_reasons.update(q.review_reasons)
            for sq in q.subquestions:
                aggregated_reasons.update(sq.review_reasons)

        # Synchronize total_pages_detected from question page numbers
        max_page = max(
            [self.total_pages_detected]
            + [p for q in self.questions for p in q.page_numbers]
            + [q.page_number for q in self.questions if q.page_number is not None]
        )
        object.__setattr__(self, "total_pages_detected", max_page)

        object.__setattr__(self, "requires_human_review", requires_review)
        object.__setattr__(self, "review_reasons", sorted(list(aggregated_reasons)))
        return self


def build_gemini_compatible_schema(
    schema_or_model: Union[type[BaseModel], Dict[str, Any]],
) -> Dict[str, Any]:
    """Transform a Pydantic model or JSON schema into a Gemini-compatible schema dictionary.

    Gemini's structured output API rejects `additionalProperties` (which Pydantic generates
    when `extra="forbid"` is configured) and expects inlined definitions instead of `$defs`/`$ref`.

    This function:
    1. Dereferences all `$ref` pointers using `$defs` definitions.
    2. Removes `$defs` once dereferenced.
    3. Recursively removes all `additionalProperties` and `additional_properties` keywords.
    4. Simplifies nullable `anyOf` constructs (e.g. `[{"type": T}, {"type": "null"}]`) into
       `type=T` and `nullable=True`.
    5. Preserves required fields, property definitions, nested array schemas, descriptions,
       and validation constraints.
    """
    if isinstance(schema_or_model, type) and issubclass(schema_or_model, BaseModel):
        raw_schema = schema_or_model.model_json_schema()
    elif isinstance(schema_or_model, dict):
        raw_schema = schema_or_model
    else:
        raise TypeError(f"Expected BaseModel subclass or dict, got {type(schema_or_model)}")

    working_schema = copy.deepcopy(raw_schema)
    defs = working_schema.pop("$defs", {})

    def _resolve_refs(node: Any, visited: Optional[Set[str]] = None) -> Any:
        if visited is None:
            visited = set()

        if isinstance(node, dict):
            if "$ref" in node:
                ref_path = str(node["$ref"])
                ref_name = ref_path.split("/")[-1]
                if ref_name in defs and ref_path not in visited:
                    resolved = copy.deepcopy(defs[ref_name])
                    resolved = _resolve_refs(resolved, visited | {ref_path})
                    # Merge any sibling keys from the ref node (e.g., description or title)
                    extra_keys = {
                        k: _resolve_refs(v, visited)
                        for k, v in node.items()
                        if k != "$ref"
                    }
                    if isinstance(resolved, dict):
                        resolved.update(extra_keys)
                    return resolved
                return node
            return {k: _resolve_refs(v, visited) for k, v in node.items()}
        elif isinstance(node, list):
            return [_resolve_refs(item, visited) for item in node]
        return node

    def _clean_node(node: Any) -> Any:
        if isinstance(node, dict):
            cleaned: Dict[str, Any] = {}

            # Handle anyOf with null (e.g., Optional[str]) -> type + nullable: True
            if "anyOf" in node and isinstance(node["anyOf"], list):
                any_of = node["anyOf"]
                nulls = [x for x in any_of if isinstance(x, dict) and x.get("type") == "null"]
                non_nulls = [x for x in any_of if not (isinstance(x, dict) and x.get("type") == "null")]
                if len(nulls) == 1 and len(non_nulls) == 1 and isinstance(non_nulls[0], dict):
                    target = non_nulls[0]
                    for k, v in target.items():
                        if k in ("additionalProperties", "additional_properties", "$defs"):
                            continue
                        cleaned[k] = _clean_node(v)
                    cleaned["nullable"] = True
                    for k, v in node.items():
                        if k not in ("anyOf", "additionalProperties", "additional_properties", "$defs"):
                            cleaned[k] = _clean_node(v)
                    return cleaned

            for k, v in node.items():
                if k in ("additionalProperties", "additional_properties", "$defs"):
                    continue
                cleaned[k] = _clean_node(v)
            return cleaned
        elif isinstance(node, list):
            return [_clean_node(item) for item in node]
        return node

    dereferenced = _resolve_refs(working_schema)
    return _clean_node(dereferenced)


def get_gemini_extraction_schema() -> Dict[str, Any]:
    """Return a fresh Gemini-compatible JSON schema for PaperExtractionResult."""
    return build_gemini_compatible_schema(PaperExtractionResult)

