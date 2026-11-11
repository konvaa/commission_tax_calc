import copy
import json
from decimal import Decimal
from importlib import resources

import pytest

from commission_tax_calc.core.rules import RulesError, RulesRepository, parse_rules


def bundled_json(year=2026):
    path = resources.files("commission_tax_calc") / "rules" / f"{year}.json"
    return json.loads(path.read_text("utf-8"))


def test_bundled_years_available():
    repo = RulesRepository(None)
    assert {2024, 2025, 2026} <= set(repo.years)


def test_index_matches_bundled_files():
    # The remote updater trusts index.json - it must list every file and revision.
    folder = resources.files("commission_tax_calc") / "rules"
    index = json.loads((folder / "index.json").read_text("utf-8"))
    files = {
        e.name[:4]: json.loads(e.read_text("utf-8"))["revision"]
        for e in folder.iterdir()
        if e.name[:4].isdigit()
    }
    assert index["years"] == files


def test_current_rates_2026():
    rules = parse_rules(bundled_json(2026))
    assert [(r.percent, r.max_expenses) for r in rules.rates] == [
        (Decimal(80), Decimal(1_600_000)),
        (Decimal(60), Decimal(1_200_000)),
        (Decimal(40), Decimal(800_000)),
        (Decimal(30), Decimal(600_000)),
    ]
    assert rules.income_cap == Decimal(2_000_000)


@pytest.mark.parametrize(
    ("heading", "percent"),
    [
        ("Není živností, řídí se zvláštním předpisem", 40),
        ("Živnost volná", 60),
        ("Živnost řemeslná", 80),
    ],
)
def test_activity_mapping(heading, percent):
    rate = parse_rules(bundled_json()).rate_for_activity(heading)
    assert rate.percent == percent


def test_unknown_activity_maps_to_none():
    assert parse_rules(bundled_json()).rate_for_activity("Něco úplně jiného") is None


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d["rates"][0].update(percent=120),
        lambda d: d["rates"][0].update(percent="abc"),
        lambda d: d["activity_mapping"].append({"match": "x", "rate_id": "nope"}),
        lambda d: d["sources"][0].update(url="http://insecure.example"),
        lambda d: d.update(schema_version=99),
        lambda d: d.pop("rates"),
    ],
)
def test_invalid_rules_rejected(mutate):
    data = copy.deepcopy(bundled_json())
    mutate(data)
    with pytest.raises(RulesError):
        parse_rules(data)


def test_fallback_to_earlier_year():
    rules, exact = RulesRepository(None).get(2099)
    assert not exact
    assert rules.tax_year == max(RulesRepository(None).years)


def test_cache_with_higher_revision_wins(tmp_path):
    data = bundled_json(2026)
    data["revision"] = 99
    data["rates"][2]["percent"] = 45
    (tmp_path / "2026.json").write_text(json.dumps(data), "utf-8")
    rules, _ = RulesRepository(tmp_path).get(2026)
    assert rules.revision == 99
    assert rules.origin == "cache"
    assert rules.rate("other_self_employment").percent == 45


def test_corrupt_cache_is_ignored(tmp_path):
    (tmp_path / "2026.json").write_text("{not json", "utf-8")
    rules, _ = RulesRepository(tmp_path).get(2026)
    assert rules.origin == "bundled"


def fake_remote(files: dict[str, object]):
    calls = []

    def fetch(url: str) -> bytes:
        calls.append(url)
        name = url.rsplit("/", 1)[-1]
        if name not in files:
            raise OSError("404")
        return json.dumps(files[name]).encode()

    return fetch, calls


def test_update_downloads_only_newer_revisions(tmp_path):
    newer = bundled_json(2026)
    newer["revision"] = 5
    fetch, calls = fake_remote(
        {
            "index.json": {"schema_version": 1, "years": {"2025": 1, "2026": 5}},
            "2026.json": newer,
        }
    )
    repo = RulesRepository(tmp_path, remote_base="https://example.test/", fetch=fetch)
    result = repo.update_from_remote()
    assert result.updated_years == [2026]
    assert calls == ["https://example.test/index.json", "https://example.test/2026.json"]
    assert repo.get(2026)[0].revision == 5
    assert (tmp_path / "2026.json").is_file()


def test_update_rejects_mismatched_year(tmp_path):
    wrong = bundled_json(2025)
    wrong["revision"] = 9
    fetch, _ = fake_remote(
        {
            "index.json": {"schema_version": 1, "years": {"2026": 9}},
            "2026.json": wrong,
        }
    )
    repo = RulesRepository(tmp_path, remote_base="https://example.test/", fetch=fetch)
    with pytest.raises(RulesError):
        repo.update_from_remote()
    assert not (tmp_path / "2026.json").exists()


def test_update_network_error_propagates(tmp_path):
    fetch, _ = fake_remote({})
    repo = RulesRepository(tmp_path, remote_base="https://example.test/", fetch=fetch)
    with pytest.raises(OSError):
        repo.update_from_remote()
