import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from stock_red_flags.models import Company, year_from_dict  # noqa: E402


def clean_years(n=3, start=2022):
    """A healthy, steadily growing (10%/yr) company that should trigger no flags."""
    out = []
    for k in range(n):
        g = 1.1 ** k
        out.append({
            "year": start + k,
            "revenue": 1000 * g,
            "net_profit": 100 * g,
            "operating_cash_flow": 110 * g,
            "total_debt": 200.0,
            "equity": 1000.0 + 100 * k,
            "interest_expense": 10.0,
            "ebit": 160 * g,
            "receivables": 150 * g,
            "inventory": 120 * g,
            "total_assets": 1500.0 + 100 * k,
            "current_assets": 600.0,
            "current_liabilities": 300.0,
            "shares_outstanding": 50.0,
            "promoter_holding_pct": 60.0,
            "promoter_pledged_pct": 0.0,
            "price": 100.0,
            "gross_profit": 400 * g,
            "retained_earnings": 500.0,
        })
    return out


def company(years, is_financial=False, name="Test Co"):
    return Company(name=name, years=[year_from_dict(y) for y in years], symbol="TEST", is_financial=is_financial)


def modified(changes, n=3):
    """Clean company whose year ``i`` gets ``changes[i]`` (dict) merged in. Negative indices allowed."""
    ys = clean_years(n)
    for idx, upd in changes.items():
        ys[idx].update(upd)
    return ys
