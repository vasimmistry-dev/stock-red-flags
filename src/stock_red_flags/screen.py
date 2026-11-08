"""Screener-style filtering, e.g. ``roe > 15`` and ``de < 0.5``."""

from __future__ import annotations

import operator
import re
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple, Union

from .flags import HIGH, Thresholds, check_company
from .models import Company
from .scores import altman_z, current_ratio, debt_to_equity, interest_coverage, pe_ratio, piotroski, roce, roe

#: metric name -> description (units)
METRICS = {
    "roe": "return on average equity, %",
    "roce": "EBIT / average (equity + debt), %",
    "de": "total debt / equity",
    "pe": "market value / net profit (loss-makers excluded)",
    "market_cap": "market value, in the file's money unit",
    "interest_coverage": "EBIT / interest expense",
    "current_ratio": "current assets / current liabilities",
    "sales_growth": "latest YoY revenue growth, %",
    "profit_growth": "latest YoY net profit growth, % (previous profit must be > 0)",
    "promoter_holding": "promoter holding, %",
    "pledge": "promoter shares pledged, %",
    "fscore": "Piotroski F-score (0-9)",
    "zscore": "Altman Z-score",
    "red_flags": "number of red flags",
    "high_flags": "number of high-severity red flags",
}

ALIASES = {"d/e": "de", "debt_to_equity": "de", "mcap": "market_cap", "market_value": "market_cap",
           "p/e": "pe", "f_score": "fscore", "z_score": "zscore"}

OPS: Dict[str, Callable[[float, float], bool]] = {
    ">=": operator.ge, "<=": operator.le, "!=": operator.ne,
    "==": operator.eq, ">": operator.gt, "<": operator.lt, "=": operator.eq,
}

_COND = re.compile(r"^\s*([A-Za-z_/]+)\s*(>=|<=|!=|==|>|<|=)\s*(-?[0-9]*\.?[0-9]+)\s*$")

Condition = Tuple[str, str, float]


def parse_condition(text: str) -> Condition:
    """Parse ``"roe>15"`` / ``"de <= 0.5"`` into ``(metric, op, value)``."""
    m = _COND.match(text)
    if not m:
        raise ValueError("Cannot parse condition %r (expected e.g. 'roe > 15')" % text)
    name = m.group(1).lower()
    name = ALIASES.get(name, name)
    if name not in METRICS:
        raise ValueError("Unknown metric %r. Available: %s" % (m.group(1), ", ".join(METRICS)))
    return name, m.group(2), float(m.group(3))


def _growth_pct(prev: Optional[float], cur: Optional[float]) -> Optional[float]:
    if prev is None or cur is None or prev <= 0:
        return None
    return 100.0 * (cur / prev - 1)


def compute_metrics(c: Company, thresholds: Optional[Thresholds] = None) -> Dict[str, Optional[float]]:
    """All screenable metrics for the latest year (``None`` where data is missing)."""
    y = c.latest
    if y is None:
        return {k: None for k in METRICS}
    p = c.years[-2] if len(c.years) >= 2 else None
    flags = check_company(c, thresholds)
    fs = piotroski(c) if p is not None else None
    z = altman_z(c)
    return {
        "roe": roe(c),
        "roce": roce(c),
        "de": debt_to_equity(y),
        "pe": pe_ratio(y),
        "market_cap": y.market_value,
        "interest_coverage": interest_coverage(y),
        "current_ratio": current_ratio(y),
        "sales_growth": _growth_pct(p.revenue, y.revenue) if p else None,
        "profit_growth": _growth_pct(p.net_profit, y.net_profit) if p else None,
        "promoter_holding": y.promoter_holding_pct,
        "pledge": y.promoter_pledged_pct,
        "fscore": float(fs.score) if fs is not None else None,
        "zscore": z.z,
        "red_flags": float(len(flags)),
        "high_flags": float(sum(1 for f in flags if f.severity == HIGH)),
    }


@dataclass
class ScreenResult:
    company: Company
    metrics: Dict[str, Optional[float]]

    def to_dict(self) -> dict:
        return {
            "name": self.company.name,
            "symbol": self.company.symbol,
            "metrics": {k: (None if v is None else round(v, 4)) for k, v in self.metrics.items()},
        }


def screen(
    companies: Iterable[Company],
    conditions: Sequence[Union[str, Condition]] = (),
    thresholds: Optional[Thresholds] = None,
) -> List[ScreenResult]:
    """Keep companies meeting *every* condition.

    A company whose metric is ``None`` (missing data, loss-maker for P/E,
    negative equity for D/E ...) fails that condition rather than passing it.
    """
    conds = [parse_condition(c) if isinstance(c, str) else c for c in conditions]
    out = []
    for comp in companies:
        m = compute_metrics(comp, thresholds)
        ok = True
        for name, op, value in conds:
            v = m.get(name)
            if v is None or not OPS[op](v, value):
                ok = False
                break
        if ok:
            out.append(ScreenResult(comp, m))
    return out
