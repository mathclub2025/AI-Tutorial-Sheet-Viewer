# Database schema guide

This document explains the SQLAlchemy persistence schema in
[`app/persistence/models.py`](app/persistence/models.py). That Python module is
the model source of truth; Alembic migrations in
[`migrations/versions/`](migrations/versions/) are the versioned database
changes. API request/response schemas are separate and live in
[`docs/contracts/`](docs/contracts/).

## At a glance

The schema stores users, document metadata and storage locations, extracted
questions and answers, subject/module/topic classification, processing and
callback records, embeddings, and audit events.

Most tables use an internal UUID primary key. `documents.external_id` and
`questions.external_id` provide stable string identifiers for API contracts
that use string IDs. Do not expose an internal UUID in place of an external ID
without coordinating that API change.

PostgreSQL is the target database. The migration enables the `vector`
extension. JSON fields use PostgreSQL `JSONB` when available and have a JSON
variant for SQLite tests.

## Tables

| Table | Purpose and important data |
| --- | --- |
| `users` | User/account starting point: name, email, password hash, role, active flag and timestamps. Roles are constrained to `admin`, `reviewer`, and `uploader`. This schema does not itself implement login, role provisioning, or authorization. |
| `subjects` | Top-level curriculum labels, optional description, and active flag. A case-insensitive unique index prevents duplicate labels with different capitalization. |
| `modules` | Modules belonging to a subject, with optional positive module number, name and description. Subject deletion cascades to modules. Module names are unique within a subject, including case-insensitive uniqueness. |
| `topics` | Hierarchical topics belonging to a subject. `parent_topic_id` links a child topic to its parent. Deleting a subject or parent topic cascades to its topics. Root and child topics have separate case-insensitive uniqueness rules. |
| `documents` | Canonical document and object-storage metadata: external ID, version, title, document/source types, object key, bucket, MIME type, size, optional SHA-256, publication year, subject/module/uploader links, visibility, extraction state and indexing state. The object key and external ID are unique. |
| `questions` | Extracted or curated question text and metadata: external ID, owning document, optional subject/module, document version, extraction/job IDs, question number/type, marks, page range and review status. A document owns its questions; deleting the document cascades to them. |
| `answers` | Answer/solution text for a question, optional source document and external ID, answer type, page range and independent review status. Deleting a question cascades to its answers; deleting an optional source document clears that reference. |
| `question_topics` | Many-to-many association between questions and topics. It records whether assignment was manual or AI-generated and an optional confidence score from 0 to 1. |
| `document_processing_jobs` | Local processing/indexing bookkeeping, including document, job type, client idempotency key, document version, optional source type and AI job ID, local status, attempts, result hash, metadata and timestamps. The client key and non-null AI job ID are unique. This table does not replace the AI service's authoritative job state or provide a queue/worker. |
| `query_events` | Persisted search/ask/explain capture: event ID, timestamp, event type, request ID, optional query/question/filter data and result count. Event ID is the primary key for deduplication. |
| `document_result_events` | Receipt for a terminal extraction callback: event ID, content hash, job/document/version identifiers, indexing acknowledgement and creation time. It supports retry-safe callback intake. |
| `question_embeddings` | One pgvector embedding per question, with model name and update time. The vector dimension and vector index are intentionally unspecified until the embedding model contract is agreed. |
| `audit_logs` | Actor (optional), action, entity type and ID, JSON details and creation time. The actor reference is cleared if the user is deleted. Retention and audit-writing policy still need to be defined by the integrated application. |

## Exact PostgreSQL table schema

The DDL below is compiled from `Base.metadata` in
`app/persistence/models.py`. It lists every column, constraint, and index
represented by the current ORM models. The first migration separately enables
the `vector` extension required by `question_embeddings`.

Defaults declared as SQLAlchemy `default=` values (such as UUIDs, timestamps,
and initial status values) are applied by SQLAlchemy on inserts; they are not
PostgreSQL `DEFAULT` clauses. Only the defaults shown below are server
defaults. `onupdate=utc_now` is also handled by ORM writes, not by a database
trigger.

