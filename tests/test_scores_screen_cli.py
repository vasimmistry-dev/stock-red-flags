import json
import os

import pytest
from conftest import clean_years, company

from stock_red_flags import (
    altman_z, compute_metrics, load_companies, parse_condition, piotroski, roce, roe, screen,
)
from stock_red_flags.cli import main
from stock_red_flags.models import companies_from_json

EX = os.path.join(os.path.dirname(__file__), "..", "examples")


# ---------------------------------------------------------------- Piotroski (hand-computed)

def fscore_years():
    return [
        {"year": 2022, "total_assets": 1000, "net_profit": 50, "revenue": 900},
        {"year": 2023, "total_assets": 1100, "net_profit": 60, "revenue": 1000, "total_debt": 330,
         "current_assets": 400, "current_liabilities": 250, "shares_outstanding": 100,
         "gross_profit": 300, "operating_cash_flow": 70},
        {"year": 2024, "total_assets": 1200, "net_profit": 88, "revenue": 1210, "total_debt": 300,
         "current_assets": 480, "current_liabilities": 280, "shares_outstanding": 100,
         "gross_profit": 375, "operating_cash_flow": 120},
    ]


def test_piotroski_perfect_nine():
    fs = piotroski(company(fscore_years()))
    assert fs.asset_basis == "beginning"
    assert (fs.score, fs.evaluated) == (9, 9)
    v = {c.name: c.values for c in fs.criteria}
    assert v["roa_positive"]["roa"] == pytest.approx(88 / 1100)          # 0.08
    assert v["roa_improving"]["roa_prev"] == pytest.approx(60 / 1000)    # 0.06
    assert v["leverage_falling"]["leverage"] == pytest.approx(0.25)
    assert v["leverage_falling"]["leverage_prev"] == pytest.approx(0.30)
    assert v["current_ratio_improving"]["current_ratio"] == pytest.approx(480 / 280)
    assert v["gross_margin_improving"]["gross_margin"] == pytest.approx(375 / 1210)
    assert v["asset_turnover_improving"]["asset_turnover"] == pytest.approx(1.1)
    assert v["asset_turnover_improving"]["asset_turnover_prev"] == pytest.approx(1.0)


def test_piotroski_one_point_only_accruals():
    ys = fscore_years()
    ys[2].update({"net_profit": -10, "operating_cash_flow": -5, "total_debt": 400, "current_assets": 300,
                  "shares_outstanding": 120, "gross_profit": 300, "revenue": 1050})
    fs = piotroski(company(ys))
    passed = [c.name for c in fs.criteria if c.passed]
    assert passed == ["accruals"]  # CFO -5 > net profit -10
    assert fs.score == 1


def test_piotroski_end_of_year_basis_with_two_years():
    fs = piotroski(company(fscore_years()[1:]))
    assert fs.asset_basis == "end"
    roa = next(c for c in fs.criteria if c.name == "roa_improving").values
    assert roa["roa"] == pytest.approx(88 / 1200)
    assert roa["roa_prev"] == pytest.approx(60 / 1100)


def test_piotroski_missing_gross_profit_not_evaluated():
    ys = fscore_years()
    del ys[2]["gross_profit"]
    fs = piotroski(company(ys))
    gm = next(c for c in fs.criteria if c.name == "gross_margin_improving")
    assert gm.passed is None
    assert (fs.score, fs.evaluated) == (8, 8)


def test_piotroski_debt_free_both_years_passes_leverage():
    ys = fscore_years()
    ys[1]["total_debt"] = 0
    ys[2]["total_debt"] = 0
    lev = next(c for c in piotroski(company(ys)).criteria if c.name == "leverage_falling")
    assert lev.passed is True


def test_piotroski_needs_two_years():
    with pytest.raises(ValueError):
        piotroski(company(fscore_years()[:1]))


def test_piotroski_specific_year():
    fs = piotroski(company(fscore_years()), year=2023)
    assert fs.year == 2023 and fs.asset_basis == "end"


# ---------------------------------------------------------------- Altman (hand-computed)

def z_year(**kw):
    y = {"year": 2024, "total_assets": 1000, "current_assets": 500, "current_liabilities": 300,
         "retained_earnings": 250, "ebit": 100, "equity": 400, "price": 30, "shares_outstanding": 40,
         "revenue": 1500}
    y.update(kw)
    return y


def test_altman_safe_zone():
    z = altman_z(company([z_year()]))
    # X1 .2, X2 .25, X3 .1, X4 1200/600 = 2, X5 1.5
    assert z.components == pytest.approx({"x1": 0.2, "x2": 0.25, "x3": 0.1, "x4": 2.0, "x5": 1.5})
    assert z.z == pytest.approx(1.2 * 0.2 + 1.4 * 0.25 + 3.3 * 0.1 + 0.6 * 2.0 + 1.5)  # 3.62
    assert z.z == pytest.approx(3.62)
    assert z.zone == "safe"


