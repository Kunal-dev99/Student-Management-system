"""Relationship signal — read message + meeting-notes history for a student-supervisor
pair, classify the trajectory (thriving / steady / drifting / strained), surface as a
soft badge for the supervisor's own eyes and (aggregated) for graduate-school directors.

Follows the AI-as-a-layer rules:
- Deterministic evidence built first — the messages and meeting notes that drove the
  classification are returned alongside the label so the supervisor can verify.
- Shape is bounded: Classify + one sentence, from the `ai/classify.py` shape.
- Falls back to keyword rules when the model is unavailable.
- Never writes state, never proposes an action. Just a signal.
"""
