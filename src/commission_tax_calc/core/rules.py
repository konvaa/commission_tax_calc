"""Flat-rate expense rules ("paušální výdaje", § 7 odst. 7 ZDP) loaded from JSON.

Why rules are *data* and not code: the percentages and caps change with
legislation, not with the program. Keeping them in versioned JSON files means

* a law change is a one-file commit, reviewable by anyone (no Python needed),
* installed apps can download the new file from GitHub without a new release,
* every tax year keeps its own rules, so recomputing 2024 uses 2024 rules.

Three sources are merged, the highest ``revision`` per year wins:
bundled files (shipped with the app) < cached downloads < nothing else.
Downloaded files are validated by the same parser as bundled ones before they
are cached, so a broken or malicious file can never replace working rules.
"""

from __future__ import annotations

import json
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from importlib import resources
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
DEFAULT_REMOTE_BASE = (
    "https://raw.githubusercontent.com/konvaa/commission_tax_calc/main/src/commission_tax_calc/rules/"
)
_MAX_DOWNLOAD_BYTES = 256 * 1024  # rules are a few KB; anything bigger is suspicious


class RulesError(ValueError):
    """A rules file is malformed."""


@dataclass(frozen=True)
class Source:
    label: dict[str, str]
    url: str


@dataclass(frozen=True)
class RateCategory:
    id: str
    percent: Decimal
    max_expenses: Decimal
    legal_ref: str
    name: dict[str, str]
    description: dict[str, str]
    examples: dict[str, tuple[str, ...]]


@dataclass(frozen=True)
class ActivityMapping:
    match: str  # case-insensitive substring of the statement's activity heading
    rate_id: str


@dataclass(frozen=True)
class TradeClassification:
    """How trades from the Trade Licensing Register (RŽP) map to rates.

    Only *craft* trades (annex 1 of the Trade Licensing Act) get 80 %; every
    other trade - unqualified, qualified, licensed - gets 60 %. Listing the 41
    craft trades is therefore enough to classify any trade by its name, which
    is more robust than relying on ARES code values that are not documented.
    """

    craft_rate_id: str
    default_rate_id: str
    craft_trades: frozenset[str]  # casefolded names
    sources: tuple[Source, ...] = ()

    def rate_id_for_trade(self, subject: str) -> str:
        name = " ".join(subject.split()).casefold()
        return self.craft_rate_id if name in self.craft_trades else self.default_rate_id


@dataclass(frozen=True)
class RuleSet:
    tax_year: int
    revision: int
    updated: str
    income_cap: Decimal
    rates: tuple[RateCategory, ...]
    mappings: tuple[ActivityMapping, ...]
    sources: tuple[Source, ...]
    note: dict[str, str]
    origin: str = "bundled"  # "bundled" | "cache" - shown in the rules dialog
    # Optional (added in revision 2). Older apps ignore the key, so adding it
    # did not require a new schema_version.
    trades: TradeClassification | None = None

    def rate(self, rate_id: str) -> RateCategory | None:
        return next((r for r in self.rates if r.id == rate_id), None)

    def rate_for_activity(self, category: str) -> RateCategory | None:
        """First mapping whose ``match`` occurs in the heading wins.

        Order matters: "Není živností" must be tested before any generic
        "živnost" pattern, which is why mappings are an ordered list in JSON.
        """
        text = category.casefold()
        for mapping in self.mappings:
            if mapping.match.casefold() in text:
                return self.rate(mapping.rate_id)
        return None


def text(localized: dict[str, str], lang: str) -> str:
    """Pick a translation, falling back to Czech, then to anything."""
    return localized.get(lang) or localized.get("cs") or next(iter(localized.values()), "")


# ----------------------------------------------------------------- parsing ---


def parse_rules(data: Any, origin: str = "bundled") -> RuleSet:
    """Validate a decoded JSON document and build a :class:`RuleSet`."""
    try:
        if data["schema_version"] != SCHEMA_VERSION:
            raise RulesError(f"unsupported schema_version {data['schema_version']!r}")
        rates = tuple(
            RateCategory(
                id=str(r["id"]),
                percent=_decimal(r["percent"], 0, 100),
                max_expenses=_decimal(r["max_expenses"], 0),
                legal_ref=str(r.get("legal_ref", "")),
                name=_localized(r["name"]),
                description=_localized(r.get("description", {})),
                examples={k: tuple(map(str, v)) for k, v in r.get("examples", {}).items()},
            )
            for r in data["rates"]
        )
        ids = {r.id for r in rates}
        if len(ids) != len(rates):
            raise RulesError("duplicate rate id")
        mappings = tuple(
            ActivityMapping(str(m["match"]), str(m["rate_id"])) for m in data["activity_mapping"]
        )
        unknown = {m.rate_id for m in mappings} - ids
        if unknown:
            raise RulesError(f"mapping refers to unknown rate(s): {sorted(unknown)}")
        sources = tuple(Source(_localized(s["label"]), _https(s["url"])) for s in data["sources"])
        trades = _trade_classification(data.get("trade_classification"), ids)
        return RuleSet(
            trades=trades,
            tax_year=int(data["tax_year"]),
            revision=int(data["revision"]),
            updated=str(data.get("updated", "")),
            income_cap=_decimal(data["income_cap"], 0),
            rates=rates,
            mappings=mappings,
            sources=sources,
            note=_localized(data.get("note", {})),
            origin=origin,
        )
    except RulesError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise RulesError(f"invalid rules file: {exc!r}") from exc


