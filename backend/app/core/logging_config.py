"""
JSON logging for the root logger so ``logger.info("event", extra={...})`` fields are visible.

Configure early (before other imports) from ``app.main`` or any entrypoint.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Mapping

# Attributes present on every LogRecord; anything else came from ``extra=``.
_STANDARD_LOGRECORD_KEYS = frozenset(
    logging.LogRecord(
        name="",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="",
        args=(),
        exc_info=None,
    ).__dict__.keys()
) | frozenset({"taskName"})


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Mapping):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", errors="replace")
    return str(value)


class JsonFormatter(logging.Formatter):
    """One JSON object per line: timestamp, level, message, logger, extras, optional exception."""

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat()
        payload: dict[str, Any] = {
            "timestamp": ts,
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        for key, raw in record.__dict__.items():
            if key in _STANDARD_LOGRECORD_KEYS:
                continue
            if key == "message":
                continue
            try:
                payload[key] = _json_safe(raw)
            except Exception:
                payload[key] = str(raw)

        return json.dumps(payload, ensure_ascii=False)


def setup_logging() -> None:
    """
    Attach a single JSON StreamHandler to the root logger (stderr).

    Idempotent: if the root logger already has a JsonFormatter handler, no-op.
    """
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    for h in root.handlers:
        if isinstance(h.formatter, JsonFormatter):
            root.setLevel(level)
            h.setLevel(level)
            return

    root.setLevel(level)
    for h in root.handlers[:]:
        root.removeHandler(h)

    handler = logging.StreamHandler(sys.stderr)
    handler.setLevel(level)
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