```sql
CREATE TABLE document_result_events (
    event_id VARCHAR(128) NOT NULL,
    content_sha256 VARCHAR(64) NOT NULL,
    job_id VARCHAR(128) NOT NULL,
    document_id VARCHAR(128) NOT NULL,
    document_version VARCHAR(100) NOT NULL,
    indexing_status VARCHAR(24) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (event_id),
    CONSTRAINT ck_document_result_events_indexing_status
        CHECK (indexing_status IN ('pending', 'queued', 'indexed', 'not_applicable'))
);

CREATE TABLE query_events (
    event_id VARCHAR(128) NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL,
    event_type VARCHAR(16) NOT NULL,
    request_id VARCHAR(128) NOT NULL,
    query TEXT,
    question_id VARCHAR(128),
    filters JSONB,
    result_count INTEGER,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (event_id),
    CONSTRAINT ck_query_events_type CHECK (event_type IN ('search', 'ask', 'explain'))
);
CREATE INDEX ix_query_events_created_at ON query_events (created_at);

CREATE TABLE subjects (
    id UUID NOT NULL,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    is_active BOOLEAN NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    UNIQUE (name)
);
CREATE UNIQUE INDEX uq_subjects_name_lower ON subjects (lower(name));

CREATE TABLE users (
    id UUID NOT NULL,
    name VARCHAR(200) NOT NULL,
    email VARCHAR(320) NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(32) NOT NULL,
    is_active BOOLEAN NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_users_role CHECK (role IN ('admin', 'reviewer', 'uploader'))
);
CREATE UNIQUE INDEX uq_users_email_lower ON users (lower(email));

CREATE TABLE audit_logs (
    id UUID NOT NULL,
    actor_id UUID,
    action VARCHAR(100) NOT NULL,
    entity_type VARCHAR(100) NOT NULL,
    entity_id VARCHAR(128) NOT NULL,
    details JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    FOREIGN KEY (actor_id) REFERENCES users (id) ON DELETE SET NULL
);
CREATE INDEX ix_audit_logs_actor_id ON audit_logs (actor_id);
CREATE INDEX ix_audit_logs_entity ON audit_logs (entity_type, entity_id);

CREATE TABLE modules (
    id UUID NOT NULL,
    subject_id UUID NOT NULL,
    name VARCHAR(200) NOT NULL,
    module_number INTEGER,
    description TEXT,
    PRIMARY KEY (id),
    CONSTRAINT uq_modules_subject_number UNIQUE (subject_id, module_number),
    CONSTRAINT uq_modules_subject_name UNIQUE (subject_id, name),
    CONSTRAINT ck_modules_positive_number
        CHECK (module_number IS NULL OR module_number > 0),
    FOREIGN KEY (subject_id) REFERENCES subjects (id) ON DELETE CASCADE
);
CREATE INDEX ix_modules_subject_id ON modules (subject_id);
CREATE UNIQUE INDEX uq_modules_subject_name_lower
    ON modules (subject_id, lower(name));

CREATE TABLE topics (
    id UUID NOT NULL,
    subject_id UUID NOT NULL,
    parent_topic_id UUID,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    PRIMARY KEY (id),
    FOREIGN KEY (subject_id) REFERENCES subjects (id) ON DELETE CASCADE,
    FOREIGN KEY (parent_topic_id) REFERENCES topics (id) ON DELETE CASCADE
);
CREATE INDEX ix_topics_parent_topic_id ON topics (parent_topic_id);
CREATE INDEX ix_topics_subject_id ON topics (subject_id);
CREATE UNIQUE INDEX uq_topics_child_name
    ON topics (subject_id, parent_topic_id, lower(name))
    WHERE parent_topic_id IS NOT NULL;
CREATE UNIQUE INDEX uq_topics_root_name
    ON topics (subject_id, lower(name))
    WHERE parent_topic_id IS NULL;

CREATE TABLE documents (
    id UUID NOT NULL,
    external_id VARCHAR(128) NOT NULL,
    current_version VARCHAR(100) DEFAULT 'v1' NOT NULL,
    publication_year INTEGER,
    subject_id UUID,
    module_id UUID,
    uploaded_by UUID,
    title VARCHAR(500) NOT NULL,
    document_type VARCHAR(32) NOT NULL,
    source_type VARCHAR(24),
    original_filename VARCHAR(255) NOT NULL,
    object_key VARCHAR(1024) NOT NULL,
    bucket_name VARCHAR(255) NOT NULL,
    mime_type VARCHAR(127) NOT NULL,
    file_size_bytes INTEGER NOT NULL,
    sha256 VARCHAR(64),
    processing_status VARCHAR(24) NOT NULL,
    indexing_status VARCHAR(24) NOT NULL,
    visibility VARCHAR(16) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_documents_type
        CHECK (document_type IN ('question_paper', 'answer_sheet', 'tutorial_sheet', 'other')),
    CONSTRAINT ck_documents_source_type
        CHECK (source_type IS NULL OR source_type IN ('tutorial', 'pyq', 'practice')),
    CONSTRAINT ck_documents_processing_status
        CHECK (processing_status IN ('pending', 'processing', 'succeeded', 'failed')),
    CONSTRAINT ck_documents_visibility CHECK (visibility IN ('private', 'public')),
    CONSTRAINT ck_documents_publication_year
        CHECK (publication_year IS NULL OR publication_year BETWEEN 1990 AND 2100),
    CONSTRAINT ck_documents_indexing_status
        CHECK (indexing_status IN ('pending', 'queued', 'indexed', 'failed')),
    CONSTRAINT ck_documents_positive_size CHECK (file_size_bytes > 0),
    CONSTRAINT uq_documents_external_id UNIQUE (external_id),
    CONSTRAINT uq_documents_object_key UNIQUE (object_key),
    FOREIGN KEY (subject_id) REFERENCES subjects (id) ON DELETE SET NULL,
    FOREIGN KEY (module_id) REFERENCES modules (id) ON DELETE SET NULL,
    FOREIGN KEY (uploaded_by) REFERENCES users (id) ON DELETE SET NULL
);
CREATE INDEX ix_documents_module_id ON documents (module_id);
CREATE INDEX ix_documents_subject_id ON documents (subject_id);
CREATE INDEX ix_documents_subject_module_visibility
    ON documents (subject_id, module_id, visibility);
CREATE INDEX ix_documents_uploaded_by ON documents (uploaded_by);

CREATE TABLE document_processing_jobs (
    id UUID NOT NULL,
    document_id UUID NOT NULL,
    job_type VARCHAR(24) NOT NULL,
    client_job_key VARCHAR(128) NOT NULL,
    document_version VARCHAR(100) DEFAULT 'v1' NOT NULL,
    source_type VARCHAR(24),
    ai_job_id VARCHAR(128),
    status VARCHAR(24) NOT NULL,
    attempts INTEGER NOT NULL,
    error_message VARCHAR(2000),
    result_sha256 VARCHAR(64),
    metadata JSONB NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    started_at TIMESTAMP WITH TIME ZONE,
    finished_at TIMESTAMP WITH TIME ZONE,
    PRIMARY KEY (id),
    CONSTRAINT ck_processing_jobs_type
        CHECK (job_type IN ('extraction', 'ocr', 'indexing')),
    CONSTRAINT ck_processing_jobs_source_type
        CHECK (source_type IS NULL OR source_type IN ('tutorial', 'pyq', 'practice')),
    CONSTRAINT ck_processing_jobs_status
        CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
    CONSTRAINT ck_processing_jobs_attempts CHECK (attempts >= 0),
    CONSTRAINT uq_processing_jobs_client_key UNIQUE (client_job_key),
    CONSTRAINT uq_processing_jobs_ai_job_id UNIQUE (ai_job_id),
    FOREIGN KEY (document_id) REFERENCES documents (id) ON DELETE CASCADE
);
CREATE INDEX ix_document_processing_jobs_document_id
    ON document_processing_jobs (document_id);
CREATE INDEX ix_processing_jobs_status_created
    ON document_processing_jobs (status, created_at);

CREATE TABLE questions (
    id UUID NOT NULL,
    external_id VARCHAR(128) NOT NULL,
    document_id UUID NOT NULL,
    subject_id UUID,
    module_id UUID,
    document_version VARCHAR(100),
    extraction_id VARCHAR(128),
    processing_job_id UUID,
    question_number VARCHAR(100),
    question_text TEXT NOT NULL,
    question_type VARCHAR(64),
    marks NUMERIC(7, 2),
    page_start INTEGER,
    page_end INTEGER,
    status VARCHAR(24) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_questions_status
        CHECK (status IN ('draft', 'pending_review', 'approved', 'rejected', 'archived')),
    CONSTRAINT ck_questions_page_start CHECK (page_start IS NULL OR page_start > 0),
    CONSTRAINT ck_questions_page_range CHECK (page_end IS NULL OR page_end >= page_start),
    CONSTRAINT ck_questions_nonnegative_marks CHECK (marks IS NULL OR marks >= 0),
    CONSTRAINT uq_questions_job_extraction UNIQUE (processing_job_id, extraction_id),
    UNIQUE (external_id),
    FOREIGN KEY (document_id) REFERENCES documents (id) ON DELETE CASCADE,
    CONSTRAINT fk_questions_subject_id_subjects
        FOREIGN KEY (subject_id) REFERENCES subjects (id) ON DELETE SET NULL,
    CONSTRAINT fk_questions_module_id_modules
        FOREIGN KEY (module_id) REFERENCES modules (id) ON DELETE SET NULL,
    CONSTRAINT fk_questions_processing_job_id_document_processing_jobs
        FOREIGN KEY (processing_job_id)
        REFERENCES document_processing_jobs (id) ON DELETE SET NULL
);
CREATE INDEX ix_questions_document_id ON questions (document_id);
CREATE INDEX ix_questions_module_id ON questions (module_id);
CREATE INDEX ix_questions_processing_job_id ON questions (processing_job_id);
CREATE INDEX ix_questions_status_document ON questions (status, document_id);
CREATE INDEX ix_questions_status_subject ON questions (status, subject_id);
CREATE INDEX ix_questions_subject_id ON questions (subject_id);

CREATE TABLE answers (
    id UUID NOT NULL,
    question_id UUID NOT NULL,
    source_document_id UUID,
    external_id VARCHAR(128),
    answer_text TEXT NOT NULL,
    answer_type VARCHAR(64),
    page_start INTEGER,
    page_end INTEGER,
    review_status VARCHAR(24) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT ck_answers_review_status
        CHECK (review_status IN ('draft', 'pending_review', 'approved', 'rejected', 'archived')),
    CONSTRAINT ck_answers_page_start CHECK (page_start IS NULL OR page_start > 0),
    CONSTRAINT ck_answers_page_range CHECK (page_end IS NULL OR page_end >= page_start),
    CONSTRAINT uq_answers_external_id UNIQUE (external_id),
    FOREIGN KEY (question_id) REFERENCES questions (id) ON DELETE CASCADE,
    FOREIGN KEY (source_document_id) REFERENCES documents (id) ON DELETE SET NULL
);
CREATE INDEX ix_answers_question_id ON answers (question_id);
CREATE INDEX ix_answers_question_review ON answers (question_id, review_status);
CREATE INDEX ix_answers_source_document_id ON answers (source_document_id);

CREATE TABLE question_embeddings (
    question_id UUID NOT NULL,
    embedding VECTOR NOT NULL,
    model_name VARCHAR(255) NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
    PRIMARY KEY (question_id),
    FOREIGN KEY (question_id) REFERENCES questions (id) ON DELETE CASCADE
);

CREATE TABLE question_topics (
    question_id UUID NOT NULL,
    topic_id UUID NOT NULL,
    confidence NUMERIC(4, 3),
    assigned_by VARCHAR(32) NOT NULL,
    PRIMARY KEY (question_id, topic_id),
    CONSTRAINT ck_question_topics_confidence
        CHECK (confidence IS NULL OR (confidence >= 0 AND confidence <= 1)),
    CONSTRAINT ck_question_topics_assigned_by
        CHECK (assigned_by IN ('manual', 'ai')),
    FOREIGN KEY (question_id) REFERENCES questions (id) ON DELETE CASCADE,
    FOREIGN KEY (topic_id) REFERENCES topics (id) ON DELETE CASCADE
);
```

