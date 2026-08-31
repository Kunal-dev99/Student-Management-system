"""ICR gap 1 — persisted registration_status + milestone registration_effect.

Adds:
- student.registration_status (nullable String) — flipped automatically on decide when the
  milestone's registration_effect metadata says so; NULL keeps the pre-Phase-ICR derivation.
- milestone_definition.registration_effect (nullable JSON) — configuration that tells the
  progression engine to flip student.registration_status on a decision.

Additive only; no existing rows touched.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "icr_g1_reg_flip"
down_revision: Union[str, Sequence[str], None] = "f6_assistant_notif"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("student", sa.Column("registration_status", sa.String(length=80), nullable=True))
    op.add_column("milestone_definition", sa.Column("registration_effect", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("milestone_definition", "registration_effect")
    op.drop_column("student", "registration_status")
