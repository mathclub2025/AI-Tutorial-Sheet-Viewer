"""Add management sessions, durable uploads, assets and integration tasks.

Existing documents/questions are retained. Old vectors require explicit reindexing
because their content_revision defaults to zero.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "bc0325102026"
down_revision = "ec27961bf9a9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "integration_tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("dedupe_key", sa.String(length=300), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column(
            "payload",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("lease_token", sa.String(length=64), nullable=True),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_error", sa.String(length=1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('dispatch', 'index')", name="ck_integration_tasks_kind"),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed')",
            name="ck_integration_tasks_status",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedupe_key"),
    )
    op.create_index(
        "ix_integration_tasks_due", "integration_tasks", ["status", "next_attempt_at"], unique=False
    )
    op.create_table(
        "auth_sessions",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("token_hash"),
    )
    op.create_index(op.f("ix_auth_sessions_user_id"), "auth_sessions", ["user_id"], unique=False)
    op.create_table(
        "content_assets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("document_id", sa.Uuid(), nullable=False),
        sa.Column("document_version", sa.String(length=100), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("object_key", sa.String(length=1024), nullable=False),
        sa.Column("mime_type", sa.String(length=127), nullable=False),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_key"),
    )
    op.create_index(
        op.f("ix_content_assets_document_id"), "content_assets", ["document_id"], unique=False
    )
    op.create_table(
        "upload_intents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=True),
        sa.Column("client_key", sa.String(length=300), nullable=False),
        sa.Column("purpose", sa.String(length=24), nullable=False),
        sa.Column(
            "request_data",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column("object_key", sa.String(length=1024), nullable=False),
        sa.Column("sealed_key", sa.String(length=1024), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("document_id", sa.Uuid(), nullable=True),
        sa.Column("asset_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["content_assets.id"],
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("client_key"),
        sa.UniqueConstraint("object_key"),
        sa.UniqueConstraint("sealed_key"),
    )
    op.add_column("answers", sa.Column("solution_asset_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_answers_asset",
        "answers",
        "content_assets",
        ["solution_asset_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.add_column(
        "question_embeddings",
        sa.Column("content_revision", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "questions", sa.Column("revision", sa.Integer(), server_default="1", nullable=False)
    )
    op.add_column("questions", sa.Column("question_asset_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "fk_questions_asset",
        "questions",
        "content_assets",
        ["question_asset_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade():
    op.drop_constraint("fk_questions_asset", "questions", type_="foreignkey")
    op.drop_column("questions", "question_asset_id")
    op.drop_column("questions", "revision")
    op.drop_column("question_embeddings", "content_revision")
    op.drop_constraint("fk_answers_asset", "answers", type_="foreignkey")
    op.drop_column("answers", "solution_asset_id")
    op.drop_table("upload_intents")
    op.drop_index(op.f("ix_content_assets_document_id"), table_name="content_assets")
    op.drop_table("content_assets")
    op.drop_index(op.f("ix_auth_sessions_user_id"), table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_index("ix_integration_tasks_due", table_name="integration_tasks")
    op.drop_table("integration_tasks")
