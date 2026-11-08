import pytest
from conftest import clean_years, company, modified

from stock_red_flags import Thresholds, check_company


def ids(c, **kw):
    return {f.id for f in check_company(c, **kw)}


def get(c, fid):
    return next(f for f in check_company(c) if f.id == fid)


def test_clean_company_has_no_flags():
    assert check_company(company(clean_years())) == []


def test_single_year_does_not_crash():
    assert check_company(company(clean_years(1))) == []


# ---------------------------------------------------------------- CFO vs profit

def test_cfo_weak_vs_growing_profit_fires():
    ys = modified({0: {"operating_cash_flow": 40}, 1: {"operating_cash_flow": 50}, 2: {"operating_cash_flow": 60}})
    f = get(company(ys), "cfo_weak_vs_profit")
    pat = 100 + 110 + 121
    assert f.evidence["cfo_to_pat"] == pytest.approx(150 / pat)
    assert f.severity == "medium"


def test_cfo_weak_high_severity():
    ys = modified({0: {"operating_cash_flow": 10}, 1: {"operating_cash_flow": 20}, 2: {"operating_cash_flow": 30}})
    assert get(company(ys), "cfo_weak_vs_profit").severity == "high"


def test_cfo_at_threshold_does_not_fire():
    ys = clean_years()
    pat = sum(y["net_profit"] for y in ys)
    for y in ys:
        y["operating_cash_flow"] = 0.7 * pat / 3
    assert "cfo_weak_vs_profit" not in ids(company(ys))


def test_cfo_weak_needs_profit_growth():
    ys = modified({0: {"net_profit": 150, "operating_cash_flow": 40},
                   1: {"operating_cash_flow": 40}, 2: {"operating_cash_flow": 40}})
    assert "cfo_weak_vs_profit" not in ids(company(ys))  # profit fell from 150 to 121


def test_cfo_weak_skipped_for_financials():
    ys = modified({0: {"operating_cash_flow": 10}, 1: {"operating_cash_flow": 20}, 2: {"operating_cash_flow": 30}})
    assert "cfo_weak_vs_profit" not in ids(company(ys, is_financial=True))


# ---------------------------------------------------------------- receivables / inventory

def test_receivables_outpacing_revenue():
    ys = modified({2: {"receivables": 150 * 1.1 * 1.5}})  # +50% vs revenue +10%
    f = get(company(ys), "receivables_outpacing_revenue")
    assert f.evidence["gap"] == pytest.approx(0.40)
    assert f.severity == "medium"


def test_receivables_gap_within_threshold():
    ys = modified({2: {"receivables": 150 * 1.1 * 1.25}})  # gap 15 pp
    assert "receivables_outpacing_revenue" not in ids(company(ys))


def test_receivables_immaterial_are_ignored():
    ys = modified({1: {"receivables": 10}, 2: {"receivables": 30}})  # +200% but only 2.5% of revenue
    assert "receivables_outpacing_revenue" not in ids(company(ys))


def test_inventory_outpacing_revenue_high():
    ys = modified({2: {"inventory": 120 * 1.1 * 1.8}})  # +80% vs +10%
    f = get(company(ys), "inventory_outpacing_revenue")
    assert f.severity == "high"


# ---------------------------------------------------------------- leverage

def test_high_debt_to_equity():
    f = get(company(modified({2: {"total_debt": 1500}})), "high_debt_to_equity")
    assert f.evidence["debt_to_equity"] == pytest.approx(1500 / 1200)
    assert f.severity == "medium"
    assert get(company(modified({2: {"total_debt": 3000}})), "high_debt_to_equity").severity == "high"


def test_de_exactly_one_does_not_fire():
    assert "high_debt_to_equity" not in ids(company(modified({2: {"total_debt": 1200}})))


def test_financial_company_exempt_from_de():
    ys = modified({2: {"total_debt": 6000}})
    assert "high_debt_to_equity" not in ids(company(ys, is_financial=True))


def test_negative_equity():
    f = get(company(modified({2: {"equity": -50}})), "negative_equity")
    assert f.severity == "high"


def test_low_interest_coverage():
    f = get(company(modified({2: {"interest_expense": 120}})), "low_interest_coverage")
    assert f.evidence["interest_coverage"] == pytest.approx(193.6 / 120)
    assert f.severity == "medium"
    assert get(company(modified({2: {"interest_expense": 250}})), "low_interest_coverage").severity == "high"


def test_coverage_ok_or_debt_free():
    assert "low_interest_coverage" not in ids(company(modified({2: {"interest_expense": 90}})))  # 2.15x
    assert "low_interest_coverage" not in ids(company(modified({2: {"interest_expense": 0}})))