def test_altman_grey_and_distress_zones():
    grey = altman_z(company([z_year(market_cap=300)]))  # X4 = 0.5
    assert grey.z == pytest.approx(2.72) and grey.zone == "grey"
    distress = altman_z(company([z_year(market_cap=300, revenue=500)]))
    assert distress.z == pytest.approx(1.72) and distress.zone == "distress"


def test_altman_explicit_total_liabilities():
    z = altman_z(company([z_year(total_liabilities=1200)]))
    assert z.components["x4"] == pytest.approx(1.0)


def test_altman_missing_fields_and_financial_warning():
    z = altman_z(company([z_year(retained_earnings=None)], is_financial=True))
    assert z.z is None and any("retained_earnings" in m for m in z.missing)
    assert "not meaningful" in z.warnings[0]


# ---------------------------------------------------------------- ROE / ROCE

def test_roe_roce_average_capital():
    ys = [{"year": 2023, "equity": 400, "total_debt": 100},
          {"year": 2024, "equity": 600, "total_debt": 100, "net_profit": 100, "ebit": 150}]
    c = company(ys)
    assert roe(c) == pytest.approx(20.0)    # 100 / avg(400, 600)
    assert roce(c) == pytest.approx(25.0)   # 150 / avg(500, 700)
    assert roe(c, year=2023) is None        # no profit given


def test_roe_single_year_and_negative_equity():
    assert roe(company([{"year": 2024, "equity": 500, "net_profit": 50}])) == pytest.approx(10.0)
    assert roe(company([{"year": 2024, "equity": -5, "net_profit": 50}])) is None


# ---------------------------------------------------------------- screener

def test_parse_condition():
    assert parse_condition("roe>15") == ("roe", ">", 15.0)
    assert parse_condition(" D/E <= 0.5 ") == ("de", "<=", 0.5)
    for bad in ("roe", "roe >> 3", "foo > 1"):
        with pytest.raises(ValueError):
            parse_condition(bad)


def test_screen_examples():
    comps = load_companies(os.path.join(EX, "companies.json"))
    got = [r.company.symbol for r in screen(comps, ["roe > 15", "de < 0.5"])]
    assert got == ["ALPHA", "EPSILON"]
    assert [r.company.symbol for r in screen(comps, ["high_flags >= 1"])] == ["BETA", "DELTA"]
    assert len(screen(comps)) == len(comps)


def test_screen_missing_metric_fails_condition():
    comps = load_companies(os.path.join(EX, "companies.json"))
    syms = [r.company.symbol for r in screen(comps, ["pe < 1000"])]
    assert "DELTA" not in syms  # loss-maker has no P/E


def test_compute_metrics_on_clean_company():
    m = compute_metrics(company(clean_years()))
    assert m["red_flags"] == 0
    assert m["sales_growth"] == pytest.approx(10.0)
    assert m["de"] == pytest.approx(200 / 1200)
    assert m["market_cap"] == pytest.approx(5000)


# ---------------------------------------------------------------- loading & CLI

def test_load_json_shapes_and_csv():
    single = load_companies(os.path.join(EX, "company.json"))
    assert len(single) == 1 and single[0].symbol == "SAMPLEFAB" and len(single[0].years) == 3
    csv_comps = load_companies(os.path.join(EX, "companies.csv"))
    json_comps = load_companies(os.path.join(EX, "companies.json"))
    assert [c.symbol for c in csv_comps] == ["ALPHA", "BETA"]
    assert csv_comps[0].years == json_comps[0].years


def test_duplicate_year_rejected():
    with pytest.raises(ValueError):
        companies_from_json({"name": "x", "years": [{"year": 2024}, {"year": 2024}]})


def test_years_are_sorted():
    c = companies_from_json({"name": "x", "years": [{"year": 2025}, {"year": 2023}]})[0]
    assert [y.year for y in c.years] == [2023, 2025]


def test_cli_check_json(capsys):
    assert main(["check", os.path.join(EX, "company.json"), "--json"]) == 0
    r = json.loads(capsys.readouterr().out)
    assert {f["id"] for f in r["flags"]} >= {"promoter_pledge_high", "cfo_weak_vs_profit"}
    assert r["piotroski"]["evaluated"] == 9
    assert r["altman"]["zone"] in ("safe", "grey", "distress")


def test_cli_check_text_and_fail_on(capsys):
    path = os.path.join(EX, "company.json")
    assert main(["check", path]) == 0
    assert "Not investment advice" in capsys.readouterr().out
    assert main(["check", path, "--fail-on", "high"]) == 1


def test_cli_screen(capsys):
    assert main(["screen", os.path.join(EX, "companies.json"), "--roe-min", "15", "--de-max", "0.5", "--json"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert [m["symbol"] for m in out["matches"]] == ["ALPHA", "EPSILON"]
    assert main(["screen", os.path.join(EX, "companies.json"), "--where", "interest_coverage > 50"]) == 0
    assert "ALPHA" in capsys.readouterr().out


def test_cli_errors(capsys):
    assert main(["check", "missing.json"]) == 2
    assert main(["screen", os.path.join(EX, "companies.json"), "--where", "nonsense"]) == 2
