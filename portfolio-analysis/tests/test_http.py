import json

import pytest
import requests

from portfolio_analysis.http import (
    CachedHttp,
    ProviderError,
    QuotaExhausted,
    RateLimitLedger,
    cache_key,
)


def client(tmp_path, fetch, **kw):
    return CachedHttp(
        tmp_path,
        ledger=RateLimitLedger(tmp_path / "quota.json"),
        fetch=fetch,
        sleep=lambda _: None,
        **kw,
    )


def test_rotating_keys_and_reordered_queries_reuse_cache(tmp_path):
    calls = []
    http = client(tmp_path, lambda url: calls.append(url) or {"feed": []})
    a = "https://x?q=META&apikey=SECRET1"
    b = "https://x?apikey=SECRET2&q=META"
    assert cache_key(a) == cache_key(b)
    http.get_json("alphavantage", a, daily_limit=1)
    restarted = client(tmp_path, lambda url: pytest.fail("cache miss"))
    assert restarted.get_json("alphavantage", b, daily_limit=1) == {"feed": []}
    assert len(calls) == 1
    assert restarted.ledger.spent_today("alphavantage") == 1
    assert "SECRET" not in "".join(p.read_text() for p in tmp_path.rglob("*") if p.is_file())


def test_every_retry_reserves_quota_and_stops_before_overspend(tmp_path):
    calls = []

    def timeout(url):
        calls.append(url)
        raise requests.Timeout("sensitive URL")

    http = client(tmp_path, timeout)
    with pytest.raises(QuotaExhausted):
        http.get_json("alphavantage", "https://x", daily_limit=2)
    assert len(calls) == 2
    assert RateLimitLedger(tmp_path / "quota.json").spent_today("alphavantage") == 2


def test_process_interrupt_keeps_attempt_reserved(tmp_path):
    def interrupt(url):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        client(tmp_path, interrupt).get_json("av", "https://x", daily_limit=1)
    with pytest.raises(QuotaExhausted):
        client(tmp_path, lambda _: pytest.fail("overspend")).get_json(
            "av", "https://x", daily_limit=1
        )


def test_transient_failure_recovers_without_caching_error(tmp_path):
    calls = []

    def fetch(url):
        calls.append(url)
        if len(calls) == 1:
            response = requests.Response()
            response.status_code = 502
            raise requests.HTTPError(response=response)
        return {"ok": True}

    http = client(tmp_path, fetch)
    assert http.get_json("av", "https://x", daily_limit=3) == {"ok": True}
    assert http.ledger.spent_today("av") == 2


@pytest.mark.parametrize(
    "payload,error",
    [
        ({"Information": "rate limit 25 requests per day"}, QuotaExhausted),
        ({"Information": "invalid API key SECRET"}, ProviderError),
        ({"Error Message": "invalid symbol"}, ProviderError),
        ({"feed": [], "echo": "SECRET"}, ProviderError),
    ],
)
def test_refusals_and_echoed_secrets_never_reach_cache(tmp_path, payload, error):
    with pytest.raises(error) as caught:
        client(tmp_path, lambda _: payload).get_json(
            "alphavantage", "https://x?apikey=SECRET", daily_limit=25
        )
    assert "SECRET" not in str(caught.value)
    assert not list(tmp_path.glob("alphavantage/objects/*.json"))


@pytest.mark.parametrize(
    "payload", ["{bad", "[]", '{"av": {"2024-01-01": -1}}', '{"av": {"2024-01-01": true}}']
)
def test_corrupt_ledger_does_not_reset_quota(tmp_path, payload):
    path = tmp_path / "quota.json"
    path.write_text(payload)
    with pytest.raises(ValueError, match="ledger"):
        RateLimitLedger(path).record("av")


def test_daily_rollover_preserves_old_spend(tmp_path, monkeypatch):
    ledger = RateLimitLedger(tmp_path / "quota.json")
    monkeypatch.setattr(ledger, "_today", lambda: "2024-01-01")
    ledger.reserve("av", 1)
    monkeypatch.setattr(ledger, "_today", lambda: "2024-01-02")
    ledger.reserve("av", 1)
    assert json.loads(ledger.path.read_text())["av"] == {"2024-01-01": 1, "2024-01-02": 1}


def test_mutable_response_expires_but_old_content_remains(tmp_path):
    calls = []
    http = client(tmp_path, lambda _: calls.append(1) or {"revision": len(calls)})
    http.get_json("edgar", "https://x", daily_limit=None)
    assert http.get_json("edgar", "https://x", daily_limit=None, max_age=0) == {"revision": 2}
    assert len(list(tmp_path.glob("edgar/objects/*.json"))) == 2


def test_credential_bearing_exception_is_sanitized(tmp_path):
    def fail(url):
        raise requests.ConnectionError("https://x?apikey=SECRET")

    with pytest.raises(ProviderError) as caught:
        client(tmp_path, fail, attempts=1).get_json("av", "https://x?apikey=SECRET", daily_limit=25)
    assert "SECRET" not in str(caught.value)


def test_provider_quota_refusal_blocks_restarts_until_next_day(tmp_path, monkeypatch):
    calls = []
    http = client(tmp_path, lambda _: calls.append(1) or {"Information": "25 requests per day"})
    with pytest.raises(QuotaExhausted):
        http.get_json("alphavantage", "https://x", daily_limit=25)
    restarted = client(tmp_path, lambda _: pytest.fail("provider already refused today"))
    with pytest.raises(QuotaExhausted):
        restarted.get_json("alphavantage", "https://x", daily_limit=25)
    assert calls == [1]
    assert restarted.ledger.spent_today("alphavantage") == 1
    monkeypatch.setattr(RateLimitLedger, "_today", staticmethod(lambda: "2099-01-01"))
    assert client(tmp_path, lambda _: {"ok": True}).get_json(
        "alphavantage", "https://x", daily_limit=25
    ) == {"ok": True}
