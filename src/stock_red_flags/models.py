"""Company / yearly-financials data model and JSON / CSV loaders.

All money values for one company must use the same unit (for example
Rs crore). ``shares_outstanding`` must be in a unit such that
``price * shares_outstanding`` gives market value in that same money unit
(e.g. shares in crore when money is in Rs crore). Alternatively supply
``market_cap`` directly.
"""

from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass, field, fields
from typing import Any, Dict, Iterable, List, Optional, Union

NUMERIC_FIELDS = (
    "revenue",
    "net_profit",
    "operating_cash_flow",
    "total_debt",
    "equity",
    "interest_expense",
    "ebit",
    "receivables",
    "inventory",
    "total_assets",
    "current_assets",
    "current_liabilities",
    "shares_outstanding",
    "promoter_holding_pct",
    "promoter_pledged_pct",
    "price",
    # optional extras used by quality scores
    "gross_profit",
    "retained_earnings",
    "total_liabilities",
    "market_cap",
)


@dataclass
class YearData:
    year: int
    revenue: Optional[float] = None
    net_profit: Optional[float] = None
    operating_cash_flow: Optional[float] = None
    total_debt: Optional[float] = None
    equity: Optional[float] = None
    interest_expense: Optional[float] = None
    ebit: Optional[float] = None
    receivables: Optional[float] = None
    inventory: Optional[float] = None
    total_assets: Optional[float] = None
    current_assets: Optional[float] = None
    current_liabilities: Optional[float] = None
    shares_outstanding: Optional[float] = None
    promoter_holding_pct: Optional[float] = None
    promoter_pledged_pct: Optional[float] = None
    price: Optional[float] = None
    gross_profit: Optional[float] = None
    retained_earnings: Optional[float] = None
    total_liabilities: Optional[float] = None
    market_cap: Optional[float] = None

    @property
    def market_value(self) -> Optional[float]:
        if self.market_cap is not None:
            return self.market_cap
        if self.price is not None and self.shares_outstanding is not None:
            return self.price * self.shares_outstanding
        return None

    @property
    def liabilities(self) -> Optional[float]:
        if self.total_liabilities is not None:
            return self.total_liabilities
        if self.total_assets is not None and self.equity is not None:
            return self.total_assets - self.equity
        return None


@dataclass
class Company:
    name: str
    years: List[YearData]
    symbol: str = ""
    is_financial: bool = False
    meta: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.years = sorted(self.years, key=lambda y: y.year)
        seen = set()
        for y in self.years:
            if y.year in seen:
                raise ValueError("%s: duplicate year %s" % (self.label, y.year))
            seen.add(y.year)

    @property
    def label(self) -> str:
        return self.symbol or self.name

    @property
    def latest(self) -> Optional[YearData]:
        return self.years[-1] if self.years else None

    def last(self, n: int) -> List[YearData]:
        return self.years[-n:]


def _num(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError("boolean is not a number: %r" % value)
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    if text in ("", "-", "NA", "N/A", "null", "None"):
        return None
    return float(text)


def _bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "y")


def year_from_dict(d: Dict[str, Any]) -> YearData:
    if "year" not in d:
        raise ValueError("each yearly record needs a 'year': %r" % d)
    kwargs = {"year": int(float(str(d["year"]).strip()))}
    for name in NUMERIC_FIELDS:
        if name in d:
            kwargs[name] = _num(d[name])
    return YearData(**kwargs)


def company_from_dict(d: Dict[str, Any]) -> Company:
    years = [year_from_dict(y) for y in d.get("years", [])]
    known = {"name", "symbol", "is_financial", "years"}
    return Company(
        name=str(d.get("name") or d.get("symbol") or "unnamed"),
        symbol=str(d.get("symbol") or ""),
        is_financial=_bool(d.get("is_financial", False)),
        years=years,
        meta={k: v for k, v in d.items() if k not in known},
    )


def companies_from_json(data: Any) -> List[Company]:
    """Accepts one company object, a list of them, or ``{"companies": [...]}``."""
    if isinstance(data, dict) and "companies" in data:
        data = data["companies"]
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        raise ValueError("expected a company object or a list of companies")
    return [company_from_dict(c) for c in data]


def companies_from_csv_rows(rows: Iterable[Dict[str, Any]]) -> List[Company]:
    """One row per company-year. Rows are grouped by ``symbol`` (or ``name``)."""
    groups: Dict[str, Dict[str, Any]] = {}
    for raw in rows:
        row = {(k or "").strip(): v for k, v in raw.items()}
        key = (row.get("symbol") or row.get("name") or "").strip()
        if not key:
            raise ValueError("CSV rows need a 'symbol' or 'name' column")
        g = groups.setdefault(key, {"name": row.get("name") or key, "symbol": row.get("symbol") or "",
                                    "is_financial": False, "years": []})
        if _bool(row.get("is_financial", False)):
            g["is_financial"] = True
        g["years"].append(row)
    return [company_from_dict(g) for g in groups.values()]


def load_companies(path: Union[str, os.PathLike]) -> List[Company]:
    """Load companies from a ``.json`` or ``.csv`` file."""
    p = str(path)
    with open(p, newline="", encoding="utf-8-sig") as fh:
        if p.lower().endswith(".csv"):
            return companies_from_csv_rows(csv.DictReader(fh))
        return companies_from_json(json.load(fh))


def field_names() -> List[str]:
    return [f.name for f in fields(YearData)]
