"""Rule-based red-flag checks on yearly financials.

Every check is a small function that looks at the latest year (and, where
needed, earlier years) and returns zero or more :class:`Flag` objects. Each
flag has a stable ``id``, a ``severity`` and an ``evidence`` dict holding the
exact numbers that triggered it. The rules are repeated in README.md.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .models import Company, YearData

LOW, MEDIUM, HIGH = "low", "medium", "high"
SEVERITY_RANK = {LOW: 0, MEDIUM: 1, HIGH: 2}


@dataclass
class Flag:
    id: str
    severity: str
    year: int
    title: str
    explanation: str
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["evidence"] = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in self.evidence.items()}
        return d


@dataclass
class Thresholds:
    """All tunable limits. Percentages are fractions unless the name ends in ``_pp`` (percentage points)."""

    cfo_to_pat_min: float = 0.7          # cumulative 3-year CFO / PAT
    cfo_to_pat_high: float = 0.3
    growth_gap: float = 0.20             # receivables/inventory growth minus revenue growth
    growth_gap_high: float = 0.50
    materiality: float = 0.05            # receivables/inventory must be >= 5% of revenue
    de_max: float = 1.0
    de_high: float = 2.0
    coverage_min: float = 2.0
    coverage_high: float = 1.0
    debt_rise: float = 0.10              # debt up more than 10% YoY
    pledge_max_pct: float = 25.0
    pledge_rise_pp: float = 5.0
    promoter_drop_pp: float = 5.0
    promoter_drop_high_pp: float = 10.0
    dilution: float = 0.10
    dilution_high: float = 0.25


def _growth(prev: Optional[float], cur: Optional[float]) -> Optional[float]:
    """Fractional growth, defined only when the previous value is positive.

    Rounded to 10 decimals so values exactly at a threshold (e.g. 50 -> 55
    shares = 10%) are not tipped over it by floating-point error.
    """
    if prev is None or cur is None or prev <= 0:
        return None
    return round(cur / prev - 1, 10)


def _pct(x: float) -> str:
    return "%.1f%%" % (100 * x)


def _pair(c: Company):
    if len(c.years) < 2:
        return None, None
    return c.years[-2], c.years[-1]


# --------------------------------------------------------------------------- earnings quality


def check_cfo_vs_profit(c: Company, t: Thresholds) -> List[Flag]:
    if c.is_financial:
        return []
    ys = c.last(3)
    if len(ys) < 3 or any(y.net_profit is None or y.operating_cash_flow is None for y in ys):
        return []
    pat = sum(y.net_profit for y in ys)  # type: ignore[misc]
    cfo = sum(y.operating_cash_flow for y in ys)  # type: ignore[misc]
    growing = ys[-1].net_profit > ys[0].net_profit  # type: ignore[operator]
    if pat <= 0 or not growing:
        return []
    ratio = cfo / pat
    if ratio >= t.cfo_to_pat_min:
        return []
    sev = HIGH if ratio < t.cfo_to_pat_high else MEDIUM
    return [Flag(
        "cfo_weak_vs_profit", sev, ys[-1].year, "Profit growing but cash flow weak",
        "Over %d-%d net profit grew, but operating cash flow covered only %s of cumulative profit "
        "(threshold %s). Profits that do not turn into cash can point to aggressive revenue "
        "recognition or working-capital build-up." % (ys[0].year, ys[-1].year, _pct(ratio), _pct(t.cfo_to_pat_min)),
        {"years": [y.year for y in ys], "cumulative_net_profit": pat, "cumulative_cfo": cfo, "cfo_to_pat": ratio},
    )]


def _outpacing(c: Company, t: Thresholds, attr: str, fid: str, label: str, days_name: str) -> List[Flag]:
    p, y = _pair(c)
    if y is None:
        return []
    rev_g = _growth(p.revenue, y.revenue)
    item_g = _growth(getattr(p, attr), getattr(y, attr))
    if rev_g is None or item_g is None or not y.revenue:
        return []
    if getattr(y, attr) < t.materiality * y.revenue:
        return []
    gap = item_g - rev_g
    if gap <= t.growth_gap:
        return []
    sev = HIGH if gap > t.growth_gap_high else MEDIUM
    days_prev = getattr(p, attr) / p.revenue * 365
    days_cur = getattr(y, attr) / y.revenue * 365
    return [Flag(
        fid, sev, y.year, "%s growing much faster than revenue" % label.capitalize(),
        "%s grew %s while revenue grew %s (gap %s, threshold %s). %s went from %.0f to %.0f days."
        % (label.capitalize(), _pct(item_g), _pct(rev_g), _pct(gap), _pct(t.growth_gap), days_name, days_prev, days_cur),
        {attr + "_growth": item_g, "revenue_growth": rev_g, "gap": gap,
         days_name.lower().replace(" ", "_") + "_prev": days_prev,
         days_name.lower().replace(" ", "_"): days_cur},
    )]


def check_receivables(c: Company, t: Thresholds) -> List[Flag]:
    return _outpacing(c, t, "receivables", "receivables_outpacing_revenue", "receivables", "Debtor days")


def check_inventory(c: Company, t: Thresholds) -> List[Flag]:
    return _outpacing(c, t, "inventory", "inventory_outpacing_revenue", "inventory", "Inventory days")


# --------------------------------------------------------------------------- balance sheet


def check_leverage(c: Company, t: Thresholds) -> List[Flag]:
    y = c.latest
    if y is None or y.equity is None or y.total_debt is None:
        return []
    if y.equity <= 0:
        return [Flag(
            "negative_equity", HIGH, y.year, "Negative or zero net worth",
            "Shareholders' equity is %.2f, so accumulated losses have wiped out the capital base." % y.equity,
            {"equity": y.equity, "total_debt": y.total_debt},
        )]
    if c.is_financial:
        return []
    de = y.total_debt / y.equity
    if de <= t.de_max:
        return []
    sev = HIGH if de > t.de_high else MEDIUM
    return [Flag(
        "high_debt_to_equity", sev, y.year, "High debt to equity",
        "Debt/equity is %.2f (threshold %.2f). High leverage magnifies losses when business slows."
        % (de, t.de_max),
        {"total_debt": y.total_debt, "equity": y.equity, "debt_to_equity": de},
    )]


def check_interest_coverage(c: Company, t: Thresholds) -> List[Flag]:
    y = c.latest
    if c.is_financial or y is None or y.ebit is None or not y.interest_expense or y.interest_expense <= 0:
        return []
    cov = y.ebit / y.interest_expense
    if cov >= t.coverage_min:
        return []
    sev = HIGH if cov < t.coverage_high else MEDIUM
    return [Flag(
        "low_interest_coverage", sev, y.year, "Low interest coverage",
        "EBIT covers interest only %.2fx (threshold %.1fx).%s"
        % (cov, t.coverage_min, " Operating profit does not even cover interest." if cov < 1 else ""),
        {"ebit": y.ebit, "interest_expense": y.interest_expense, "interest_coverage": cov},
    )]


def check_debt_up_profit_down(c: Company, t: Thresholds) -> List[Flag]:
    p, y = _pair(c)
    if y is None or c.is_financial:
        return []
    if None in (p.total_debt, y.total_debt, p.net_profit, y.net_profit):
        return []
    rising = y.total_debt > p.total_debt * (1 + t.debt_rise) and y.total_debt > 0
    if not rising or y.net_profit >= p.net_profit:
        return []
    dg = _growth(p.total_debt, y.total_debt)
    return [Flag(
        "rising_debt_falling_profit", HIGH if y.net_profit < 0 else MEDIUM, y.year,
        "Debt rising while profit falls",
        "Total debt went from %.2f to %.2f%s while net profit fell from %.2f to %.2f."
        % (p.total_debt, y.total_debt, " (+%s)" % _pct(dg) if dg is not None else "", p.net_profit, y.net_profit),
        {"debt_prev": p.total_debt, "debt": y.total_debt, "debt_growth": dg,
         "net_profit_prev": p.net_profit, "net_profit": y.net_profit},
    )]


# --------------------------------------------------------------------------- shareholding


def check_pledge(c: Company, t: Thresholds) -> List[Flag]:
    y = c.latest
    if y is None or y.promoter_pledged_pct is None:
        return []
    out = []
    if y.promoter_pledged_pct > t.pledge_max_pct:
        out.append(Flag(
            "promoter_pledge_high", HIGH, y.year, "High promoter pledge",
            "%.1f%% of promoter shares are pledged (threshold %.0f%%). A falling share price can trigger "
            "margin calls and forced selling." % (y.promoter_pledged_pct, t.pledge_max_pct),
            {"promoter_pledged_pct": y.promoter_pledged_pct},
        ))
    p = c.years[-2] if len(c.years) >= 2 else None
    if p is not None and p.promoter_pledged_pct is not None:
        rise = y.promoter_pledged_pct - p.promoter_pledged_pct
        if rise >= t.pledge_rise_pp:
            sev = LOW if y.promoter_pledged_pct <= 10 else MEDIUM
            out.append(Flag(
                "promoter_pledge_rising", sev, y.year, "Promoter pledge rising",
                "Pledged share of promoter holding rose from %.1f%% to %.1f%% (+%.1f pp)."
                % (p.promoter_pledged_pct, y.promoter_pledged_pct, rise),
                {"pledged_prev": p.promoter_pledged_pct, "pledged": y.promoter_pledged_pct, "rise_pp": rise},
            ))
    return out


def check_promoter_holding(c: Company, t: Thresholds) -> List[Flag]:
    p, y = _pair(c)
    if y is None or p.promoter_holding_pct is None or y.promoter_holding_pct is None:
        return []
    drop = p.promoter_holding_pct - y.promoter_holding_pct
    if drop <= t.promoter_drop_pp:
        return []
    return [Flag(
        "promoter_holding_falling", HIGH if drop > t.promoter_drop_high_pp else MEDIUM, y.year,
        "Promoter holding falling sharply",
        "Promoter holding fell from %.1f%% to %.1f%% (-%.1f pp). Check whether this was a stake sale, "
        "an offer for sale or dilution from fresh issuance." % (p.promoter_holding_pct, y.promoter_holding_pct, drop),
        {"holding_prev": p.promoter_holding_pct, "holding": y.promoter_holding_pct, "drop_pp": drop},
    )]


def check_dilution(c: Company, t: Thresholds) -> List[Flag]:
    p, y = _pair(c)
    if y is None:
        return []
    g = _growth(p.shares_outstanding, y.shares_outstanding)
    if g is None or g <= t.dilution:
        return []
    return [Flag(
        "equity_dilution", HIGH if g > t.dilution_high else MEDIUM, y.year, "Equity dilution",
        "Shares outstanding rose %s in a year (threshold %s). If this was a bonus issue or split, "
        "adjust the share counts first; otherwise existing holders were diluted." % (_pct(g), _pct(t.dilution)),
        {"shares_prev": p.shares_outstanding, "shares": y.shares_outstanding, "growth": g},
    )]


# --------------------------------------------------------------------------- losses & cash burn


def check_repeated_losses(c: Company, t: Thresholds) -> List[Flag]:
    ys = [y for y in c.last(3) if y.net_profit is not None]
    losses = [y.year for y in ys if y.net_profit < 0]  # type: ignore[operator]
    if len(losses) < 2:
        return []
    sev = HIGH if len(losses) >= 3 else MEDIUM
    return [Flag(
        "repeated_losses", sev, c.years[-1].year, "Repeated losses",
        "Net loss in %d of the last %d reported years (%s)." % (len(losses), len(ys), ", ".join(map(str, losses))),
        {"loss_years": losses, "years_checked": [y.year for y in ys]},
    )]


def check_negative_cfo(c: Company, t: Thresholds) -> List[Flag]:
    y = c.latest
    if c.is_financial or y is None or y.operating_cash_flow is None or y.operating_cash_flow >= 0:
        return []
    neg = [x.year for x in c.last(3) if x.operating_cash_flow is not None and x.operating_cash_flow < 0]
    return [Flag(
        "negative_cfo", HIGH if len(neg) >= 2 else MEDIUM, y.year, "Negative operating cash flow",
        "Operating cash flow was %.2f; negative in %d of the last %d years. The business is consuming "
        "cash and may need debt or equity to fund operations." % (y.operating_cash_flow, len(neg), len(c.last(3))),
        {"operating_cash_flow": y.operating_cash_flow, "negative_years": neg},
    )]


CHECKS: Dict[str, Callable[[Company, Thresholds], List[Flag]]] = {
    "cfo_weak_vs_profit": check_cfo_vs_profit,
    "receivables_outpacing_revenue": check_receivables,
    "inventory_outpacing_revenue": check_inventory,
    "leverage": check_leverage,
    "low_interest_coverage": check_interest_coverage,
    "rising_debt_falling_profit": check_debt_up_profit_down,
    "promoter_pledge": check_pledge,
    "promoter_holding_falling": check_promoter_holding,
    "equity_dilution": check_dilution,
    "repeated_losses": check_repeated_losses,
    "negative_cfo": check_negative_cfo,
}


def check_company(company: Company, thresholds: Optional[Thresholds] = None) -> List[Flag]:
    """Run all checks; flags are sorted high -> low severity, then by id."""
    t = thresholds or Thresholds()
    flags: List[Flag] = []
    for fn in CHECKS.values():
        flags.extend(fn(company, t))
    flags.sort(key=lambda f: (-SEVERITY_RANK[f.severity], f.id))
    return flags


__all__ = ["Flag", "Thresholds", "CHECKS", "check_company", "LOW", "MEDIUM", "HIGH", "YearData"]
