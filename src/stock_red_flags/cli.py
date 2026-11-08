"""Command-line interface: ``red-flags check`` and ``red-flags screen``."""

from __future__ import annotations

import argparse
import json
import sys
from typing import List, Optional

from . import __version__
from .flags import HIGH, SEVERITY_RANK, check_company
from .models import Company, load_companies
from .scores import altman_z, piotroski, roce, roe
from .screen import METRICS, screen

DISCLAIMER = "Educational use only. Not investment advice."


def _fmt(v: Optional[float], spec: str = "%.2f") -> str:
    return "-" if v is None else spec % v


def report(c: Company) -> dict:
    flags = check_company(c)
    fs = piotroski(c) if len(c.years) >= 2 else None
    z = altman_z(c) if c.years else None
    return {
        "name": c.name,
        "symbol": c.symbol,
        "is_financial": c.is_financial,
        "year": c.latest.year if c.latest else None,
        "flags": [f.to_dict() for f in flags],
        "piotroski": fs.to_dict() if fs else None,
        "altman": z.to_dict() if z else None,
        "roe_pct": None if roe(c) is None else round(roe(c), 2),  # type: ignore[arg-type]
        "roce_pct": None if roce(c) is None else round(roce(c), 2),  # type: ignore[arg-type]
        "disclaimer": DISCLAIMER,
    }


def _print_report(r: dict) -> None:
    title = r["name"] + (" (%s)" % r["symbol"] if r["symbol"] and r["symbol"] != r["name"] else "")
    print("=" * 72)
    print("%s - FY%s%s" % (title, r["year"], "  [financial company]" if r["is_financial"] else ""))
    print("ROE %s%%   ROCE %s%%" % (_fmt(r["roe_pct"], "%.1f"), _fmt(r["roce_pct"], "%.1f")))
    fs = r["piotroski"]
    if fs:
        print("Piotroski F-score: %d (out of %d criteria with data; asset basis: %s)"
              % (fs["score"], fs["evaluated"], fs["asset_basis"]))
        for cr in fs["criteria"]:
            mark = {True: "PASS", False: "fail", None: " n/a"}[cr["passed"]]
            print("   %s  %s" % (mark, cr["name"]))
    z = r["altman"]
    if z:
        if z["z"] is None:
            print("Altman Z-score: not computed (missing: %s)" % "; ".join(z["missing"]))
        else:
            print("Altman Z-score: %.2f (%s zone)" % (z["z"], z["zone"]))
        if r["is_financial"]:
            print("   note: " + z["warnings"][0])
    if not r["flags"]:
        print("Red flags: none triggered")
    else:
        print("Red flags (%d):" % len(r["flags"]))
        for f in r["flags"]:
            print("  [%-6s] %s" % (f["severity"].upper(), f["title"]))
            print("           " + f["explanation"])


def cmd_check(args) -> int:
    companies = load_companies(args.file)
    reports = [report(c) for c in companies]
    if args.json:
        print(json.dumps(reports if len(reports) != 1 else reports[0], indent=2))
    else:
        for r in reports:
            _print_report(r)
        print("\n" + DISCLAIMER)
    if args.fail_on:
        limit = SEVERITY_RANK[args.fail_on]
        if any(SEVERITY_RANK[f["severity"]] >= limit for r in reports for f in r["flags"]):
            return 1
    return 0


def cmd_screen(args) -> int:
    conds: List[str] = list(args.where or [])
    pairs = [("roe", ">=", args.roe_min), ("roce", ">=", args.roce_min), ("de", "<=", args.de_max),
             ("pe", "<=", args.pe_max), ("pe", ">=", args.pe_min), ("market_cap", ">=", args.mcap_min),
             ("market_cap", "<=", args.mcap_max), ("fscore", ">=", args.fscore_min),
             ("high_flags", "<=", args.max_high_flags)]
    conds += ["%s %s %s" % (m, op, v) for m, op, v in pairs if v is not None]
    companies = load_companies(args.file)
    results = screen(companies, conds)
    if args.json:
        print(json.dumps({"conditions": conds, "matches": [r.to_dict() for r in results]}, indent=2))
        return 0
    print("Conditions: %s" % (" AND ".join(conds) or "(none)"))
    print("%d of %d companies match\n" % (len(results), len(companies)))
    if results:
        cols = ["roe", "roce", "de", "pe", "market_cap", "fscore", "high_flags"]
        print("%-16s" % "company" + "".join("%11s" % c for c in cols))
        for r in results:
            print("%-16s" % (r.company.symbol or r.company.name)[:16]
                  + "".join("%11s" % _fmt(r.metrics[c], "%.2f") for c in cols))
    print("\n" + DISCLAIMER)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="red-flags", description="Transparent fundamental red-flag checks. " + DISCLAIMER)
    p.add_argument("--version", action="version", version="%(prog)s " + __version__)
    sub = p.add_subparsers(dest="command", required=True)

    c = sub.add_parser("check", help="red flags, F-score, Z-score, ROE/ROCE for each company in a file")
    c.add_argument("file", help=".json or .csv yearly financials")
    c.add_argument("--json", action="store_true")
    c.add_argument("--fail-on", choices=["low", "medium", "high"],
                   help="exit with status 1 if any flag of this severity or worse fires")
    c.set_defaults(func=cmd_check)

    s = sub.add_parser("screen", help="filter companies with screener-style conditions",
                       epilog="Metrics for --where: " + ", ".join(METRICS))
    s.add_argument("file")
    s.add_argument("--roe-min", type=float)
    s.add_argument("--roce-min", type=float)
    s.add_argument("--de-max", type=float)
    s.add_argument("--pe-min", type=float)
    s.add_argument("--pe-max", type=float)
    s.add_argument("--mcap-min", type=float)
    s.add_argument("--mcap-max", type=float)
    s.add_argument("--fscore-min", type=float)
    s.add_argument("--max-high-flags", type=float)
    s.add_argument("--where", action="append", help="extra condition, e.g. 'interest_coverage>3' (repeatable)")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_screen)
    return p


def main(argv: Optional[List[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except (OSError, ValueError) as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
