import json
from datetime import date
from pathlib import Path

import pytest

from commission_tax_calc.core.ares import (
    AresError,
    info_from_json,
    info_to_json,
    lookup,
    parse_rzp,
    suggested_rate_ids,
)
from commission_tax_calc.core.grouping import best_profile, group_invoices, profile_from_group, tokens
from commission_tax_calc.core.isdoc import parse_isdoc
from commission_tax_calc.core.rules import RulesRepository
from factory import CUSTOMER_A, CUSTOMER_B, InvoiceSpec, make_isdoc

RULES, _ = RulesRepository(None).get(2026)


def inv(number, customer, *lines):
    spec = InvoiceSpec(
        number=number,
        customer_ico=customer[0],
        customer_name=customer[1],
        lines=[(text, 1000) for text in lines],
    )
    return parse_isdoc(make_isdoc(spec), Path(f"{number}.isdoc"))


def test_tokens_ignore_numbers_and_stopwords():
    assert tokens("IP-12-8035791 Lužná, č.parc. 3424 NNV, dle Vaší objednávky") == {
        "ip",
        "lužná",
        "parc",
        "nnv",
    }


def test_groups_by_customer_and_similar_text():
    invoices = [
        inv("1", CUSTOMER_A, "Montáž elektroinstalace, byt Lužná", "Revize elektroinstalace"),
        inv("2", CUSTOMER_A, "Montáž elektroinstalace, dům Doubrava", "Revize elektroinstalace"),
        inv("3", CUSTOMER_B, "Projektová dokumentace stavby, Hlinka"),
        inv("4", CUSTOMER_B, "Projektová dokumentace přípojky, Lhota"),
    ]
    groups = group_invoices(invoices)
    assert sorted(sorted(i.number for i in g.invoices) for g in groups) == [["1", "2"], ["3", "4"]]
    labels = {g.customer_ico: g.label for g in groups}
    assert "elektroinstalace" in labels[CUSTOMER_A[0]]
    assert "dokumentace" in labels[CUSTOMER_B[0]]


def test_same_customer_different_work_is_split():
    groups = group_invoices(
        [
            inv("1", CUSTOMER_A, "Montáž elektroinstalace"),
            inv("2", CUSTOMER_A, "Pronájem lešení"),
        ]
    )
    assert len(groups) == 2


def test_profile_matches_new_similar_invoice():
    group = group_invoices([inv("1", CUSTOMER_A, "Montáž elektroinstalace, Lužná", "Revize")])[0]
    profile = profile_from_group(group, "crafts_agriculture")
    newcomer = inv("9", CUSTOMER_A, "Montáž elektroinstalace, Frenštát", "Revize")
    stranger = inv("8", CUSTOMER_B, "Účetní služby za březen")
    assert best_profile(newcomer, [profile]) is profile
    assert best_profile(stranger, [profile]) is None


# ----------------------------------------------------------------- ARES ---

FREE_TRADE = "Výroba, obchod a služby neuvedené v přílohách 1 až 3 živnostenského zákona"
RZP_RESPONSE = {
    "icoId": "12345679",
    "zaznamy": [
        {
            "ico": "12345679",
            "obchodniJmeno": "Testovací Tomáš",
            "primarniZaznam": True,
            "zivnosti": [
                {
                    "predmetPodnikani": "Montáž, opravy, revize a zkoušky elektrických zařízení",
                    "druhZivnosti": "R",
                    "datumVzniku": "2015-01-01",
                },
                {
                    "predmetPodnikani": FREE_TRADE,
                    "druhZivnosti": "V",
                    "datumVzniku": "2015-01-01",
                },
                {
                    "predmetPodnikani": "Hostinská činnost",
                    "datumVzniku": "2010-01-01",
                    "datumZaniku": "2012-12-31",
                },
            ],
        }
    ],
}


def test_parse_rzp_and_suggest_rates():
    info = parse_rzp(RZP_RESPONSE, "12345679", date(2026, 11, 12))
    assert info.name == "Testovací Tomáš"
    assert len(info.trades) == 3
    assert len(info.active_trades(date(2026, 12, 31))) == 2  # the 2012 trade ended
    assert suggested_rate_ids(info, RULES, date(2026, 12, 31)) == {"crafts_agriculture", "trades"}


def test_single_rate_when_all_trades_agree():
    data = json.loads(json.dumps(RZP_RESPONSE))
    data["zaznamy"][0]["zivnosti"] = data["zaznamy"][0]["zivnosti"][1:2]
    info = parse_rzp(data, "12345679", date(2026, 1, 1))
    assert suggested_rate_ids(info, RULES, date(2026, 12, 31)) == {"trades"}


def test_lookup_uses_fetcher_and_handles_404():
    calls = []

    def fetch(url):
        calls.append(url)
        return None  # not in the trade register

    info = lookup("12345679", fetch=fetch, today=date(2026, 1, 1))
    assert info.trades == ()
    assert calls == ["https://ares.gov.cz/ekonomicke-subjekty-v-be/rest/ekonomicke-subjekty-rzp/12345679"]


def test_invalid_ico_is_never_sent():
    def fetch(url):
        raise AssertionError("must not be called")

    with pytest.raises(AresError):
        lookup("12345678", fetch=fetch)


def test_ares_cache_roundtrip():
    info = parse_rzp(RZP_RESPONSE, "12345679", date(2026, 11, 12))
    assert info_from_json(json.loads(json.dumps(info_to_json(info)))) == info
