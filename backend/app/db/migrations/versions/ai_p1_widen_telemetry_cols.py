"""AI-P1 fix — widen intelligence_telemetry.engine_used / fallback_path.

Both columns were sized for Groq-only model names ("openai/gpt-oss-120b", 18 chars)
and short deterministic-fallback labels. Two things outgrew them:

  1. OpenRouter model slugs run much longer — e.g.
     "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free" is 50 chars, already past
     engine_used's old String(30).
  2. `fallback_path` stores the actual provider error text (via ai_bridge._engine_from),
     and real provider errors ("Groq request failed: Error code: 400 - {...}") run
     several hundred characters — String(60) truncated them, which made every such
     insert raise `StringDataRightTruncationError` and silently drop the telemetry
     row entirely (caught by ai_bridge's try/except so it never broke the request,
     but it meant real failures left zero audit trail).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "ai_p1_widen_telemetry_cols"
down_revision: Union[str, Sequence[str], None] = "ai_p6_policy_compiler"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("intelligence_telemetry", "engine_used",
                     type_=sa.String(length=120), existing_type=sa.String(length=30))
    op.alter_column("intelligence_telemetry", "fallback_path",
                     type_=sa.String(length=500), existing_type=sa.String(length=60),
                     existing_nullable=True)


def downgrade() -> None:
    op.alter_column("intelligence_telemetry", "fallback_path",
                     type_=sa.String(length=60), existing_type=sa.String(length=500),
                     existing_nullable=True)
    op.alter_column("intelligence_telemetry", "engine_used",
                     type_=sa.String(length=30), existing_type=sa.String(length=120))
