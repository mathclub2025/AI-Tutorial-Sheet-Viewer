"""Persist portal difficulty and review flags; topics use existing relation."""
import sqlalchemy as sa
from alembic import op

revision = "d104_portal_metadata"
down_revision = "bc0325102026"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("questions", sa.Column("difficulty", sa.String(12), nullable=True))
    op.add_column("questions", sa.Column("flag_note", sa.Text(), nullable=True))


def downgrade():
    op.drop_column("questions", "flag_note")
    op.drop_column("questions", "difficulty")
