"""Background worker entrypoint placeholder (arch §9.3, §19.1).

One image runs both API and workers, selected by the container command. The concrete
Celery/ARQ app and periodic schedules land in Phase 2 (BE-2.2).
"""
from __future__ import annotations


def main() -> None:  # pragma: no cover - wired in Phase 2
    raise NotImplementedError("Worker tier is implemented in Phase 2 (BE-2.2).")
