"""Grouping of similar invoices, so one flat-rate choice covers many invoices.

Why word-set similarity and not machine learning: a few hundred invoices per
year are far too few to train anything, a clustering library (scikit-learn)
would add tens of MB to the .exe, and the user must be able to see *why* two
invoices ended up together. Comparing the sets of meaningful words (Jaccard
index) is instant, needs no dependency and every group can be labelled with
its typical words.

Rules:
* numbers, dates, parcel numbers and short words are ignored, so
  "IP-12-8035791 Lužná, č.parc. 3424 NNV" and "IV-12-8032481 Lhota,
  č.parc. 217, kNN" share the words that describe the *kind* of work;
* same customer + moderately similar texts -> same group,
* very similar texts -> same group even for different customers.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field

from .invoice_models import Invoice

SAME_CUSTOMER_THRESHOLD = 0.15
ANY_CUSTOMER_THRESHOLD = 0.5

# Words present on almost every Czech invoice - they say nothing about the work.
_STOPWORDS = frozenset(
    [
        "a",
        "aj",
        "ale",
        "až",
        "bez",
        "by",
        "být",
        "dle",
        "do",
        "faktura",
        "fakturujeme",
        "fakturace",
        "celkem",
        "cena",
        "dph",
        "ev",
        "hod",
        "jako",
        "je",
        "jsou",
        "k",
        "ks",
        "kč",
        "ke",
        "na",
        "nad",
        "o",
        "od",
        "ode",
        "objednávka",
        "objednávky",
        "objednávce",
        "po",
        "pod",
        "podle",
        "pro",
        "práce",
        "s",
        "se",
        "smlouva",
        "smlouvy",
        "služby",
        "služba",
        "částka",
        "č",
        "čj",
        "ks",
        "m",
        "mj",
        "množství",
        "tj",
        "u",
        "v",
        "ve",
        "vám",
        "vaší",
        "vašeho",
        "za",
        "zboží",
        "že",
        "the",
        "of",
        "and",
        "for",
    ]
)


def tokens(text: str) -> frozenset[str]:
    words = re.split(r"[\W_]+", text.casefold())
    return frozenset(
        w for w in words if len(w) >= 2 and not any(ch.isdigit() for ch in w) and w not in _STOPWORDS
    )


def jaccard(a: frozenset[str], b: frozenset[str]) -> float:
    if not a and not b:
        return 1.0  # two invoices without any description are alike
    return len(a & b) / len(a | b)


def similar(a_tokens, a_customer, b_tokens, b_customer) -> bool:
    score = jaccard(a_tokens, b_tokens)
    if a_customer and a_customer == b_customer and score >= SAME_CUSTOMER_THRESHOLD:
        return True
    return score >= ANY_CUSTOMER_THRESHOLD


@dataclass(frozen=True)
class GroupProfile:
    """A remembered group: "invoices like these get rate X".

    Stored in the user's settings; new invoices similar to a profile get its
    rate automatically (and are flagged so the user can check them).
    """

    customer_ico: str | None
    tokens: frozenset[str]
    rate_id: str
    label: str = ""

    def matches(self, invoice: Invoice) -> float | None:
        invoice_tokens = tokens(invoice.description_text)
        if similar(invoice_tokens, invoice.customer_ico, self.tokens, self.customer_ico):
            return jaccard(invoice_tokens, self.tokens)
        return None


@dataclass
class InvoiceGroup:
    id: str
    invoices: list[Invoice] = field(default_factory=list)
    customer_ico: str | None = None
    customer_name: str | None = None
    top_words: tuple[str, ...] = ()

    @property
    def label(self) -> str:
        who = self.customer_name or self.customer_ico or "?"
        words = ", ".join(self.top_words)
        return f"{who} – {words}" if words else who

    @property
    def token_union(self) -> frozenset[str]:
        return frozenset().union(*(tokens(i.description_text) for i in self.invoices))


def best_profile(invoice: Invoice, profiles: Iterable[GroupProfile]) -> GroupProfile | None:
    scored = [(score, p) for p in profiles if (score := p.matches(invoice)) is not None]
    return max(scored, key=lambda pair: pair[0])[1] if scored else None


def group_invoices(invoices: list[Invoice]) -> list[InvoiceGroup]:
    """Single-linkage clustering with union-find.

    Single linkage ("similar to *any* member") keeps a chain of related
    invoices together even if the first and last share few words - typical
    for a series of jobs at different addresses.
    """
    token_sets = [tokens(i.description_text) for i in invoices]
    parent = list(range(len(invoices)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]  # path halving keeps trees flat
            i = parent[i]
        return i

    for i in range(len(invoices)):
        for j in range(i + 1, len(invoices)):
            if similar(token_sets[i], invoices[i].customer_ico, token_sets[j], invoices[j].customer_ico):
                parent[find(i)] = find(j)

    clusters: dict[int, list[int]] = {}
    for i in range(len(invoices)):
        clusters.setdefault(find(i), []).append(i)

    groups = []
    for members in clusters.values():
        member_invoices = [invoices[i] for i in members]
        # Count words per *line*: a word repeated on many lines and invoices
        # ("knn", "parc") describes the kind of work, a word on one line (a
        # village name) does not. Ties keep alphabetical order for stability.
        counts = Counter(
            word
            for invoice in member_invoices
            for line in (invoice.note, *(item.description for item in invoice.lines))
            for word in tokens(line)
        )
        ranked = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
        shared = [w for w, c in ranked if c > 1] or [w for w, _ in ranked]
        customers = Counter(i.customer_ico for i in member_invoices)
        customer_ico = customers.most_common(1)[0][0]
        name = next((i.customer_name for i in member_invoices if i.customer_ico == customer_ico), None)
        groups.append(
            InvoiceGroup(
                id="g:" + min(i.key for i in member_invoices),
                invoices=member_invoices,
                customer_ico=customer_ico,
                customer_name=name,
                top_words=tuple(shared[:4]),
            )
        )
    groups.sort(key=lambda g: (-len(g.invoices), g.label))
    return groups


def profile_from_group(group: InvoiceGroup, rate_id: str) -> GroupProfile:
    return GroupProfile(group.customer_ico, group.token_union, rate_id, group.label)
