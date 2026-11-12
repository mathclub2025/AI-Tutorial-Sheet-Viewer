import argparse
import json
import time
from pathlib import Path

from app.extraction.config import settings
from app.extraction.services.extractor import GeminiMathExtractor
from app.extraction.services.pdf_processor import PDFProcessor
from app.extraction.services.preprocessor import ImagePreprocessor


def run(pdf_path: Path, output_path: Path):
    print(f"Reading PDF from {pdf_path}...")
    pdf_bytes = pdf_path.read_bytes()

    print(f"PDF size: {len(pdf_bytes)} bytes")
    pdf_processor = PDFProcessor()
    preprocessor = ImagePreprocessor()

    print("Rendering PDF pages...")
    rendered_pages = pdf_processor.process_pdf(pdf_bytes)
    print(f"Rendered {len(rendered_pages)} pages.")

    print("Preprocessing pages...")
    preprocessed_pages = []
    for p in rendered_pages:
        prep_res = preprocessor.preprocess(p.image_bytes)
        preprocessed_pages.append((p.page_number, prep_res))

    print(
        f"Initializing GeminiMathExtractor with "
        f"Primary: {settings.GEMINI_MODEL}, "
        f"Fallback: {settings.GEMINI_FALLBACK_MODEL}, "
        f"Reconciler: {settings.GEMINI_RECONCILIATION_MODEL}..."
    )
    extractor = GeminiMathExtractor(
        api_key=settings.GEMINI_API_KEY,
        model=settings.GEMINI_MODEL,
        fallback_model=settings.GEMINI_FALLBACK_MODEL,
        reconciliation_model=settings.GEMINI_RECONCILIATION_MODEL,
    )

    start_time = time.time()
    print("Executing extract_from_pdf_pages (Stage 1 + Stage 2)...")
    result = extractor.extract_from_pdf_pages(preprocessed_pages)
    elapsed = time.time() - start_time

    print(f"\nCompleted in {elapsed:.2f}s!")
    print(f"Reconciliation mode: {result.reconciliation_mode}")
    print(f"Total questions detected: {result.total_questions_detected}")
    print(f"Requires human review: {result.requires_human_review}")
    print(f"Review reasons: {result.review_reasons}")
    print(f"Paper title: {result.paper_title}")
    print(f"Raw blocks captured: {len(result.raw_blocks)}")

    result_dict = result.model_dump()
    output_path.write_text(
        json.dumps(result_dict, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Result written to {output_path}")

    print("\n=== Question Summary ===")
    for q in result.questions:
        page_refs = getattr(q, "page_numbers", [q.page_number] if q.page_number else [])
        print(
            f"- Q{q.question_number} (pages {page_refs}): "
            f"'{q.question_text[:60]}...' | "
            f"answer={q.answer} | "
            f"has_explicit={q.has_explicit_answer} | "
            f"subqs={len(q.subquestions)} | "
            f"review={q.needs_human_review} | "
            f"src={q.source_block_ids}"
        )
        for sq in q.subquestions:
            sq_page = getattr(sq, "page_number", None)
            print(
                f"    * ({sq.subquestion_label}) page={sq_page}: "
                f"'{sq.text[:50]}...' | "
                f"answer={sq.answer} | "
                f"review={sq.needs_human_review} | "
                f"src={sq.source_block_ids}"
            )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("pdf", type=Path)
    parser.add_argument("output", nargs="?", type=Path, default=Path("live_extraction_result.json"))
    args = parser.parse_args()
    run(args.pdf, args.output)


if __name__ == "__main__":
    main()
