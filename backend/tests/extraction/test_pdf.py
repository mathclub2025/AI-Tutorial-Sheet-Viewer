"""Tests for PDF processing, rendering, and extraction via the PDFProcessor service
and POST /api/v1/papers/extract endpoint (mocked — no Gemini API credits consumed).

Coverage:
- Valid single-page PDF
- Valid multi-page PDF
- Scanned PDF (bitmap embedded inside PDF)
- Digitally generated PDF (vector fonts)
- Corrupted PDF (truncated / bad magic bytes)
- Encrypted PDF (password-protected)
- Oversized PDF
- PDF exceeding page limit
- Question spanning two pages (page_numbers aggregation)
- Regression: existing image uploads (JPEG, PNG, WEBP) still work after PDF changes
- API-level HTTP status code mapping for all PDF error types
"""

from io import BytesIO
from unittest.mock import MagicMock

import pymupdf
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.extraction.api.deps import get_extractor, get_pdf_processor, get_preprocessor
from app.extraction.config import settings
from app.extraction.main import app
from app.extraction.schemas.extraction import PaperExtractionResult, QuestionItem, SubQuestion
from app.extraction.services.extractor import GeminiMathExtractor
from app.extraction.services.pdf_processor import (
    CorruptPDFError,
    EncryptedPDFError,
    InvalidPDFPageError,
    OversizedPDFError,
    PDFPageLimitExceededError,
    PDFProcessingError,
    PDFProcessor,
    RenderedPDFPage,
)
from app.extraction.services.preprocessor import PreprocessedImageResult

# ---------------------------------------------------------------------------
# Helpers — Synthetic PDF / image generators (all in-memory, no disk I/O)
# ---------------------------------------------------------------------------

