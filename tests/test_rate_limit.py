"""Юнит-тесты app/services/rate_limit.py (in-memory скользящее окно)."""

import pytest
from fastapi import HTTPException

from app.services import rate_limit


def test_hit_allows_up_to_max_then_blocks():
    for i in range(3):
        assert rate_limit.hit("t", "k", max_hits=3, window_seconds=60) is True, f"попытка {i}"
    assert rate_limit.hit("t", "k", max_hits=3, window_seconds=60) is False


def test_scopes_and_keys_are_independent():
    assert rate_limit.hit("scopeA", "k", max_hits=1, window_seconds=60) is True
    assert rate_limit.hit("scopeA", "k", max_hits=1, window_seconds=60) is False
    assert rate_limit.hit("scopeB", "k", max_hits=1, window_seconds=60) is True   # другой scope
    assert rate_limit.hit("scopeA", "other", max_hits=1, window_seconds=60) is True  # другой key


def test_enforce_raises_429_past_limit():
    rate_limit.enforce("e", "k", max_hits=1, window_seconds=60)
    with pytest.raises(HTTPException) as exc:
        rate_limit.enforce("e", "k", max_hits=1, window_seconds=60)
    assert exc.value.status_code == 429
    assert exc.value.detail == "RATE_LIMITED"


def test_window_slides_old_hits_expire(monkeypatch):
    fake = {"now": 1_000.0}
    monkeypatch.setattr(rate_limit.time, "time", lambda: fake["now"])

    assert rate_limit.hit("w", "k", max_hits=1, window_seconds=10) is True
    assert rate_limit.hit("w", "k", max_hits=1, window_seconds=10) is False
    fake["now"] += 11  # окно прошло
    assert rate_limit.hit("w", "k", max_hits=1, window_seconds=10) is True


def test_reset_clears_all_counters():
    rate_limit.hit("r", "k", max_hits=1, window_seconds=60)
    assert rate_limit.hit("r", "k", max_hits=1, window_seconds=60) is False
    rate_limit.reset()
    assert rate_limit.hit("r", "k", max_hits=1, window_seconds=60) is True


class _FakeRequest:
    def __init__(self, headers: dict, client_host: str | None):
        self.headers = headers
        self.client = type("C", (), {"host": client_host})() if client_host else None


def test_client_ip_prefers_x_forwarded_for():
    req = _FakeRequest({"x-forwarded-for": "203.0.113.7, 10.0.0.1"}, client_host="10.0.0.1")
    assert rate_limit.client_ip(req) == "203.0.113.7"


def test_client_ip_falls_back_to_peer():
    assert rate_limit.client_ip(_FakeRequest({}, client_host="198.51.100.9")) == "198.51.100.9"
    assert rate_limit.client_ip(_FakeRequest({}, client_host=None)) == "unknown"
