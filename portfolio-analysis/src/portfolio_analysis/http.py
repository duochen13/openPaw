"""Serial, resumable HTTP: reserve quota before every attempt; cache valid JSON.

Request identities exclude credentials. Immutable response objects are addressed
by content hash; small request manifests point to the latest successful object.
Mutable indexes use max_age; historical windows may be cached indefinitely.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import requests

_SECRET_PARAMS = frozenset({"apikey", "api_key", "token", "key"})


class QuotaExhausted(RuntimeError):
    """A local daily budget or a provider quota is exhausted."""


class ProviderError(RuntimeError):
    """A provider could not supply usable data; never an empty success."""


def atomic_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=path.parent, delete=False) as handle:
            temporary = handle.name
            json.dump(payload, handle, indent=2, sort_keys=True, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


@contextmanager
def file_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def cache_key(url: str) -> str:
    parts = urlsplit(url)
    if parts.username or parts.password:
        raise ValueError("URL credentials are unsupported")
    query = sorted(
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if k.lower() not in _SECRET_PARAMS
    )
    canonical = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), ""))
    return hashlib.sha256(canonical.encode()).hexdigest()


class RateLimitLedger:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)

    @staticmethod
    def _today() -> str:
        return datetime.now(UTC).date().isoformat()

    def _load(self) -> dict[str, dict[str, int]]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text())
            if not isinstance(data, dict):
                raise ValueError
            for provider, days in data.items():
                if not isinstance(provider, str) or not isinstance(days, dict):
                    raise ValueError
                for day, count in days.items():
                    if datetime.strptime(day, "%Y-%m-%d").strftime("%Y-%m-%d") != day:
                        raise ValueError
                    if type(count) is not int or count < 0:
                        raise ValueError
        except (ValueError, TypeError) as exc:
            raise ValueError("rate-limit ledger is invalid; refusing to reset spend") from exc
        return data

    def spent_today(self, provider: str) -> int:
        return self._load().get(provider, {}).get(self._today(), 0)

    def _blocked(self) -> dict[str, str]:
        path = self.path.with_suffix(".blocked.json")
        if not path.exists():
            return {}
        data = json.loads(path.read_text())
        if not isinstance(data, dict) or any(
            not isinstance(k, str) or not isinstance(v, str) for k, v in data.items()
        ):
            raise ValueError("invalid provider block ledger")
        for day in data.values():
            if datetime.strptime(day, "%Y-%m-%d").strftime("%Y-%m-%d") != day:
                raise ValueError("invalid provider block ledger date")
        return data

    def block_today(self, provider: str) -> None:
        with file_lock(self.path.with_suffix(".lock")):
            blocked = self._blocked()
            blocked[provider] = self._today()
            atomic_json(self.path.with_suffix(".blocked.json"), blocked)

    def reserve(self, provider: str, daily_limit: int | None) -> None:
        with file_lock(self.path.with_suffix(".lock")):
            data = self._load()
            day = self._today()
            if self._blocked().get(provider) == day:
                raise QuotaExhausted(f"{provider}: provider quota refused today; retry after reset")
            count = data.get(provider, {}).get(day, 0)
            if daily_limit is not None and count >= daily_limit:
                raise QuotaExhausted(f"{provider}: daily budget of {daily_limit} requests spent")
            data.setdefault(provider, {})[day] = count + 1
            atomic_json(self.path, data)

    def record(self, provider: str) -> None:
        self.reserve(provider, None)


def _http_get_json(url: str) -> dict[str, Any]:
    agent = os.environ.get("SEC_USER_AGENT", "portfolio-analysis/0.1 research")
    response = requests.get(url, headers={"User-Agent": agent}, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ProviderError("expected a JSON object")
    return payload


class CachedHttp:
    def __init__(
        self,
        cache_dir: Path,
        *,
        ledger: RateLimitLedger,
        fetch: Callable[[str], dict[str, Any]] = _http_get_json,
        sleep: Callable[[float], None] = time.sleep,
        attempts: int = 4,
    ) -> None:
        if attempts < 1:
            raise ValueError("attempts must be positive")
        self.cache_dir, self.ledger = Path(cache_dir), ledger
        self._fetch, self._sleep, self._attempts = fetch, sleep, attempts

    def get_json(
        self,
        provider: str,
        url: str,
        *,
        daily_limit: int | None,
        max_age: float | None = None,
    ) -> dict[str, Any]:
        if not provider or any(c not in "abcdefghijklmnopqrstuvwxyz_0123456789" for c in provider):
            raise ValueError("invalid provider name")
        directory = self.cache_dir / provider
        manifest = directory / "requests" / f"{cache_key(url)}.json"
        # Also serializes separate collectors sharing this cache. Recheck cache
        # after acquiring the lock to avoid duplicate requests on contention.
        with file_lock(directory / "fetch.lock"):
            if manifest.exists():
                entry = json.loads(manifest.read_text())
                if max_age is None or time.time() - entry["fetched_at"] < max_age:
                    digest = entry["sha256"]
                    if (
                        not isinstance(digest, str)
                        or len(digest) != 64
                        or any(c not in "0123456789abcdef" for c in digest)
                    ):
                        raise ValueError("invalid HTTP cache manifest")
                    raw = (directory / "objects" / f"{digest}.json").read_text()
                    if hashlib.sha256(raw.encode()).hexdigest() != digest:
                        raise ValueError("HTTP cache content hash mismatch")
                    cached = json.loads(raw)
                    if not isinstance(cached, dict):
                        raise ValueError("invalid cached response")
                    return cached

            for attempt in range(self._attempts):
                self.ledger.reserve(provider, daily_limit)
                # Keep SEC traffic below its published 10 requests/sec ceiling.
                if provider == "edgar":
                    self._sleep(0.15)
                try:
                    payload = self._fetch(url)
                except requests.RequestException as exc:
                    status = exc.response.status_code if exc.response is not None else None
                    if status == 429:
                        if daily_limit is not None:
                            self.ledger.block_today(provider)
                        raise QuotaExhausted(f"{provider}: HTTP 429; retry later") from None
                    transient = status is None or status in {408, 500, 502, 503, 504}
                    if not transient or attempt == self._attempts - 1:
                        raise ProviderError(f"{provider}: request failed (HTTP {status})") from None
                    self._sleep(float(2**attempt))
                    continue
                except ValueError:
                    raise ProviderError(f"{provider}: invalid JSON response") from None
                break

            if not isinstance(payload, dict):
                raise ProviderError(f"{provider}: expected a JSON object")
            if provider == "alphavantage":
                note = str(payload.get("Information") or payload.get("Note") or "")
                if note:
                    if any(
                        term in note.lower()
                        for term in ("rate limit", "call frequency", "requests per", "calls per")
                    ):
                        self.ledger.block_today(provider)
                        raise QuotaExhausted(f"{provider}: provider refused due to quota")
                    raise ProviderError(f"{provider}: provider refused the request")
                if "Error Message" in payload:
                    raise ProviderError(f"{provider}: invalid request or credentials")

            # A vendor can echo a key in a response, including in URLs. Refuse
            # persistence rather than changing the evidence to hide it.
            raw = json.dumps(payload, sort_keys=True, allow_nan=False)
            secrets = [
                v for k, v in parse_qsl(urlsplit(url).query) if k.lower() in _SECRET_PARAMS and v
            ]
            if any(secret in raw for secret in secrets):
                raise ProviderError(f"{provider}: response echoed credentials; not cached")
            digest = hashlib.sha256(raw.encode()).hexdigest()
            target = directory / "objects" / f"{digest}.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            # Objects are written atomically as exact bytes used by the hash.
            with tempfile.NamedTemporaryFile(mode="w", dir=target.parent, delete=False) as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
                temporary = handle.name
            os.replace(temporary, target)
            atomic_json(manifest, {"sha256": digest, "fetched_at": time.time()})
            return payload
