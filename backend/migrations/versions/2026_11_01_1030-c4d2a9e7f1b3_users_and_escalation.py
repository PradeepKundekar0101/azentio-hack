"""users and alert escalation

Revision ID: c4d2a9e7f1b3
Revises: 8b5b83935338
Create Date: 2026-11-01 10:30:00

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c4d2a9e7f1b3"
down_revision: str | Sequence[str] | None = "8b5b83935338"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_STATUSES = "'open', 'reviewed', 'dismissed'"
NEW_STATUSES = "'open', 'reviewed', 'dismissed', 'evidence_requested', 'escalated'"


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column("username", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=120), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_by", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("role in ('analyst', 'senior_reviewer', 'admin')", name=op.f("ck_users_role")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
        sa.UniqueConstraint("username", name=op.f("uq_users_username")),
    )
    with op.batch_alter_table("alerts") as batch:
        batch.drop_constraint("ck_alerts_status", type_="check")
        batch.alter_column("status", type_=sa.String(length=20), existing_type=sa.String(length=10))
        batch.create_check_constraint("ck_alerts_status", f"status in ({NEW_STATUSES})")
        batch.add_column(sa.Column("reviewed_by", sa.String(length=100), nullable=True))
        batch.add_column(sa.Column("escalated_to", sa.String(length=20), nullable=True))
        batch.add_column(sa.Column("escalated_by", sa.String(length=100), nullable=True))
        batch.add_column(sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("escalation_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(f"update alerts set status = 'open' where status not in ({OLD_STATUSES})")
    with op.batch_alter_table("alerts") as batch:
        batch.drop_column("escalation_reason")
        batch.drop_column("escalated_at")
        batch.drop_column("escalated_by")
        batch.drop_column("escalated_to")
        batch.drop_column("reviewed_by")
        batch.drop_constraint("ck_alerts_status", type_="check")
        batch.alter_column("status", type_=sa.String(length=10), existing_type=sa.String(length=20))
        batch.create_check_constraint("ck_alerts_status", f"status in ({OLD_STATUSES})")
    op.drop_table("users")