## Relationships

```text
users 1 ── * documents                         (uploader; set null on user deletion)
subjects 1 ── * modules                         (cascade)
subjects 1 ── * topics                          (cascade)
topics 1 ── * topics                            (parent/child; cascade)
documents 1 ── * questions                      (cascade)
subjects 1 ── * questions                       (optional; set null)
modules 1 ── * questions                        (optional; set null)
questions * ── * topics                         (through question_topics)
questions 1 ── * answers                        (cascade)
documents 1 ── * answers                        (optional source document; set null)
documents 1 ── * document_processing_jobs       (cascade)
document_processing_jobs 1 ── * questions       (optional provenance; set null)
questions 1 ── 0..1 question_embeddings         (cascade)
users 1 ── * audit_logs                         (optional actor; set null)
```

`query_events` and `document_result_events` intentionally store contract
identifiers rather than foreign keys. This allows intake and replay tracking
without coupling those receipts to local UUID lifecycle.

## Important validation rules

- Document types: `question_paper`, `answer_sheet`, `tutorial_sheet`, `other`.
- Source types: `tutorial`, `pyq`, `practice` (nullable where the record need
  not be source-classified).
- Document processing state: `pending`, `processing`, `succeeded`, `failed`.
- Document indexing state: `pending`, `queued`, `indexed`, `failed`.
- Document visibility: `private`, `public`. Search should only return approved
  questions attached to public documents.