def test_rising_debt_falling_profit():
    f = get(company(modified({2: {"total_debt": 260, "net_profit": 90}})), "rising_debt_falling_profit")
    assert f.evidence["debt_growth"] == pytest.approx(0.30)
    assert f.severity == "medium"


def test_rising_debt_with_rising_profit_is_fine():
    assert "rising_debt_falling_profit" not in ids(company(modified({2: {"total_debt": 260}})))


def test_small_debt_increase_is_fine():
    ys = modified({2: {"total_debt": 215, "net_profit": 90}})  # +7.5%
    assert "rising_debt_falling_profit" not in ids(company(ys))


# ---------------------------------------------------------------- promoters

def test_pledge_above_25_pct():
    f = get(company(modified({1: {"promoter_pledged_pct": 26}, 2: {"promoter_pledged_pct": 26}})),
            "promoter_pledge_high")
    assert f.severity == "high"
    assert "promoter_pledge_rising" not in ids(company(modified({1: {"promoter_pledged_pct": 26},
                                                                 2: {"promoter_pledged_pct": 26}})))


def test_pledge_exactly_25_does_not_fire():
    assert "promoter_pledge_high" not in ids(company(modified({2: {"promoter_pledged_pct": 25}})))


def test_pledge_rising():
    c = company(modified({1: {"promoter_pledged_pct": 5}, 2: {"promoter_pledged_pct": 15}}))
    f = get(c, "promoter_pledge_rising")
    assert f.evidence["rise_pp"] == 10 and f.severity == "medium"
    small = company(modified({1: {"promoter_pledged_pct": 2}, 2: {"promoter_pledged_pct": 8}}))
    assert get(small, "promoter_pledge_rising").severity == "low"
    assert "promoter_pledge_rising" not in ids(company(modified({2: {"promoter_pledged_pct": 4}})))


def test_promoter_holding_falling():
    f = get(company(modified({2: {"promoter_holding_pct": 52}})), "promoter_holding_falling")
    assert f.evidence["drop_pp"] == 8 and f.severity == "medium"
    assert get(company(modified({2: {"promoter_holding_pct": 45}})), "promoter_holding_falling").severity == "high"
    assert "promoter_holding_falling" not in ids(company(modified({2: {"promoter_holding_pct": 55}})))


# ---------------------------------------------------------------- dilution / losses / CFO

def test_equity_dilution():
    f = get(company(modified({2: {"shares_outstanding": 56}})), "equity_dilution")
    assert f.evidence["growth"] == pytest.approx(0.12)
    assert "equity_dilution" not in ids(company(modified({2: {"shares_outstanding": 55}})))  # exactly 10%
    assert get(company(modified({2: {"shares_outstanding": 70}})), "equity_dilution").severity == "high"


def test_repeated_losses():
    two = company(modified({1: {"net_profit": -5}, 2: {"net_profit": -8}}))
    assert get(two, "repeated_losses").severity == "medium"
    three = company(modified({0: {"net_profit": -1}, 1: {"net_profit": -5}, 2: {"net_profit": -8}}))
    assert get(three, "repeated_losses").severity == "high"
    assert "repeated_losses" not in ids(company(modified({2: {"net_profit": -8}})))


def test_negative_cfo():
    one = company(modified({2: {"operating_cash_flow": -10}}))
    assert get(one, "negative_cfo").severity == "medium"
    two = company(modified({1: {"operating_cash_flow": -3}, 2: {"operating_cash_flow": -10}}))
    assert get(two, "negative_cfo").severity == "high"
    assert "negative_cfo" not in ids(company(modified({2: {"operating_cash_flow": -10}}), is_financial=True))


# ---------------------------------------------------------------- misc

def test_custom_thresholds():
    c = company(modified({2: {"total_debt": 900}}))  # D/E 0.75
    assert "high_debt_to_equity" not in ids(c)
    assert "high_debt_to_equity" in ids(c, thresholds=Thresholds(de_max=0.5))


def test_flags_sorted_by_severity_and_serialisable():
    c = company(modified({2: {"promoter_pledged_pct": 40, "shares_outstanding": 56}}))
    flags = check_company(c)
    assert [f.severity for f in flags] == ["high", "medium", "medium"][: len(flags)]
    d = flags[0].to_dict()
    assert set(d) == {"id", "severity", "year", "title", "explanation", "evidence"}


def test_missing_data_is_skipped_not_crashing():
    ys = [{"year": 2023}, {"year": 2024, "revenue": 10}]
    assert check_company(company(ys)) == []
