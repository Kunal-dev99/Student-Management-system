"""MT-4 (24) — backfill any users left without a tenant.

MT-1 backfilled users that existed then; users created between MT-1 and MT-4 (tests,
seeds, ad-hoc) could still be NULL because `User.tenant_id` had no default until MT-4.
This sweeps them to the default tenant so no principal ends up tenant-less (which would
bypass RLS). New users are stamped by the ORM default from here on.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "mt4_24_user_tenant_backfill"
down_revision: Union[str, Sequence[str], None] = "mt4_23_intelligence"
branch_labels = None
depends_on = None

DEFAULT_TENANT_ID = "00000000-0000-0000-0000-000000000001"


def upgrade() -> None:
    op.execute(sa.text(
        "UPDATE users SET tenant_id = CAST(:tid AS uuid) WHERE tenant_id IS NULL"
    ).bindparams(tid=DEFAULT_TENANT_ID))


def downgrade() -> None:
    # Data backfill; nothing to reverse.
    pass
