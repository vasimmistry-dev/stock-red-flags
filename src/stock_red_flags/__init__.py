"""stock-red-flags: transparent fundamental red-flag and quality checks.

Quick start::

    from stock_red_flags import load_companies, check_company, piotroski
    company = load_companies("examples/company.json")[0]
    for flag in check_company(company):
        print(flag.severity, flag.id, flag.explanation)
"""

__version__ = "0.1.0"

from .flags import CHECKS, HIGH, LOW, MEDIUM, Flag, Thresholds, check_company  # noqa: E402
from .models import Company, YearData, companies_from_json, load_companies  # noqa: E402
from .scores import (  # noqa: E402
    FScore, ZScore, altman_z, current_ratio, debt_to_equity, interest_coverage, pe_ratio, piotroski, roce, roe,
)
from .screen import METRICS, compute_metrics, parse_condition, screen  # noqa: E402

__all__ = [
    "Company", "YearData", "load_companies", "companies_from_json",
    "Flag", "Thresholds", "CHECKS", "check_company", "LOW", "MEDIUM", "HIGH",
    "FScore", "ZScore", "piotroski", "altman_z", "roe", "roce",
    "debt_to_equity", "interest_coverage", "current_ratio", "pe_ratio",
    "METRICS", "compute_metrics", "parse_condition", "screen",
    "__version__",
]
