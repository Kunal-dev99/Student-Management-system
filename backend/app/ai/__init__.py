"""AI-as-a-layer.

The deterministic core decides; the model narrates. Every public function here has the
same contract — it takes structured input, calls the model in JSON mode with one shape,
validates the reply against that shape, and returns a deterministic fallback on any
failure (network, parse, out-of-set id, timeout).

Turn the model off and everything still works, in plainer prose.
"""
from app.ai.types import (
    Candidate,
    ClassifyResult,
    Evidence,
    Narration,
    RankResult,
    ReadResult,
)

__all__ = [
    "Candidate",
    "ClassifyResult",
    "Evidence",
    "Narration",
    "RankResult",
    "ReadResult",
]