def _trade_classification(data: Any, rate_ids: set[str]) -> TradeClassification | None:
    if data is None:
        return None
    if not isinstance(data, dict):
        raise RulesError("trade_classification must be an object")
    craft, default = str(data["craft_rate_id"]), str(data["default_rate_id"])
    if not {craft, default} <= rate_ids:
        raise RulesError("trade_classification refers to an unknown rate")
    names = frozenset(" ".join(str(n).split()).casefold() for n in data.get("craft_trades", []))
    sources = tuple(Source(_localized(s["label"]), _https(s["url"])) for s in data.get("sources", []))
    return TradeClassification(craft, default, names, sources)


def _decimal(value: Any, minimum: float, maximum: float | None = None) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        raise RulesError(f"not a number: {value!r}")
    try:
        number = Decimal(str(value))
    except InvalidOperation as exc:
        raise RulesError(f"not a number: {value!r}") from exc
    if not number.is_finite() or number < minimum or (maximum is not None and number > maximum):
        raise RulesError(f"out of range: {value!r}")
    return number


def _localized(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        raise RulesError(f"expected a {{lang: text}} object, got {value!r}")
    return {str(k): str(v) for k, v in value.items()}


def _https(url: Any) -> str:
    # Links are opened in the user's browser - only allow https.
    if not isinstance(url, str) or not url.startswith("https://"):
        raise RulesError(f"source URL must be https: {url!r}")
    return url


# -------------------------------------------------------------- repository ---

# fetch(url) -> bytes; injectable so tests never touch the network.
Fetcher = Callable[[str], bytes]


def _default_fetch(url: str, timeout: float = 10.0) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "commission-tax-calc"})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 (https only)
        payload = response.read(_MAX_DOWNLOAD_BYTES + 1)
    if len(payload) > _MAX_DOWNLOAD_BYTES:
        raise RulesError("downloaded rules file is too large")
    return payload


@dataclass
class UpdateResult:
    updated_years: list[int]
    checked_years: list[int]


class RulesRepository:
    def __init__(
        self,
        cache_dir: Path | None,
        remote_base: str = DEFAULT_REMOTE_BASE,
        fetch: Fetcher | None = None,
    ) -> None:
        self.cache_dir = cache_dir
        self.remote_base = remote_base
        self._fetch = fetch or _default_fetch
        self._rules: dict[int, RuleSet] = {}
        self.reload()

    # -- loading ---------------------------------------------------------
    def reload(self) -> None:
        rules = dict(_load_bundled())
        for year, cached in self._load_cache().items():
            if year not in rules or cached.revision > rules[year].revision:
                rules[year] = cached
        self._rules = rules

    def _load_cache(self) -> dict[int, RuleSet]:
        result: dict[int, RuleSet] = {}
        if not self.cache_dir or not self.cache_dir.is_dir():
            return result
        for path in self.cache_dir.glob("[0-9][0-9][0-9][0-9].json"):
            try:
                rules = parse_rules(json.loads(path.read_text("utf-8")), origin="cache")
            except (OSError, ValueError):
                continue  # a corrupt cache file must not break the app
            result[rules.tax_year] = rules
        return result

    # -- queries ---------------------------------------------------------
    @property
    def years(self) -> list[int]:
        return sorted(self._rules)

    def get(self, year: int) -> tuple[RuleSet | None, bool]:
        """Rules for ``year`` and whether they are an exact match.

        For a year without rules (e.g. a new year before an update), the
        closest earlier year is returned with ``exact=False`` so the GUI can
        warn instead of silently using possibly outdated percentages.
        """
        if year in self._rules:
            return self._rules[year], True
        earlier = [y for y in self._rules if y < year]
        candidates = earlier or list(self._rules)
        if not candidates:
            return None, False
        fallback = max(earlier) if earlier else min(candidates)
        return self._rules[fallback], False

    # -- updating --------------------------------------------------------
    def update_from_remote(self) -> UpdateResult:
        """Download newer rule revisions listed in the remote ``index.json``.

        Raises ``OSError`` / ``RulesError`` on network or format problems; the
        caller decides how to present them.
        """
        index = json.loads(self._fetch(self.remote_base + "index.json").decode("utf-8"))
        if index.get("schema_version") != SCHEMA_VERSION:
            raise RulesError("unsupported remote index")
        updated, checked = [], []
        for year_text, revision in index["years"].items():
            year = int(year_text)
            checked.append(year)
            current = self._rules.get(year)
            if current is not None and current.revision >= int(revision):
                continue
            raw = self._fetch(f"{self.remote_base}{year}.json")
            rules = parse_rules(json.loads(raw.decode("utf-8")), origin="cache")
            if rules.tax_year != year:
                raise RulesError(f"{year}.json declares tax_year {rules.tax_year}")
            if self.cache_dir:
                self.cache_dir.mkdir(parents=True, exist_ok=True)
                (self.cache_dir / f"{year}.json").write_bytes(raw)
            updated.append(year)
        self.reload()
        return UpdateResult(sorted(updated), sorted(checked))


def _load_bundled() -> dict[int, RuleSet]:
    result = {}
    folder = resources.files("commission_tax_calc") / "rules"
    for entry in folder.iterdir():
        name = entry.name
        if name.endswith(".json") and name[:4].isdigit():
            rules = parse_rules(json.loads(entry.read_text("utf-8")), origin="bundled")
            result[rules.tax_year] = rules
    return result
