import json
from datetime import date
from pathlib import Path

from commission_tax_calc import cli
from commission_tax_calc.core.loader import LoadResult
from commission_tax_calc.core.parser import parse_text
from factory import Spec, make_text


def fake_load(monkeypatch, tmp_path, specs):
    statements = [parse_text(make_text(s), source=Path(f"{i}.pdf")) for i, s in enumerate(specs)]
    monkeypatch.setattr(cli, "load_documents", lambda paths, my_ico=None: LoadResult(statements=statements))
    monkeypatch.setattr(cli, "rules_cache_dir", lambda: tmp_path / "cache")
    monkeypatch.setattr(cli, "user_data_dir", lambda: tmp_path / "data")


def test_cli_json(monkeypatch, tmp_path, capsys):
    fake_load(
        monkeypatch,
        tmp_path,
        [
            Spec(start=date(2030, 1, 1), end=date(2030, 1, 14), rows=[("A", "1", "P", "X, a.s.", 1000)]),
            Spec(start=date(2030, 1, 15), end=date(2030, 1, 31), rows=[("B", "2", "P", "X, a.s.", 2000)]),
        ],
    )
    assert cli.main([str(tmp_path), "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["year"] == 2030
    assert out["commission_total"] == "3000"
    assert out["rates"][0]["percent"] == "40"
    assert out["partial_tax_base"] == "1800"
    assert out["rules_exact_year"] is False  # no rules for 2030 -> fallback


def test_cli_text(monkeypatch, tmp_path, capsys):
    fake_load(monkeypatch, tmp_path, [Spec()])
    assert cli.main([str(tmp_path), "--year", "2030"]) == 0
    assert "Partial tax base § 7" in capsys.readouterr().out


def test_cli_rejects_missing_folder(capsys):
    assert cli.main(["/definitely/not/here"]) == 2
