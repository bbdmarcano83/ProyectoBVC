"""Auto-revisión fail-closed para backfill fundamental V5.

Sólo auto-selecciona cuando la evidencia es inequívoca. Para balance busca una
combinación única Activos = Pasivos + Patrimonio dentro de tolerancia. Para otros
campos sólo acepta cuando todos los candidatos útiles representan el mismo valor.
Nunca fuerza una selección ambigua.
"""
from __future__ import annotations

from itertools import product
from math import isfinite


def _num(v):
    try:
        x = float(v)
        return x if isfinite(x) else None
    except (TypeError, ValueError):
        return None


def _unique_value_index(options: list[dict], *, rel_tol: float = 1e-9) -> int | None:
    values = []
    for idx, option in enumerate(options or []):
        value = _num(option.get("value")) if isinstance(option, dict) else None
        if value is not None:
            values.append((idx, value))
    if not values:
        return None
    base = values[0][1]
    scale = max(1.0, abs(base))
    if all(abs(v - base) <= rel_tol * scale for _, v in values[1:]):
        return values[0][0]
    return None


def _balance_selection(fields: dict[str, list[dict]], tolerance_pct: float = 1.0) -> dict[str, int] | None:
    assets = fields.get("total_assets") or []
    liabilities = fields.get("total_liabilities") or []
    equity = fields.get("equity") or []
    matches = []
    for ai, li, ei in product(range(len(assets)), range(len(liabilities)), range(len(equity))):
        a = _num(assets[ai].get("value")); l = _num(liabilities[li].get("value")); e = _num(equity[ei].get("value"))
        if a is None or l is None or e is None or abs(a) < 1e-12:
            continue
        error_pct = abs(a - (l + e)) / abs(a) * 100.0
        if error_pct <= tolerance_pct:
            matches.append((error_pct, ai, li, ei))
    if not matches:
        return None
    matches.sort(key=lambda x: x[0])
    best = matches[0]
    # Exige solución única: otra combinación prácticamente igual implica ambigüedad.
    if len(matches) > 1 and abs(matches[1][0] - best[0]) <= 0.05:
        if matches[1][1:] != best[1:]:
            return None
    return {"total_assets": best[1], "total_liabilities": best[2], "equity": best[3]}


def propose_fail_closed_selections(review: dict) -> dict:
    if not review.get("valid"):
        return {"valid": False, "reason": "invalid_review_package", "selections": {}}
    fields = review.get("fields") or {}
    selections: dict[str, int] = {}
    balance = _balance_selection(fields)
    if balance:
        selections.update(balance)

    for field, options in fields.items():
        if field in selections:
            continue
        idx = _unique_value_index(options)
        if idx is not None:
            selections[field] = idx

    kind = str(review.get("industry_type") or "")
    required = {
        "financial": {"total_assets", "equity", "net_income"},
        "non_financial": {"total_assets", "equity", "net_income"},
        "investment_vehicle": {"total_assets", "equity"},
    }.get(kind, set())
    missing = sorted(required - set(selections))
    return {
        "valid": not missing,
        "selections": selections,
        "required": sorted(required),
        "missing_required": missing,
        "reason": None if not missing else "ambiguous_or_missing_required_fields",
        "method": "unique_accounting_equation_and_unique_values",
    }
