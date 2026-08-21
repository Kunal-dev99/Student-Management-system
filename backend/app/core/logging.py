"""Structured JSON logging (arch §18). One line per request via middleware."""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Merge structured extras attached via logger.info(..., extra={...}).
        for key, value in getattr(record, "__dict__", {}).items():
            if key in _RESERVED or key.startswith("_"):
                continue
            if key not in payload:
                payload[key] = value
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


_RESERVED = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()) | {
    "message",
    "asctime",
}


def configure_logging(level: str = "info") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
