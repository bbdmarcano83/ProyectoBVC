"""Read-only release gate for Caracas Bull V5.

This script never backfills, creates tables, updates rows, or enables feature
flags. It checks the persisted Neon datasets that a live V5 release depends on.
Missing verified publication dates are reported as a backtest warning rather
than fabricated to obtain a green release gate.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime

from sqlalchemy import func

from database import DB_PERSISTENCE_MODE, FundamentalDocument, SessionLocal
from services.fundamental_store_v5 import load_latest_validated
from services.fundamental_trend_v5 import compute_fundamental_trend_from_series
from services.fx_history_v5 import FxRateV5
from services.ibc_store_v5 import load_persisted_ibc

EXPECTED_HISTORY = {
    "MVZ.A": {
        "industry": "financial",
        "required_dates": {"2022-12-31", "2023-12-31", "2024-12-31", "2025-12-31"},
        "min_periods": 4,
    },
    "SVS": {
        "industry": "non_financial",
        "required_dates": {"2022-09-30", "2023-09-30", "2024-09-30", "2025-09-30"},
        "min_periods": 4,
    },
    "ICP.B": {
        "industry": "investment_vehicle",
        "required_dates": {"2022-12-31", "2024-12-31", "2025-12-31"},
        "forbidden_dates": {"2023-12-31"},
        "min_periods": 3,
    },
}


def _iso_day(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _flag_is_false(name: str) -> bool:
    return str(os.environ.get(name, "false")).strip().lower() in {"", "0", "false", "no", "off"}


def _fx_state() -> dict:
    with SessionLocal() as db:
        count = int(db.query(func.count(FxRateV5.id)).scalar() or 0)
        latest = db.query(func.max(FxRateV5.rate_date)).scalar()
    latest_day = _iso_day(latest)
    age_days = (date.today() - latest_day).days if latest_day else None
    return {
        "count": count,
        "latest": latest_day.isoformat() if latest_day else None,
        "age_days": age_days,
        "fresh_enough": bool(latest_day and age_days is not None and age_days <= 7),
    }


def _publication_state() -> dict:
    with SessionLocal() as db:
        total = int(db.query(func.count(FundamentalDocument.id)).scalar() or 0)
        dated = int(db.query(func.count(FundamentalDocument.id)).filter(
            FundamentalDocument.published_at.isnot(None),
            FundamentalDocument.published_at != "",
        ).scalar() or 0)
    return {
        "documents": total,
        "with_published_at": dated,
        "coverage_pct": round(dated / total * 100.0, 1) if total else 0.0,
        "backtest_no_lookahead_ready": bool(total and dated == total),
    }


def run_gate() -> dict:
    errors: list[str] = []
    warnings: list[str] = []

    if DB_PERSISTENCE_MODE != "external":
        errors.append("external_neon_database_required")

    if not _flag_is_false("SCORING_ENGINE_V5_ENABLED"):
        errors.append("scoring_v5_must_remain_disabled_during_release_gate")
    if not _flag_is_false("PORTFOLIO_IBC_BENCHMARK_V5_ENABLED"):
        errors.append("portfolio_ibc_v5_must_remain_disabled_during_release_gate")

    points, ibc_meta = load_persisted_ibc()
    ibc_points = len(points or [])
    if ibc_points < 1000:
        errors.append(f"ibc_history_insufficient:{ibc_points}")

    fundamentals, fundamental_meta = load_latest_validated()
    fundamentals = fundamentals if isinstance(fundamentals, dict) else {}
    symbol_state: dict[str, dict] = {}

    for symbol, expected in EXPECTED_HISTORY.items():
        row = fundamentals.get(symbol)
        if not row:
            errors.append(f"missing_fundamental:{symbol}")
            symbol_state[symbol] = {"available": False}
            continue

        dates = {str(x)[:10] for x in (row.get("history_dates_usd") or []) if x}
        periods = int(row.get("history_periods_usd") or 0)
        missing_dates = sorted(expected["required_dates"] - dates)
        forbidden = sorted(expected.get("forbidden_dates", set()) & dates)
        if periods < int(expected["min_periods"]):
            errors.append(f"history_periods_insufficient:{symbol}:{periods}")
        if missing_dates:
            errors.append(f"history_dates_missing:{symbol}:{','.join(missing_dates)}")
        if forbidden:
            errors.append(f"forbidden_history_date:{symbol}:{','.join(forbidden)}")

        trend = compute_fundamental_trend_from_series(row, expected["industry"])
        symbol_state[symbol] = {
            "available": True,
            "latest_as_of": row.get("as_of"),
            "history_periods_usd": periods,
            "history_dates_usd": sorted(dates),
            "trend": trend,
        }

    fx = _fx_state()
    if fx["count"] <= 0:
        errors.append("fx_history_empty")
    elif not fx["fresh_enough"]:
        errors.append(f"fx_history_stale:{fx['latest']}")

    publications = _publication_state()
    if not publications["backtest_no_lookahead_ready"]:
        warnings.append(
            "published_at_incomplete: live validated fundamentals are usable, "
            "but historical no-lookahead backtests must remain fail-closed"
        )

    out = {
        "ready_for_live_release_review": not errors,
        "errors": errors,
        "warnings": warnings,
        "database_mode": DB_PERSISTENCE_MODE,
        "feature_flags": {
            "SCORING_ENGINE_V5_ENABLED": os.environ.get("SCORING_ENGINE_V5_ENABLED", "false"),
            "PORTFOLIO_IBC_BENCHMARK_V5_ENABLED": os.environ.get("PORTFOLIO_IBC_BENCHMARK_V5_ENABLED", "false"),
        },
        "ibc": {"points": ibc_points, "meta": ibc_meta},
        "fx": fx,
        "fundamentals": symbol_state,
        "fundamental_meta": fundamental_meta,
        "publication_dates": publications,
        "policy": {
            "live_release": "requires all hard gates green",
            "backtest": "published_at required; never inferred from filename/auditor date",
        },
    }
    return out


def main() -> int:
    result = run_gate()
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result["ready_for_live_release_review"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
