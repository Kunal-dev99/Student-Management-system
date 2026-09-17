"""Full audit trail for rule suppressions.

Reshape ``ReportProfile.muted_rule_keys`` from ``list[str]`` to ``list[dict]`` with a proper record
per suppression: ``{ruleKey, reason, at, byUserId, byUserName}``. Existing string entries are
converted in place with reason=None so no data is lost (they read as "legacy — no reason given").

Also add ``StatutorySpecVersion.disabled_rule_keys`` so a rule can be suppressed at the pack level
(fixes every profile using the pack), which is the right fix when a bad advisory shipped an
inverted rule and every profile is going to hit it.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Union

import sqlalchemy as sa
from alembic import op

revision: str = "w4_rule_suppressions"
down_revision: Union[str, Sequence[str], None] = "w3_profile_muted_rules"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1) Add pack-level disabled rule keys (list of ruleKey strings).
    op.add_column(
        "statutory_spec_version",
        sa.Column("disabled_rule_keys", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
    )
    # 2) Convert any existing string entries in profile.muted_rule_keys into full records.
    #    We use jsonb_build_object per element so the shape matches what the code expects going forward.
    op.execute(
        """
        UPDATE report_profile
        SET muted_rule_keys = COALESCE(
            (
                SELECT jsonb_agg(
                    CASE
                        WHEN jsonb_typeof(elem) = 'string' THEN jsonb_build_object(
                            'ruleKey',      elem,
                            'reason',       NULL,
                            'at',           NULL,
                            'byUserId',     NULL,
                            'byUserName',   'legacy (before audit)'
                        )
                        ELSE elem
                    END
                )
                FROM jsonb_array_elements(muted_rule_keys::jsonb) AS elem
            ),
            '[]'::jsonb
        )::json
        WHERE muted_rule_keys IS NOT NULL
        """
    )


def downgrade() -> None:
    # Drop pack-level column; leave profile.muted_rule_keys shape unchanged on downgrade (it can
    # hold either strings or dicts, and older code reads only the ruleKey field).
    op.drop_column("statutory_spec_version", "disabled_rule_keys")
