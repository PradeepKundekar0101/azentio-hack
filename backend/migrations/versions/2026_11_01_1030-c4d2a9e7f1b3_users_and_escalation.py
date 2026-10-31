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
    # op.f() marks the names as final, so the naming convention is not applied a second time.
    op.drop_constraint(op.f("ck_alerts_status"), "alerts", type_="check")
    op.alter_column("alerts", "status", type_=sa.String(length=20), existing_type=sa.String(length=10))
    op.create_check_constraint(op.f("ck_alerts_status"), "alerts", f"status in ({NEW_STATUSES})")
    op.add_column("alerts", sa.Column("reviewed_by", sa.String(length=100), nullable=True))
    op.add_column("alerts", sa.Column("escalated_to", sa.String(length=20), nullable=True))
    op.add_column("alerts", sa.Column("escalated_by", sa.String(length=100), nullable=True))
    op.add_column("alerts", sa.Column("escalated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("alerts", sa.Column("escalation_reason", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(f"update alerts set status = 'open' where status not in ({OLD_STATUSES})")
    for column in ("escalation_reason", "escalated_at", "escalated_by", "escalated_to", "reviewed_by"):
        op.drop_column("alerts", column)
    op.drop_constraint(op.f("ck_alerts_status"), "alerts", type_="check")
    op.alter_column("alerts", "status", type_=sa.String(length=10), existing_type=sa.String(length=20))
    op.create_check_constraint(op.f("ck_alerts_status"), "alerts", f"status in ({OLD_STATUSES})")
    op.drop_table("users")