- Question and answer review states: `draft`, `pending_review`, `approved`,
  `rejected`, `archived`.
- Processing job types: `extraction`, `ocr`, `indexing`; local job states:
  `queued`, `running`, `succeeded`, `failed`.
- Query event types: `search`, `ask`, `explain`.
- Page numbers must be positive; page end cannot precede page start; marks
  cannot be negative; file size must be positive; publication year, when
  present, must be between 1990 and 2100.
- Extracted questions are kept pending review by the data-service flow. Do not
  treat extraction completion as approval or successful indexing.

These values are enforced in part by database check constraints and in part by
application validation. When changing a value set or relationship, update the
ORM model, add a new Alembic migration, update contract/service tests, and
coordinate any dependent API or AI contract.

## Migration history and local workflow

The migration chain currently contains:

1. `a102e892e276` — initial persistence schema and pgvector extension.
2. `15c6c35bbf9f` — Person 2 data-service tables and added provenance,
   versioning, and classification fields.
3. `a23973fbea99` — case-insensitive catalog-name uniqueness.
4. `ec27961bf9a9` — metadata integrity constraints.

With the backend virtual environment active, apply changes using:

```powershell
python -m alembic upgrade head
python -m alembic current
python -m alembic check
```

The database role needs permission to create `vector` when the initial
migration is applied. Do not run downgrades or reset a shared database without
explicit coordination. Keep database URLs and passwords in a local ignored
`.env`, never in migrations or documentation.

## Known integration boundaries

- The user table is a schema foundation, not a complete authentication or
  authorization system.
- B2 helpers exist, but authenticated upload initiation/confirmation routes
  and a reviewer/admin workflow are not implemented.
- Local processing-job records are not a durable queue and do not supersede
  AI-owned job status.
- Callback results can store extracted solutions for review, but matching an
  answer to a separate answer-sheet document is not agreed.
- Search is currently lexical. Embedding model, dimension, indexing worker,
  and vector index require an agreed AI contract.
- `updated_at` is updated by ORM writes; direct SQL updates do not automatically
  change it.
