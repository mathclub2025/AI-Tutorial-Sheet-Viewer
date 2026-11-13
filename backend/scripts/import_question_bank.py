"""Import the tagged question bank into PostgreSQL and queue embedding index tasks."""

import argparse
import json
from decimal import Decimal
from pathlib import Path

from sqlalchemy import delete, select

from app.data_service.service import DataService
from app.data_service.settings import DataServiceSettings
from app.data_service.tasks import queue_index
from app.data_service.worker import Worker
from app.persistence.database import create_database_engine, create_session_factory, session_scope
from app.persistence.models import (
    Document,
    QuestionEmbedding,
    QuestionRecord,
    QuestionTopic,
)

BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = BACKEND_ROOT / "app/topic_classifier/data/question_bank.json"
DEFAULT_TAXONOMY = BACKEND_ROOT / "app/topic_classifier/data/taxonomy.json"


def load_bank(dataset_path):
    payload = json.loads(dataset_path.read_text(encoding="utf-8"))
    return payload["questions"] if isinstance(payload, dict) else payload


def load_taxonomy(taxonomy_path):
    return json.loads(taxonomy_path.read_text(encoding="utf-8"))["subjects"]


def module_number(module_key):
    digits = "".join(character for character in module_key if character.isdigit())
    return int(digits) if digits else None


def document_key(source_type, year):
    return f"question-bank-{source_type}-{year if year is not None else 'undated'}"


def document_title(source_type, year):
    if year is None:
        return f"Imported question bank ({source_type})"
    return f"Imported question bank ({source_type}, {year})"


def upsert_document(session, source_type, year, size_bytes):
    external_id = document_key(source_type, year)
    document = session.scalar(select(Document).where(Document.external_id == external_id))
    if document is None:
        document = Document(
            external_id=external_id,
            title=document_title(source_type, year),
            document_type="question_paper" if source_type == "pyq" else "tutorial_sheet",
            source_type=source_type,
            publication_year=year,
            original_filename=external_id + ".json",
            object_key=f"imported/{external_id}.json",
            bucket_name="local-import",
            mime_type="application/json",
            file_size_bytes=size_bytes,
            processing_status="succeeded",
            visibility="public",
        )
        session.add(document)
        session.flush()
        return document, True
    if document.source_type != source_type or document.publication_year != year:
        document.source_type = source_type
        document.publication_year = year
    return document, False


def resolve_topics(record, taxonomy):
    subject = taxonomy[record["subject"]]
    confidence = Decimal(str(record.get("confidence", 0)))
    resolved = []
    for key in record.get("topic_keys") or []:
        _, module_key, topic_key = key.split("/")
        resolved.append(
            (module_key, subject["modules"][module_key]["topics"][topic_key]["name"], confidence)
        )
    if not resolved:
        module_key = record["module"]
        for topic_key in record["topics"]:
            resolved.append(
                (module_key, subject["modules"][module_key]["topics"][topic_key]["name"], confidence)
            )
    return resolved


def upsert_question(session, record, document, subject, module, topics):
    question = session.scalar(
        select(QuestionRecord).where(QuestionRecord.external_id == record["id"])
    )
    status = "pending_review" if record.get("needs_review") else "approved"
    if question is None:
        question = QuestionRecord(
            external_id=record["id"],
            document_id=document.id,
            subject_id=subject.id,
            module_id=module.id if module is not None else None,
            document_version=document.current_version,
            question_text=record["text"],
            status=status,
        )
        session.add(question)
        session.flush()
    else:
        if question.question_text != record["text"]:
            question.revision += 1
        question.document_id = document.id
        question.subject_id = subject.id
        question.module_id = module.id if module is not None else None
        question.question_text = record["text"]
        question.status = status
        question.document_version = document.current_version
        session.flush()
    session.execute(delete(QuestionTopic).where(QuestionTopic.question_id == question.id))
    for _, topic_name, confidence in topics:
        topic = DataService._get_or_create_topic(session, subject, topic_name)
        session.add(
            QuestionTopic(
                question_id=question.id,
                topic_id=topic.id,
                confidence=confidence,
                assigned_by="ai",
            )
        )
    session.flush()
    return question


def ensure_index_task(session, question, model):
    if question.status != "approved":
        return False
    embedding = session.get(QuestionEmbedding, question.id)
    if (
        embedding is not None
        and embedding.model_name == model
        and embedding.content_revision == question.revision
    ):
        return False
    queue_index(session, question, model)
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--taxonomy", type=Path, default=DEFAULT_TAXONOMY)
    parser.add_argument(
        "--index", action="store_true", help="Run the indexing worker until the queue drains"
    )
    args = parser.parse_args()
    settings = DataServiceSettings()
    engine = create_database_engine(settings.database_url())
    factory = create_session_factory(engine)
    taxonomy = load_taxonomy(args.taxonomy)
    bank = load_bank(args.dataset)
    dataset_bytes = max(1, len(args.dataset.read_bytes()))
    grouped = {}
    for record in bank:
        grouped.setdefault((record["source"], record.get("year")), []).append(record)
    summary = {"documents": 0, "questions": 0, "topics": 0, "index_tasks": 0, "model": settings.embedding_model}
    with session_scope(factory) as session:
        for (source_type, year), records in sorted(
            grouped.items(), key=lambda item: (item[0][0], -1 if item[0][1] is None else item[0][1])
        ):
            document, created = upsert_document(session, source_type, year, dataset_bytes)
            if created:
                summary["documents"] += 1
            for record in records:
                subject_key = taxonomy[record["subject"]]
                subject = DataService._get_or_create_subject(session, subject_key["name"])
                module = None
                if record.get("module"):
                    module_key = record["module"]
                    module = DataService._get_or_create_module(
                        session, subject, subject_key["modules"][module_key]["name"]
                    )
                    if module.module_number is None:
                        module.module_number = module_number(module_key)
                topics = resolve_topics(record, taxonomy)
                question = upsert_question(session, record, document, subject, module, topics)
                summary["questions"] += 1
                summary["topics"] += len(topics)
                if ensure_index_task(session, question, settings.embedding_model):
                    summary["index_tasks"] += 1
    print(json.dumps(summary, sort_keys=True))
    if args.index:
        worker = Worker(factory, settings)
        while worker.run_once():
            pass
        print(json.dumps({"indexing": "drained"}))
    engine.dispose()


if __name__ == "__main__":
    main()
