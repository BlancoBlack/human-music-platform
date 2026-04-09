"""Tests for in-memory POST /stream rate limiting (routes module)."""

import logging
import unittest
from unittest.mock import MagicMock

from fastapi import HTTPException

from app.api import routes


def _mock_request(path: str = "/stream", host: str = "203.0.113.9") -> MagicMock:
    req = MagicMock()
    req.url.path = path
    req.headers.get = MagicMock(return_value=None)
    req.client = MagicMock()
    req.client.host = host
    return req


def _clear_rate_limit_store() -> None:
    with routes.rate_limit_lock:
        routes._stream_rate_limit_store.clear()


class StreamRateLimitTests(unittest.TestCase):
    def setUp(self) -> None:
        _clear_rate_limit_store()

    def tearDown(self) -> None:
        _clear_rate_limit_store()

    def test_five_requests_allowed_burst_window(self) -> None:
        req = _mock_request()
        for _ in range(5):
            routes._enforce_stream_rate_limit(req, user_id=42)

    def test_sixth_request_burst_429(self) -> None:
        req = _mock_request()
        for _ in range(5):
            routes._enforce_stream_rate_limit(req, user_id=7)
        with self.assertRaises(HTTPException) as ctx:
            routes._enforce_stream_rate_limit(req, user_id=7)
        exc = ctx.exception
        self.assertEqual(exc.status_code, 429)
        self.assertEqual(
            exc.detail,
            {"status": "rate_limited", "reason": "burst_rate_limited"},
        )
        self.assertIn("Retry-After", exc.headers or {})

    def test_ten_rapid_calls_some_429(self) -> None:
        req = _mock_request()
        statuses = []
        for _ in range(10):
            try:
                routes._enforce_stream_rate_limit(req, user_id=99)
                statuses.append(200)
            except HTTPException as e:
                self.assertEqual(e.status_code, 429)
                statuses.append(429)
        self.assertIn(200, statuses)
        self.assertIn(429, statuses)

    def test_rate_limit_exceeded_logged(self) -> None:
        log = logging.getLogger(routes.__name__)
        handler = logging.Handler()
        records: list[logging.LogRecord] = []

        def emit(record: logging.LogRecord) -> None:
            records.append(record)

        handler.emit = emit  # type: ignore[method-assign]
        log.addHandler(handler)
        log.setLevel(logging.WARNING)
        try:
            req = _mock_request()
            for _ in range(5):
                routes._enforce_stream_rate_limit(req, user_id=1)
            with self.assertRaises(HTTPException):
                routes._enforce_stream_rate_limit(req, user_id=1)
        finally:
            log.removeHandler(handler)

        msgs = [r.getMessage() for r in records]
        self.assertIn("rate_limit_exceeded", msgs)

    def test_skips_dev_and_admin_paths(self) -> None:
        for path in ("/dev/stream", "/admin/foo"):
            req = _mock_request(path=path)
            for _ in range(20):
                routes._enforce_stream_rate_limit(req, user_id=1)


if __name__ == "__main__":
    unittest.main()
