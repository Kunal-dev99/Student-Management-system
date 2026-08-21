"""baseline

Revision ID: e95334ff3d83
Revises: 
Create Date: 2026-08-21 16:56:35.611527
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e95334ff3d83'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
