"""Quality scores and ratios: Piotroski F-score, Altman Z-score, ROE, ROCE and friends."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from .models import Company, YearData


def _div(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None or b == 0:
        return None
    return a / b


def _year(c: Company, year: Optional[int]) -> int:
    if not c.years:
        raise ValueError("%s has no yearly data" % c.label)
    if year is None:
        return len(c.years) - 1
    for i, y in enumerate(c.years):
        if y.year == year:
            return i
    raise ValueError("%s has no data for %s" % (c.label, year))


def _avg(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None:
        return b
    if b is None:
        return a
    return (a + b) / 2


# --------------------------------------------------------------------------- simple ratios


def roe(c: Company, year: Optional[int] = None) -> Optional[float]:
    """Return on equity in percent: net profit / average equity (opening + closing) / 2.

    Falls back to closing equity when the previous year is missing. ``None``
    if average equity is not positive.
    """
    i = _year(c, year)
    y = c.years[i]
    prev_eq = c.years[i - 1].equity if i > 0 else None
    eq = _avg(prev_eq, y.equity)
    if y.net_profit is None or eq is None or eq <= 0:
        return None
    return 100.0 * y.net_profit / eq


def roce(c: Company, year: Optional[int] = None) -> Optional[float]:
    """Return on capital employed in percent: EBIT / average (equity + total debt)."""
    i = _year(c, year)
    y = c.years[i]

    def ce(x: YearData) -> Optional[float]:
        if x.equity is None or x.total_debt is None:
            return None
        return x.equity + x.total_debt

    cap = _avg(ce(c.years[i - 1]) if i > 0 else None, ce(y))
    if y.ebit is None or cap is None or cap <= 0:
        return None
    return 100.0 * y.ebit / cap


def debt_to_equity(y: YearData) -> Optional[float]:
    if y.equity is None or y.equity <= 0:
        return None
    return _div(y.total_debt, y.equity)


def interest_coverage(y: YearData) -> Optional[float]:
    if not y.interest_expense or y.interest_expense <= 0:
        return None
    return _div(y.ebit, y.interest_expense)


def current_ratio(y: YearData) -> Optional[float]:
    return _div(y.current_assets, y.current_liabilities)


def pe_ratio(y: YearData) -> Optional[float]:
    """Market value / net profit; ``None`` for loss-makers."""
    mv = y.market_value
    if mv is None or y.net_profit is None or y.net_profit <= 0:
        return None
    return mv / y.net_profit


# --------------------------------------------------------------------------- Piotroski


@dataclass
class Criterion:
    name: str
    passed: Optional[bool]  # None = not evaluable (missing data)
    rule: str
    values: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FScore:
    year: int
    score: int
    evaluated: int
    asset_basis: str  # "beginning" or "end"
    criteria: List[Criterion]

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        for cr in d["criteria"]:
            cr["values"] = {k: (round(v, 6) if isinstance(v, float) else v) for k, v in cr["values"].items()}
        return d


def piotroski(c: Company, year: Optional[int] = None) -> FScore:
    """Piotroski (2000) F-score with a per-criterion breakdown.

    Needs the scored year and the previous year. ROA and asset turnover are
    scaled by *beginning-of-year* total assets (as in the paper) when a third,
    earlier year is available; otherwise both years use end-of-year assets so
    the comparison stays like-for-like (see ``asset_basis``). Criteria that
    lack data are ``passed=None`` and excluded from ``evaluated``.
    """
    i = _year(c, year)
    if i < 1:
        raise ValueError("Piotroski F-score needs at least two consecutive years")
    t, p = c.years[i], c.years[i - 1]
    pp = c.years[i - 2] if i >= 2 else None
    if pp is not None and pp.total_assets and p.total_assets:
        basis, a_t, a_p = "beginning", p.total_assets, pp.total_assets
    else:
        basis, a_t, a_p = "end", t.total_assets, p.total_assets

    roa_t, roa_p = _div(t.net_profit, a_t), _div(p.net_profit, a_p)
    lev_t, lev_p = _div(t.total_debt, t.total_assets), _div(p.total_debt, p.total_assets)
    cr_t, cr_p = current_ratio(t), current_ratio(p)
    gm_t, gm_p = _div(t.gross_profit, t.revenue), _div(p.gross_profit, p.revenue)
    at_t, at_p = _div(t.revenue, a_t), _div(p.revenue, a_p)

    def cmp(ok: bool, *vals: Optional[float]) -> Optional[bool]:
        return None if any(v is None for v in vals) else ok

    crit = [
        Criterion("roa_positive", cmp(roa_t is not None and roa_t > 0, roa_t),
                  "net profit / total assets > 0", {"roa": roa_t}),
        Criterion("cfo_positive", cmp(t.operating_cash_flow is not None and t.operating_cash_flow > 0,
                                      t.operating_cash_flow),
                  "operating cash flow > 0", {"cfo": t.operating_cash_flow}),
        Criterion("roa_improving", cmp(roa_t is not None and roa_p is not None and roa_t > roa_p, roa_t, roa_p),
                  "ROA this year > ROA last year", {"roa": roa_t, "roa_prev": roa_p}),
        Criterion("accruals", cmp(t.operating_cash_flow is not None and t.net_profit is not None
                                  and t.operating_cash_flow > t.net_profit, t.operating_cash_flow, t.net_profit),
                  "operating cash flow > net profit (CFO/assets > ROA)",
                  {"cfo": t.operating_cash_flow, "net_profit": t.net_profit}),
        Criterion("leverage_falling",
                  cmp(lev_t is not None and lev_p is not None and (lev_t < lev_p or (lev_t == 0 and lev_p == 0)),
                      lev_t, lev_p),
                  "total debt / total assets lower than last year (debt-free both years also passes)",
                  {"leverage": lev_t, "leverage_prev": lev_p}),
        Criterion("current_ratio_improving", cmp(cr_t is not None and cr_p is not None and cr_t > cr_p, cr_t, cr_p),
                  "current ratio higher than last year", {"current_ratio": cr_t, "current_ratio_prev": cr_p}),
        Criterion("no_dilution",
                  cmp(t.shares_outstanding is not None and p.shares_outstanding is not None
                      and t.shares_outstanding <= p.shares_outstanding, t.shares_outstanding, p.shares_outstanding),
                  "shares outstanding not higher than last year",
                  {"shares": t.shares_outstanding, "shares_prev": p.shares_outstanding}),
        Criterion("gross_margin_improving", cmp(gm_t is not None and gm_p is not None and gm_t > gm_p, gm_t, gm_p),
                  "gross profit / revenue higher than last year (needs gross_profit)",
                  {"gross_margin": gm_t, "gross_margin_prev": gm_p}),
        Criterion("asset_turnover_improving",
                  cmp(at_t is not None and at_p is not None and at_t > at_p, at_t, at_p),
                  "revenue / total assets higher than last year",
                  {"asset_turnover": at_t, "asset_turnover_prev": at_p}),
    ]
    score = sum(1 for cr in crit if cr.passed)
    evaluated = sum(1 for cr in crit if cr.passed is not None)
    return FScore(t.year, score, evaluated, basis, crit)


# --------------------------------------------------------------------------- Altman


ALTMAN_NOTE = (
    "Original Altman (1968) Z-score, calibrated on US listed manufacturing companies. "
    "It is not designed for banks, NBFCs, insurers or asset-light service firms, and "
    "Indian accounting, promoter-group structures and market valuations can shift results."
)


@dataclass
class ZScore:
    year: int
    z: Optional[float]
    zone: Optional[str]  # "safe" (> 2.99), "grey" (1.81-2.99), "distress" (< 1.81)
    components: Dict[str, Optional[float]]
    missing: List[str]
    warnings: List[str]

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        if d["z"] is not None:
            d["z"] = round(d["z"], 4)
        d["components"] = {k: (None if v is None else round(v, 6)) for k, v in d["components"].items()}
        return d


def altman_z(c: Company, year: Optional[int] = None) -> ZScore:
    """Z = 1.2*X1 + 1.4*X2 + 3.3*X3 + 0.6*X4 + 1.0*X5.

    X1 = working capital / total assets, X2 = retained earnings / total assets,
    X3 = EBIT / total assets, X4 = market value of equity / total liabilities,
    X5 = revenue / total assets.
    """
    y = c.years[_year(c, year)]
    need = {
        "total_assets": y.total_assets,
        "current_assets": y.current_assets,
        "current_liabilities": y.current_liabilities,
        "retained_earnings": y.retained_earnings,
        "ebit": y.ebit,
        "market_value (price*shares or market_cap)": y.market_value,
        "total_liabilities (or total_assets - equity)": y.liabilities,
        "revenue": y.revenue,
    }
    missing = [k for k, v in need.items() if v is None]
    warnings = [ALTMAN_NOTE]
    if c.is_financial:
        warnings.insert(0, "Company is flagged is_financial: the Z-score is not meaningful for financial firms.")
    ta, tl = y.total_assets, y.liabilities
    if ta is not None and ta <= 0:
        missing.append("total_assets must be > 0")
    if tl is not None and tl <= 0:
        missing.append("total_liabilities must be > 0")
    if missing:
        return ZScore(y.year, None, None, {}, missing, warnings)
    x1 = (y.current_assets - y.current_liabilities) / ta  # type: ignore[operator]
    x2 = y.retained_earnings / ta  # type: ignore[operator]
    x3 = y.ebit / ta  # type: ignore[operator]
    x4 = y.market_value / tl  # type: ignore[operator]
    x5 = y.revenue / ta  # type: ignore[operator]
    z = 1.2 * x1 + 1.4 * x2 + 3.3 * x3 + 0.6 * x4 + 1.0 * x5
    zone = "safe" if z > 2.99 else ("grey" if z >= 1.81 else "distress")
    return ZScore(y.year, z, zone, {"x1": x1, "x2": x2, "x3": x3, "x4": x4, "x5": x5}, [], warnings)
