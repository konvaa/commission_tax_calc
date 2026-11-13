"""The user's decisions about invoices, persisted as one JSON file.

What is stored: own IČO, confirmed payment dates, corrections from the review
dialog, manually chosen rates, remembered group profiles and cached ARES
answers. All of it is keyed by the invoice ``key`` (ISDOC UUID or file hash),
so renaming or moving the PDFs does not lose anything.

Why a JSON file in the user's data folder and not QSettings: the data is
structured (lists, nested dicts) and shared with the CLI, which has no Qt.
Why not next to the invoices: the app never writes into the user's document
folders.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from .ares import AresInfo, info_from_json, info_to_json
from .grouping import GroupProfile
from .invoice_models import EDITABLE_FIELDS, DocType, Invoice

SCHEMA_VERSION = 1


@dataclass
class InvoiceStore:
    path: Path | None = None
    my_ico: str | None = None
    payment_dates: dict[str, date] = field(default_factory=dict)
    corrections: dict[str, dict[str, Any]] = field(default_factory=dict)
    manual_rates: dict[str, str] = field(default_factory=dict)
    profiles: list[GroupProfile] = field(default_factory=list)
    ares: dict[str, AresInfo] = field(default_factory=dict)

    # ------------------------------------------------------------ load ---
    @classmethod
    def load(cls, path: Path | None) -> InvoiceStore:
        store = cls(path=path)
        if path is None or not path.is_file():
            return store
        try:
            data = json.loads(path.read_text("utf-8"))
        except (OSError, ValueError):
            return store  # a broken file must not prevent the app from starting
        if data.get("schema_version") != SCHEMA_VERSION:
            return store
        store.my_ico = data.get("my_ico")
        for key, value in data.get("payment_dates", {}).items():
            parsed = _parse_date(value)
            if parsed:
                store.payment_dates[key] = parsed
        store.corrections = {k: v for k, v in data.get("corrections", {}).items() if isinstance(v, dict)}
        store.manual_rates = {str(k): str(v) for k, v in data.get("manual_rates", {}).items()}
        store.profiles = [
            GroupProfile(
                p.get("customer_ico"), frozenset(p.get("tokens", [])), p["rate_id"], p.get("label", "")
            )
            for p in data.get("profiles", [])
            if isinstance(p, dict) and "rate_id" in p
        ]
        for ico, info in data.get("ares", {}).items():
            try:
                store.ares[ico] = info_from_json(info)
            except (KeyError, ValueError, TypeError):
                continue
        return store

    # ------------------------------------------------------------ save ---
    def save(self) -> None:
        if self.path is None:
            return
        data = {
            "schema_version": SCHEMA_VERSION,
            "my_ico": self.my_ico,
            "payment_dates": {k: v.isoformat() for k, v in sorted(self.payment_dates.items())},
            "corrections": self.corrections,
            "manual_rates": dict(sorted(self.manual_rates.items())),
            "profiles": [
                {
                    "customer_ico": p.customer_ico,
                    "tokens": sorted(p.tokens),
                    "rate_id": p.rate_id,
                    "label": p.label,
                }
                for p in self.profiles
            ],
            "ares": {ico: info_to_json(info) for ico, info in self.ares.items()},
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Write to a temporary file and atomically replace the old one, so a
        # crash or power cut mid-write never leaves a half-written file that
        # would lose all of the user's decisions.
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".invoices-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise

    # ----------------------------------------------------- corrections ---
    def set_correction(self, invoice: Invoice, values: dict[str, Any]) -> None:
        """Store reviewed values; the invoice counts as confirmed from now on."""
        serial = {}
        for name, value in values.items():
            if name not in EDITABLE_FIELDS:
                raise KeyError(name)
            if isinstance(value, date):
                serial[name] = value.isoformat()
            elif isinstance(value, (Decimal, DocType)):
                serial[name] = str(value.value if isinstance(value, DocType) else value)
            else:
                serial[name] = value
        self.corrections[invoice.key] = serial

    def apply(self, invoice: Invoice) -> Invoice:
        stored = self.corrections.get(invoice.key)
        if stored is None:
            return invoice
        changes: dict[str, Any] = {"confirmed": True}
        for name, value in stored.items():
            kind = EDITABLE_FIELDS.get(name)
            if kind is None:
                continue
            changes[name] = _convert(value, kind)
        return invoice.with_changes(**changes)


def _convert(value: Any, kind: type) -> Any:
    if value is None:
        return None
    if kind is date:
        return _parse_date(value)
    if kind is Decimal:
        try:
            return Decimal(str(value))
        except InvalidOperation:
            return None
    if kind is DocType:
        try:
            return DocType(value)
        except ValueError:
            return DocType.INVOICE
    if kind is bool:
        return bool(value)
    return str(value)


def _parse_date(value: Any) -> date | None:
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None
