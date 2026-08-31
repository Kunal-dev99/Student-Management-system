"""CB-A — Deterministic fuzzy+BoW intent router.

Zero-LLM chatbot infra. Every query is peeled through four layers:

    normaliser  ->  entity extraction  ->  time parsing  ->  bag matching

The result is a `RouteDecision` the assistant service turns into a card, chips, or
"not understood". Nothing here calls out to an external service; everything is
deterministic and unit-testable.
"""

__version__ = "0.1.0"
