"""Lookup of trades in ARES (Administrativní registr ekonomických subjektů).

ARES is the public register of the Ministry of Finance with a free REST API
(no key, no login). The trade-licensing part (RŽP) lists every trade of a
sole trader; from their names the app can tell whether they are craft trades
(80 %) or other trades (60 %) - see ``TradeClassification`` in ``rules.py``.

Only the IČO is sent. Results are cached by the caller, so ARES is asked at
most once per IČO.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from .ico import is_valid, normalize
from .rules import RuleSet

BASE_URL = "https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/"
_MAX_BYTES = 2 * 1024 * 1024


class AresError(RuntimeError):
    """ARES could not be reached or returned something unexpected."""


@dataclass(frozen=True)
class Trade:
    subject: str  # předmět podnikání, e.g. "Zednictví"
    kind_code: str | None
    valid_from: date | None
    valid_to: date | None

    def active_on(self, day: date) -> bool:
        started = self.valid_from is None or self.valid_from <= day
        not_ended = self.valid_to is None or self.valid_to >= day
        return started and not_ended


@dataclass(frozen=True)
class AresInfo:
    ico: str
    name: str | None
    trades: tuple[Trade, ...]
    fetched: date

    def active_trades(self, day: date) -> list[Trade]:
        return [t for t in self.trades if t.active_on(day)]


def parse_rzp(data: Any, ico: str, fetched: date) -> AresInfo:
    """Parse the ``ekonomicke-subjekty-rzp/{ico}`` response.

    Defensive by design: unknown or missing keys are skipped, not fatal, so a
    small change of the public API degrades to "no suggestion" instead of an
    error.
    """
    if not isinstance(data, dict):
        raise AresError("unexpected ARES response")
    records = data.get("zaznamy") or []
    # Prefer the primary record; ARES may also return historical ones.
    records = sorted(records, key=lambda r: not r.get("primarniZaznam", False))
    name = None
    trades: list[Trade] = []
    for record in records[:1]:
        name = record.get("obchodniJmeno")
        for item in record.get("zivnosti") or []:
            subject = item.get("predmetPodnikani")
            if not subject:
                continue
            trades.append(
                Trade(
                    subject=" ".join(str(subject).split()),
                    kind_code=item.get("druhZivnosti"),
                    valid_from=_date(item.get("datumVzniku")),
                    valid_to=_date(item.get("datumZaniku")),
                )
            )
    return AresInfo(ico, name, tuple(trades), fetched)


def info_to_json(info: AresInfo) -> dict:
    """Serializable form for the settings cache."""
    return {
        "ico": info.ico,
        "name": info.name,
        "fetched": info.fetched.isoformat(),
        "trades": [
            {
                "subject": t.subject,
                "kind_code": t.kind_code,
                "valid_from": t.valid_from.isoformat() if t.valid_from else None,
                "valid_to": t.valid_to.isoformat() if t.valid_to else None,
            }
            for t in info.trades
        ],
    }


def info_from_json(data: dict) -> AresInfo:
    return AresInfo(
        ico=data["ico"],
        name=data.get("name"),
        fetched=date.fromisoformat(data["fetched"]),
        trades=tuple(
            Trade(t["subject"], t.get("kind_code"), _date(t.get("valid_from")), _date(t.get("valid_to")))
            for t in data.get("trades", [])
        ),
    )


def suggested_rate_ids(info: AresInfo, rules: RuleSet, day: date) -> set[str]:
    """Rates the active trades lead to. One element = the answer is clear."""
    if rules.trades is None:
        return set()
    return {rules.trades.rate_id_for_trade(t.subject) for t in info.active_trades(day)}


# fetch(url) -> bytes; ``None`` means 404 (no record). Injectable for tests.
Fetcher = Callable[[str], bytes | None]


def _default_fetch(url: str, timeout: float = 10.0) -> bytes | None:
    request = urllib.request.Request(
        url, headers={"Accept": "application/json", "User-Agent": "commission-tax-calc"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 (fixed https URL)
            payload = response.read(_MAX_BYTES + 1)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None  # not in the trade register (e.g. no trade, only "jiné podnikání")
        raise AresError(f"ARES returned HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise AresError(f"ARES is not reachable: {exc}") from exc
    if len(payload) > _MAX_BYTES:
        raise AresError("ARES response is too large")
    return payload


def lookup(ico: str, fetch: Fetcher | None = None, today: date | None = None) -> AresInfo:
    normalized = normalize(ico)
    if normalized is None or not is_valid(normalized):
        # Never send an invalid (possibly misread) IČO to a public service.
        raise AresError(f"invalid IČO {ico!r}")
    raw = (fetch or _default_fetch)(f"{BASE_URL}ekonomicke-subjekty-rzp/{normalized}")
    today = today or date.today()
    if raw is None:
        return AresInfo(normalized, None, (), today)
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise AresError("ARES returned invalid JSON") from exc
    return parse_rzp(data, normalized, today)


def _date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None
