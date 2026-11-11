import json
import time
from dotenv import load_dotenv

load_dotenv()

from app.services.pdf_processor import PDFProcessor
from app.services.preprocessor import ImagePreprocessor
from app.services.extractor import GeminiMathExtractor
from app.config import settings

PDF_PATH = r"C:\Users\vaibh\.gemini\antigravity\brain\79c7322a-12c8-4863-902c-a768f64f1f93\.user_uploaded\media_1793784246898_fd1eeb32.pdf"
OUTPUT_PATH = r"C:\Users\vaibh\.gemini\antigravity\brain\79c7322a-12c8-4863-902c-a768f64f1f93\live_extraction_result.json"

def run():
    print(f"Reading PDF from {PDF_PATH}...")
    with open(PDF_PATH, "rb") as f:
        pdf_bytes = f.read()

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

    # Save JSON output
    result_dict = result.model_dump()
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result_dict, f, indent=2, ensure_ascii=False)
    print(f"Result written to {OUTPUT_PATH}")

    # Print summary
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

if __name__ == "__main__":
    run()