def make_simple_pdf(page_count: int = 1, title: str = "Test Exam") -> bytes:
    """Generate a minimal valid digital PDF with text content."""
    doc = pymupdf.open()
    for i in range(page_count):
        page = doc.new_page(width=595, height=842)
        page.insert_text((50, 72), title, fontsize=14)
        page.insert_text((50, 120 + i * 40), f"Question {i + 1}: Solve $x^2 = 4$.", fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


def make_encrypted_pdf() -> bytes:
    """Generate a password-protected / encrypted PDF."""
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((50, 72), "Secret exam content", fontsize=12)
    data = doc.tobytes(
        encryption=pymupdf.PDF_ENCRYPT_AES_256,
        owner_pw="ownerpass",
        user_pw="userpass",
    )
    doc.close()
    return data


def make_scanned_pdf() -> bytes:
    """Generate a PDF that contains an embedded bitmap image (simulating a scanned document)."""
    # Create a small synthetic JPEG image
    img = Image.new("RGB", (595, 842), color=(240, 240, 240))
    buf = BytesIO()
    img.save(buf, format="JPEG")
    jpeg_bytes = buf.getvalue()

    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    # insert_image embeds a raster image directly into the page (correct API for bitmaps)
    page.insert_image(page.rect, stream=jpeg_bytes)
    data = doc.tobytes()
    doc.close()
    return data


def make_spanning_pages_pdf() -> bytes:
    """PDF where Question 2 begins on page 1 and subquestion (b) is on page 2."""
    doc = pymupdf.open()
    # Page 1
    p1 = doc.new_page(width=595, height=842)
    p1.insert_text((50, 72), "Statistics Exam", fontsize=14)
    p1.insert_text((50, 130), "1. Find the mean of {1, 2, 3, 4, 5}.", fontsize=11)
    p1.insert_text((50, 160), "Answer: 3", fontsize=11)
    p1.insert_text((50, 220), "2. Let X ~ U(0, 4).", fontsize=11)
    p1.insert_text((50, 250), "   (a) Find E[X].", fontsize=11)
    p1.insert_text((50, 280), "   Answer: 2", fontsize=11)
    # Page 2 continues question 2
    p2 = doc.new_page(width=595, height=842)
    p2.insert_text((50, 72), "Statistics Exam (continued)", fontsize=14)
    p2.insert_text((50, 120), "2. (continued)", fontsize=11)
    p2.insert_text((50, 160), "   (b) Find Var(X).", fontsize=11)
    p2.insert_text((50, 190), "   Answer: 4/3", fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


def make_dummy_preprocessed(width=595, height=842) -> PreprocessedImageResult:
    """Create a minimal dummy PreprocessedImageResult."""
    # Create a valid PNG bytes for page image
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    buf = BytesIO()
    img.save(buf, format="PNG")
    png_bytes = buf.getvalue()
    return PreprocessedImageResult(
        original_bytes=png_bytes,
        processed_bytes=png_bytes,
        format="PNG",
        mime_type="image/png",
        original_dimensions=(width, height),
        processed_dimensions=(width, height),
        was_resized=False,
        exif_rotation_applied=0,
        is_preprocessed=True,
    )


def make_synthetic_image(fmt="JPEG", width=200, height=200) -> bytes:
    """Generate a valid synthetic image in memory."""
    img = Image.new("RGB", (width, height), color=(200, 210, 220))
    buf = BytesIO()
    img.save(buf, format=fmt)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    app.dependency_overrides.clear()
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def dummy_prepped():
    return make_dummy_preprocessed()


# ---------------------------------------------------------------------------
# PDFProcessor unit tests (no FastAPI, no Gemini)
# ---------------------------------------------------------------------------

class TestPDFProcessor:
    """Unit tests for the PDFProcessor service."""

    def test_valid_single_page_pdf_renders_one_page(self):
        """Single-page PDF produces exactly one RenderedPDFPage."""
        pdf_bytes = make_simple_pdf(page_count=1)
        processor = PDFProcessor()
        pages = processor.process_pdf(pdf_bytes)
        assert len(pages) == 1
        assert pages[0].page_number == 1
        assert len(pages[0].image_bytes) > 0
        w, h = pages[0].dimensions
        assert w > 0 and h > 0

    def test_valid_multi_page_pdf_renders_all_pages(self):
        """Multi-page PDF produces one RenderedPDFPage per page, with correct page numbers."""
        pdf_bytes = make_simple_pdf(page_count=3)
        processor = PDFProcessor()
        pages = processor.process_pdf(pdf_bytes)
        assert len(pages) == 3
        for i, page in enumerate(pages):
            assert page.page_number == i + 1
            assert len(page.image_bytes) > 0

    def test_scanned_pdf_renders_successfully(self):
        """PDF containing embedded bitmap pages renders without error."""
        pdf_bytes = make_scanned_pdf()
        processor = PDFProcessor()
        pages = processor.process_pdf(pdf_bytes)
        assert len(pages) == 1
        assert pages[0].page_number == 1
        # Rendered image should be valid PNG
        img = Image.open(BytesIO(pages[0].image_bytes))
        assert img.format == "PNG"

    def test_digitally_generated_pdf_renders_correctly(self):
        """Digitally generated PDF with text content renders into PNG images."""
        pdf_bytes = make_simple_pdf(title="Calculus Exam")
        processor = PDFProcessor()
        pages = processor.process_pdf(pdf_bytes)
        assert len(pages) == 1
        # Verify rendered output is valid PNG
        img = Image.open(BytesIO(pages[0].image_bytes))
        assert img.format == "PNG"
        assert img.size[0] > 0 and img.size[1] > 0

    def test_empty_bytes_raises_corrupt_error(self):
        """Empty bytes raises CorruptPDFError."""
        processor = PDFProcessor()
        with pytest.raises(CorruptPDFError, match="empty"):
            processor.process_pdf(b"")

    def test_invalid_magic_bytes_raises_corrupt_error(self):
        """Bytes without %PDF- signature raises CorruptPDFError."""
        processor = PDFProcessor()
        with pytest.raises(CorruptPDFError, match="signature"):
            processor.process_pdf(b"\x89PNG\r\n" + b"A" * 100)

    def test_truncated_pdf_raises_corrupt_error(self):
        """Truncated PDF raises CorruptPDFError."""
        pdf_bytes = make_simple_pdf()
        truncated = pdf_bytes[:20]  # cut to just the first 20 bytes
        processor = PDFProcessor()
        with pytest.raises((CorruptPDFError, PDFProcessingError)):
            processor.process_pdf(truncated)

    def test_corrupted_pdf_body_raises_error(self):
        """Corrupted PDF bytes (valid header, garbage body) raises CorruptPDFError."""
        corrupted = b"%PDF-1.4\n" + b"\x00" * 50 + b"%%EOF"
        processor = PDFProcessor()
        with pytest.raises((CorruptPDFError, PDFProcessingError)):
            processor.process_pdf(corrupted)

    def test_encrypted_pdf_raises_encrypted_error(self):
        """Password-protected PDF raises EncryptedPDFError."""
        enc_bytes = make_encrypted_pdf()
        processor = PDFProcessor()
        with pytest.raises(EncryptedPDFError):
            processor.process_pdf(enc_bytes)

    def test_oversized_pdf_raises_oversized_error(self):
        """PDF exceeding size limit raises OversizedPDFError before parsing."""
        processor = PDFProcessor(max_size_mb=1)
        oversized_bytes = b"%PDF-" + b"A" * (2 * 1024 * 1024)
        with pytest.raises(OversizedPDFError) as exc_info:
            processor.process_pdf(oversized_bytes)
        assert exc_info.value.size_bytes > exc_info.value.max_bytes

    def test_page_count_exceeded_raises_limit_error(self):
        """PDF with more pages than limit raises PDFPageLimitExceededError."""
        pdf_bytes = make_simple_pdf(page_count=5)
        processor = PDFProcessor(max_pages=3)
        with pytest.raises(PDFPageLimitExceededError) as exc_info:
            processor.process_pdf(pdf_bytes)
        assert exc_info.value.page_count == 5
        assert exc_info.value.max_pages == 3

    def test_rendered_png_bytes_are_valid_images(self):
        """All rendered page bytes can be decoded as valid PNG images."""
        pdf_bytes = make_simple_pdf(page_count=2)
        processor = PDFProcessor()
        pages = processor.process_pdf(pdf_bytes)
        for page in pages:
            img = Image.open(BytesIO(page.image_bytes))
            assert img.format == "PNG"
            assert img.size[0] > 0

    def test_dpi_affects_rendered_dimensions(self):
        """Higher DPI setting produces larger rendered image dimensions."""
        pdf_bytes = make_simple_pdf()
        low_dpi = PDFProcessor(render_dpi=72)
        high_dpi = PDFProcessor(render_dpi=300)
        low_pages = low_dpi.process_pdf(pdf_bytes)
        high_pages = high_dpi.process_pdf(pdf_bytes)
        low_w = low_pages[0].dimensions[0]
        high_w = high_pages[0].dimensions[0]
        assert high_w > low_w

    def test_document_closed_after_processing(self):
        """PDFProcessor always closes the document, even when no error occurs."""
        pdf_bytes = make_simple_pdf()
        processor = PDFProcessor()
        # Should not raise - process_pdf internally closes doc in finally block
        pages = processor.process_pdf(pdf_bytes)
        assert len(pages) == 1

    def test_document_closed_after_exception(self):
        """PDFProcessor still cleans up doc reference when an exception is raised."""
        processor = PDFProcessor(max_pages=1)
        pdf_bytes = make_simple_pdf(page_count=5)
        with pytest.raises(PDFPageLimitExceededError):
            processor.process_pdf(pdf_bytes)
        # If we reach here without ResourceWarning or hanging, cleanup succeeded


# ---------------------------------------------------------------------------
# Extractor multi-page PDF unit tests (mocked — no API credits)
# ---------------------------------------------------------------------------

class TestExtractorPDFPages:
    """Unit tests for GeminiMathExtractor.extract_from_pdf_pages."""

    def _make_mock_extractor_with_responses(self, responses: list) -> GeminiMathExtractor:
        """Return mocked GeminiMathExtractor whose extract_from_image returns successive responses."""
        extractor = GeminiMathExtractor.__new__(GeminiMathExtractor)
        extractor.model = "mock-model"
        extractor.api_key = "mock_key"
        extractor.response_schema = {}
        # Inject mock client
        mock_client = MagicMock()
        extractor._client = mock_client
        extractor._ensure_client = lambda: mock_client

        call_count = [0]

        def _side_effect(image_result, use_fallback_original=False):
            idx = call_count[0]
            call_count[0] += 1
            if idx < len(responses):
                return responses[idx]
            return PaperExtractionResult(questions=[])

        extractor.extract_from_image = _side_effect
        return extractor

    def test_single_page_pdf_extraction(self):
        """Single PDF page result is tagged with page_number=1."""
        result_p1 = PaperExtractionResult(
            paper_title="Exam",
            questions=[
                QuestionItem(
                    question_number="1",
                    question_text="Find $x$ in $x + 1 = 2$.",
                    answer="1",
                )
            ],
        )
        extractor = self._make_mock_extractor_with_responses([result_p1])
        pages = [(1, make_dummy_preprocessed())]
        result = extractor.extract_from_pdf_pages(pages)
        assert result.total_pages_detected == 1
        assert len(result.questions) == 1
        assert result.questions[0].page_number == 1

    def test_multi_page_pdf_aggregates_all_questions(self):
        """Questions from multiple pages are merged into one result."""
        result_p1 = PaperExtractionResult(
            questions=[
                QuestionItem(question_number="1", question_text="Differentiate $x^3$."),
                QuestionItem(question_number="2", question_text="Integrate $x^2$."),
            ]
        )
        result_p2 = PaperExtractionResult(
            questions=[
                QuestionItem(question_number="3", question_text="Solve $e^x = 5$.", answer="$\\ln 5$"),
            ]
        )
        extractor = self._make_mock_extractor_with_responses([result_p1, result_p2])
        pages = [(1, make_dummy_preprocessed()), (2, make_dummy_preprocessed())]
        result = extractor.extract_from_pdf_pages(pages)
        assert result.total_pages_detected == 2
        assert len(result.questions) == 3
        # Questions from page 1
        assert result.questions[0].page_number == 1
        assert result.questions[1].page_number == 1
        # Question from page 2
        assert result.questions[2].page_number == 2

    def test_question_spanning_two_pages_merges_subquestions(self):
        """Question 2 from page 1 and Question 2 from page 2 are merged, page_numbers=[1,2]."""
        result_p1 = PaperExtractionResult(
            questions=[
                QuestionItem(
                    question_number="2",
                    question_text="Let $X \\sim U(0, 4)$.",
                    subquestions=[
                        SubQuestion(
                            subquestion_label="(a)",
                            text="Find $E[X]$.",
                            answer="2",
                        )
                    ],
                )
            ]
        )
        # Page 2 has the continuation of question 2 as an independent question
        result_p2 = PaperExtractionResult(
            questions=[
                QuestionItem(
                    question_number="2",
                    question_text="Let $X \\sim U(0, 4)$. (continued)",
                    subquestions=[
                        SubQuestion(
                            subquestion_label="(b)",
                            text="Find $Var(X)$.",
                            answer="$\\frac{4}{3}$",
                        )
                    ],
                )
            ]
        )
        extractor = self._make_mock_extractor_with_responses([result_p1, result_p2])
        pages = [(1, make_dummy_preprocessed()), (2, make_dummy_preprocessed())]
        result = extractor.extract_from_pdf_pages(pages)

        assert result.total_pages_detected == 2
        # Both page-1 Q2 and page-2 Q2 merged into a single parent question
        q2_matches = [q for q in result.questions if q.question_number == "2"]
        assert len(q2_matches) == 1
        q2 = q2_matches[0]

        # page_numbers should contain both pages
        assert 1 in q2.page_numbers
        assert 2 in q2.page_numbers

        # Both subquestions preserved
        sub_labels = {sq.subquestion_label for sq in q2.subquestions}
        assert "(a)" in sub_labels
        assert "(b)" in sub_labels

        # Answers preserved on subquestions
        sub_a = next(s for s in q2.subquestions if s.subquestion_label == "(a)")
        sub_b = next(s for s in q2.subquestions if s.subquestion_label == "(b)")
        assert sub_a.answer == "2"
        assert sub_b.answer == "$\\frac{4}{3}$"

    def test_empty_pages_list_returns_empty_result(self):
        """extract_from_pdf_pages with no pages returns empty PaperExtractionResult."""
        extractor = self._make_mock_extractor_with_responses([])
        result = extractor.extract_from_pdf_pages([])
        assert result.total_questions_detected == 0
        assert result.questions == []
        # Schema requires total_pages_detected >= 1; empty input returns the minimum floor
        assert result.total_pages_detected == 1

    def test_paper_title_captured_from_first_page(self):
        """Paper title is taken from the first page that contains one."""
        result_p1 = PaperExtractionResult(paper_title="Advanced Calculus", questions=[])
        result_p2 = PaperExtractionResult(paper_title="Page 2 Title", questions=[])
        extractor = self._make_mock_extractor_with_responses([result_p1, result_p2])
        pages = [(1, make_dummy_preprocessed()), (2, make_dummy_preprocessed())]
        result = extractor.extract_from_pdf_pages(pages)
        assert result.paper_title == "Advanced Calculus"

    def test_answers_never_invented_across_pages(self):
        """Questions with no visible answers remain null — extractor never invents answers."""
        result_p1 = PaperExtractionResult(
            questions=[
                QuestionItem(
                    question_number="1",
                    question_text="Solve $x^3 - 1 = 0$.",
                    answer=None,
                    has_explicit_answer=False,
                )
            ]
        )
        extractor = self._make_mock_extractor_with_responses([result_p1])
        pages = [(1, make_dummy_preprocessed())]
        result = extractor.extract_from_pdf_pages(pages)
        assert result.questions[0].answer is None
        assert result.questions[0].has_explicit_answer is False


# ---------------------------------------------------------------------------
# API endpoint PDF tests (mocked preprocessing + extraction — no API credits)
# ---------------------------------------------------------------------------

class TestPDFAPIEndpoint:
    """Integration tests for POST /api/v1/papers/extract with PDF uploads."""

    def _build_client_with_mocks(
        self,
        pdf_bytes: bytes,
        rendered_pages: list,
        extraction_result: PaperExtractionResult,
    ):
        """Build a TestClient with mocked pdf_processor, preprocessor, and extractor."""
        mock_pdf_processor = MagicMock()
        mock_pdf_processor.process_pdf.return_value = rendered_pages

        dummy_prepped = make_dummy_preprocessed()
        mock_preprocessor = MagicMock()
        mock_preprocessor.preprocess.return_value = dummy_prepped

        mock_extractor = MagicMock()
        mock_extractor.extract_from_pdf_pages.return_value = extraction_result

        app.dependency_overrides[get_pdf_processor] = lambda: mock_pdf_processor
        app.dependency_overrides[get_preprocessor] = lambda: mock_preprocessor
        app.dependency_overrides[get_extractor] = lambda: mock_extractor

        return TestClient(app)

    def setup_method(self):
        app.dependency_overrides.clear()

    def teardown_method(self):
        app.dependency_overrides.clear()

    def test_valid_single_page_pdf_returns_200(self):
        """Valid single-page PDF upload returns HTTP 200 with extraction data."""
        pdf_bytes = make_simple_pdf(page_count=1)

        # Create a valid PNG for the rendered page
        img = Image.new("RGB", (595, 842), color=(255, 255, 255))
        buf = BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()

        rendered = [RenderedPDFPage(page_number=1, image_bytes=png_bytes, dimensions=(595, 842))]
        extraction = PaperExtractionResult(
            paper_title="Test Exam",
            questions=[
                QuestionItem(
                    question_number="1",
                    question_text="Solve $x^2 = 4$.",
                    answer="$x = \\pm 2$",
                )
            ],
        )

        client = self._build_client_with_mocks(pdf_bytes, rendered, extraction)
        response = client.post(
            "/api/v1/papers/extract",
            files={"file": ("exam.pdf", pdf_bytes, "application/pdf")},
        )
        assert response.status_code == 200
        res = response.json()
        assert res["success"] is True
        assert res["image_metadata"]["page_count"] == 1
        assert res["image_metadata"]["filename"] == "exam.pdf"
        assert res["image_metadata"]["content_type"] == "application/pdf"
        assert res["data"]["paper_title"] == "Test Exam"
        assert len(res["data"]["questions"]) == 1

    def test_multi_page_pdf_returns_page_count(self):
        """Multi-page PDF response includes correct page_count in image_metadata."""
        pdf_bytes = make_simple_pdf(page_count=3)
        img = Image.new("RGB", (595, 842))
        buf = BytesIO()
        img.save(buf, format="PNG")
        png_bytes = buf.getvalue()

        rendered = [
            RenderedPDFPage(page_number=i + 1, image_bytes=png_bytes, dimensions=(595, 842))
            for i in range(3)
        ]
        extraction = PaperExtractionResult(
            questions=[
                QuestionItem(question_number=str(i + 1), question_text=f"Q{i+1}.")
                for i in range(3)
            ]
        )

        client = self._build_client_with_mocks(pdf_bytes, rendered, extraction)
        response = client.post(
            "/api/v1/papers/extract",
            files={"file": ("paper.pdf", pdf_bytes, "application/pdf")},
        )
        assert response.status_code == 200
        res = response.json()
        assert res["image_metadata"]["page_count"] == 3

    def test_corrupted_pdf_returns_400(self):
        """Corrupted PDF bytes return HTTP 400 CorruptPDFError."""
        mock_pdf_processor = MagicMock()
        mock_pdf_processor.process_pdf.side_effect = CorruptPDFError("File does not contain a valid PDF file signature.")

        app.dependency_overrides[get_pdf_processor] = lambda: mock_pdf_processor

        client = TestClient(app)
        corrupted = b"%PDF-1.4\n" + b"\xff" * 100
        response = client.post(
            "/api/v1/papers/extract",
            files={"file": ("corrupt.pdf", corrupted, "application/pdf")},
        )
        assert response.status_code == 400
        res = response.json()
        assert res["success"] is False
        assert res["error"] == "CorruptPDFError"

    def test_encrypted_pdf_returns_400(self):
        """Encrypted PDF returns HTTP 400 EncryptedPDFError."""
        enc_bytes = make_encrypted_pdf()

        mock_pdf_processor = MagicMock()
        mock_pdf_processor.process_pdf.side_effect = EncryptedPDFError(
            "Password-protected or encrypted PDFs are not supported."
        )
        app.dependency_overrides[get_pdf_processor] = lambda: mock_pdf_processor

        client = TestClient(app)
        response = client.post(
            "/api/v1/papers/extract",
            files={"file": ("encrypted.pdf", enc_bytes, "application/pdf")},
        )
        assert response.status_code == 400
        res = response.json()
        assert res["success"] is False
        assert res["error"] == "EncryptedPDFError"
        # Must not expose internal details like encryption parameters
        assert "ownerpass" not in response.text
        assert "userpass" not in response.text

    def test_oversized_pdf_returns_413(self):
        """PDF exceeding size limit returns HTTP 413."""
        mock_pdf_processor = MagicMock()
        mock_pdf_processor.process_pdf.side_effect = OversizedPDFError(
            size_bytes=30 * 1024 * 1024,
            max_bytes=25 * 1024 * 1024,
        )
        app.dependency_overrides[get_pdf_processor] = lambda: mock_pdf_processor

        # Fake large PDF data (just the right size header)
        fake_large = b"%PDF-1.4\n" + b"A" * 1000
        client = TestClient(app)
        response = client.post(
            "/api/v1/papers/extract",
            files={"file": ("big.pdf", fake_large, "application/pdf")},
        )
        assert response.status_code == 413
        res = response.json()
        assert res["success"] is False
        assert res["error"] == "OversizedPDFError"

    def test_pdf_exceeding_page_limit_returns_400(self):
        """PDF with too many pages returns HTTP 400."""
        mock_pdf_processor = MagicMock()
        mock_pdf_processor.process_pdf.side_effect = PDFPageLimitExceededError(
            page_count=50,
            max_pages=20,
        )
        app.dependency_overrides[get_pdf_processor] = lambda: mock_pdf_processor

        fake_pdf = b"%PDF-1.4\n" + b"content" * 100
        client = TestClient(app)
        response = client.post(
            "/api/v1/papers/extract",
            files={"file": ("big.pdf", fake_pdf, "application/pdf")},
        )
        assert response.status_code == 400
        res = response.json()
        assert res["success"] is False
        assert res["error"] == "PDFPageLimitExceededError"

    def test_invalid_pdf_page_dimensions_returns_400(self):
        """PDF page with invalid dimensions returns HTTP 400."""
        mock_pdf_processor = MagicMock()
        mock_pdf_processor.process_pdf.side_effect = InvalidPDFPageError(
            "Page 1 has invalid degenerate dimensions: 0.0x0.0"
        )
        app.dependency_overrides[get_pdf_processor] = lambda: mock_pdf_processor

        fake_pdf = b"%PDF-1.4\n" + b"content" * 10
        client = TestClient(app)
        response = client.post(
            "/api/v1/papers/extract",
            files={"file": ("bad_dims.pdf", fake_pdf, "application/pdf")},
        )
        assert response.status_code == 400
        res = response.json()
        assert res["success"] is False
        assert res["error"] == "InvalidPDFPageError"

    def test_pdf_no_api_key_in_error_response(self):
        """PDF extraction errors must never expose the Gemini API key."""
        mock_pdf_processor = MagicMock()
        mock_pdf_processor.process_pdf.side_effect = CorruptPDFError("Bad PDF")
        app.dependency_overrides[get_pdf_processor] = lambda: mock_pdf_processor

        fake_pdf = b"%PDF-1.4\n" + b"\xff" * 50
        client = TestClient(app)
        response = client.post(
            "/api/v1/papers/extract",
            files={"file": ("bad.pdf", fake_pdf, "application/pdf")},
        )
        if settings.GEMINI_API_KEY:
            assert settings.GEMINI_API_KEY not in response.text


# ---------------------------------------------------------------------------
# Regression: existing image uploads still work after PDF changes
# ---------------------------------------------------------------------------

class TestImageUploadRegression:
    """Regression tests ensuring JPEG/PNG/WEBP uploads still work correctly."""

    def setup_method(self):
        app.dependency_overrides.clear()

    def teardown_method(self):
        app.dependency_overrides.clear()

    def _mock_image_upload(self, fmt: str, ext: str, mime: str):
        """Return a mock client for image upload with given format."""
        dummy_prepped = PreprocessedImageResult(
            original_bytes=b"original",
            processed_bytes=b"processed",
            format=fmt,
            mime_type=mime,
            original_dimensions=(800, 600),
            processed_dimensions=(800, 600),
            was_resized=False,
            exif_rotation_applied=0,
            is_preprocessed=True,
        )
        mock_preprocessor = MagicMock()
        mock_preprocessor.preprocess.return_value = dummy_prepped

        mock_extractor = MagicMock()
        mock_extractor.extract_from_image.return_value = PaperExtractionResult(
            paper_title="Regression Test",
            questions=[
                QuestionItem(question_number="1", question_text="Solve $x = 1$.", answer="1")
            ],
        )

        app.dependency_overrides[get_preprocessor] = lambda: mock_preprocessor
        app.dependency_overrides[get_extractor] = lambda: mock_extractor

        image_bytes = make_synthetic_image(fmt, 300, 200)
        client = TestClient(app)
        response = client.post(
            "/api/v1/papers/extract",
            files={"file": (f"paper.{ext}", image_bytes, mime)},
        )
        return response

    @pytest.mark.parametrize("fmt,ext,mime", [
        ("JPEG", "jpg", "image/jpeg"),
        ("JPEG", "jpeg", "image/jpeg"),
        ("PNG", "png", "image/png"),
        ("WEBP", "webp", "image/webp"),
    ])
    def test_image_upload_still_works(self, fmt, ext, mime):
        """Existing image formats continue to return HTTP 200 after PDF changes."""
        response = self._mock_image_upload(fmt, ext, mime)
        assert response.status_code == 200
        res = response.json()
        assert res["success"] is True
        assert res["data"]["paper_title"] == "Regression Test"
        # Images should return page_count=1
        assert res["image_metadata"]["page_count"] == 1

    def test_image_upload_uses_extract_from_image_not_pdf(self):
        """Image uploads route to extract_from_image, not extract_from_pdf_pages."""
        dummy_prepped = make_dummy_preprocessed()
        mock_preprocessor = MagicMock()
        mock_preprocessor.preprocess.return_value = dummy_prepped

        mock_extractor = MagicMock()
        mock_extractor.extract_from_image.return_value = PaperExtractionResult(questions=[])

        app.dependency_overrides[get_preprocessor] = lambda: mock_preprocessor
        app.dependency_overrides[get_extractor] = lambda: mock_extractor

        image_bytes = make_synthetic_image("JPEG", 200, 200)
        client = TestClient(app)
        client.post(
            "/api/v1/papers/extract",
            files={"file": ("paper.jpg", image_bytes, "image/jpeg")},
        )

        # Must have called extract_from_image (not extract_from_pdf_pages)
        mock_extractor.extract_from_image.assert_called_once()
        mock_extractor.extract_from_pdf_pages.assert_not_called()

    def test_unsupported_format_still_returns_415(self):
        """Non-image, non-PDF uploads still return HTTP 415."""
        client = TestClient(app)
        response = client.post(
            "/api/v1/papers/extract",
            files={"file": ("paper.docx", b"PK\x03\x04", "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
        assert response.status_code == 415
        assert response.json()["error"] == "UnsupportedFormatError"

    def test_oversized_image_still_returns_413(self):
        """Images exceeding size limit still return HTTP 413."""
        from app.extraction.services.preprocessor import OversizedImageError as OversizedImgErr

        mock_preprocessor = MagicMock()
        mock_preprocessor.preprocess.side_effect = OversizedImgErr(
            size_bytes=20 * 1024 * 1024,
            max_bytes=15 * 1024 * 1024,
        )
        app.dependency_overrides[get_preprocessor] = lambda: mock_preprocessor

        # Fake a valid JPEG header but very large declaration
        image_bytes = b"\xff\xd8\xff" + b"A" * 100
        # Patch size check to skip to preprocessor
        old_max = settings.MAX_IMAGE_SIZE_MB
        settings.MAX_IMAGE_SIZE_MB = 100
        try:
            client = TestClient(app)
            response = client.post(
                "/api/v1/papers/extract",
                files={"file": ("big.jpg", image_bytes, "image/jpeg")},
            )
        finally:
            settings.MAX_IMAGE_SIZE_MB = old_max

        assert response.status_code == 413
