"""Professional open-portfolio analytics for Caracas Bull V5.

This layer is intentionally separate from the IBC benchmark engine. It reuses
its FIFO lot reconstruction and adds investor-facing USD metrics without
changing positions, transactions or benchmark methodology.

USD calculations are fail-closed: a lot contributes to USD P/L only when its
historical BCV rate and the current BCV rate are both available. Missing FX
never falls back to today's rate for historical cost.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Iterable

from services.portfolio_benchmark_v5 import Lot, reconstruct_open_lots


def _f(value: Any, default: float = 0.0) -> float:
    try:
        return float(value if value is not None else default)
    except (TypeError, ValueError):
        return default


def _date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _fallback_lot(position: dict) -> Lot | None:
    symbol = str(position.get("simb") or position.get("simbolo") or "").upper()
    qty = max(0.0, _f(position.get("cantidad")))
    cost_bs = max(0.0, _f(position.get("costo_total")))
    acquired_on = _date(position.get("creado_en") or position.get("fecha_inicio"))
    fx_start = _f(position.get("fx_inicio") or position.get("tasa_bcv_inicio")) or None
    if not symbol or qty <= 0 or cost_bs <= 0 or not acquired_on:
        return None
    return Lot(symbol=symbol, qty=qty, cost_bs=cost_bs, acquired_on=acquired_on, fx_start=fx_start)


def _fee_metrics(transactions: Iterable[dict]) -> dict:
    fee_bs = 0.0
    fee_usd = 0.0
    fee_usd_covered_bs = 0.0
    for tx in transactions or []:
        fee = max(0.0, _f(tx.get("fee_total")))
        if fee <= 0:
            continue
        fee_bs += fee
        fx = _f(tx.get("tasa_bcv"))
        if fx > 0:
            fee_usd += fee / fx
            fee_usd_covered_bs += fee
    return {
        "fees_total_bs": round(fee_bs, 2),
        "fees_total_usd_historical": round(fee_usd, 4) if fee_usd_covered_bs > 0 else None,
        "fees_usd_coverage_pct": round(fee_usd_covered_bs / fee_bs * 100.0, 1) if fee_bs > 0 else 100.0,
    }


def build_professional_open_metrics(
    positions: Iterable[dict],
    transactions: Iterable[dict],
    *,
    current_fx: float | None,
    qty_tolerance_pct: float = 1.0,
) -> dict:
    """Return professional Bs/USD metrics for the currently open portfolio.

    Cost in USD is measured at each surviving FIFO lot's historical BCV rate.
    Current USD value uses current BCV. Therefore USD P/L reflects both the
    underlying share performance and the bolivar/USD move without contaminating
    historical cost with today's exchange rate.
    """
    pos = [dict(p) for p in positions or []]
    tx = [dict(t) for t in transactions or []]
    fx_now = _f(current_fx)

    total_declared_cost_bs = sum(max(0.0, _f(p.get("costo_total"))) for p in pos)
    total_market_bs = sum(max(0.0, _f(p.get("val_mkt") or p.get("valor_actual"))) for p in pos)
    total_reconciled_cost_bs = 0.0
    total_reconciled_current_bs = 0.0
    total_usd_covered_cost_bs = 0.0
    total_cost_usd = 0.0
    total_value_usd = 0.0
    details: list[dict] = []

    for p in pos:
        symbol = str(p.get("simb") or p.get("simbolo") or "").upper()
        qty_now = max(0.0, _f(p.get("cantidad")))
        position_cost = max(0.0, _f(p.get("costo_total")))
        current_value_bs = max(0.0, _f(p.get("val_mkt") or p.get("valor_actual")))
        if not symbol or qty_now <= 0:
            continue

        lots = reconstruct_open_lots(tx, symbol)
        lot_qty = sum(max(0.0, lot.qty) for lot in lots)
        tolerance = max(1e-8, qty_now * qty_tolerance_pct / 100.0)
        source = "bitacora_fifo"
        if not lots or abs(lot_qty - qty_now) > tolerance:
            fallback = _fallback_lot(p)
            lots = [fallback] if fallback else []
            source = "position_created_fallback" if fallback else "unreconciled"

        if not lots:
            details.append({
                "symbol": symbol,
                "available": False,
                "usd_comparable": False,
                "reason": "sin_lotes_reconciliables",
                "cost_bs": round(position_cost, 2),
                "current_value_bs": round(current_value_bs, 2),
                "weight_current_pct": round(current_value_bs / total_market_bs * 100.0, 2) if total_market_bs > 0 else 0.0,
            })
            continue

        lot_total_qty = sum(max(0.0, lot.qty) for lot in lots)
        lot_total_cost = sum(max(0.0, lot.cost_bs) for lot in lots)
        if lot_total_qty <= 0 or lot_total_cost <= 0:
            details.append({"symbol": symbol, "available": False, "usd_comparable": False, "reason": "costo_lotes_invalido"})
            continue

        total_reconciled_cost_bs += lot_total_cost
        total_reconciled_current_bs += current_value_bs

        usd_cost_bs = 0.0
        cost_usd = 0.0
        value_usd = 0.0
        usd_lots = 0
        for lot in lots:
            if lot.qty <= 0 or lot.cost_bs <= 0 or not lot.fx_start or lot.fx_start <= 0 or fx_now <= 0:
                continue
            share_bs = current_value_bs * (lot.qty / lot_total_qty)
            usd_cost_bs += lot.cost_bs
            cost_usd += lot.cost_bs / lot.fx_start
            value_usd += share_bs / fx_now
            usd_lots += 1

        total_usd_covered_cost_bs += usd_cost_bs
        total_cost_usd += cost_usd
        total_value_usd += value_usd

        pnl_bs = current_value_bs - lot_total_cost
        return_bs_pct = (current_value_bs / lot_total_cost - 1.0) * 100.0
        usd_comparable = bool(usd_cost_bs > 0 and cost_usd > 0 and fx_now > 0)
        pnl_usd = value_usd - cost_usd if usd_comparable else None
        return_usd_pct = (value_usd / cost_usd - 1.0) * 100.0 if usd_comparable else None
        effective_entry_fx = usd_cost_bs / cost_usd if usd_comparable and cost_usd > 0 else None
        fx_change_pct = (fx_now / effective_entry_fx - 1.0) * 100.0 if effective_entry_fx and effective_entry_fx > 0 else None
        fx_effect_pp = return_usd_pct - return_bs_pct if return_usd_pct is not None else None

        details.append({
            "symbol": symbol,
            "available": True,
            "source": source,
            "cost_bs": round(lot_total_cost, 2),
            "current_value_bs": round(current_value_bs, 2),
            "pnl_bs": round(pnl_bs, 2),
            "return_bs_pct": round(return_bs_pct, 2),
            "weight_current_pct": round(current_value_bs / total_market_bs * 100.0, 2) if total_market_bs > 0 else 0.0,
            "usd_comparable": usd_comparable,
            "usd_covered_lots": usd_lots,
            "usd_coverage_pct": round(usd_cost_bs / lot_total_cost * 100.0, 1),
            "cost_usd_historical": round(cost_usd, 4) if usd_comparable else None,
            "current_value_usd": round(value_usd, 4) if usd_comparable else None,
            "pnl_usd": round(pnl_usd, 4) if pnl_usd is not None else None,
            "return_usd_pct": round(return_usd_pct, 2) if return_usd_pct is not None else None,
            "effective_entry_fx": round(effective_entry_fx, 6) if effective_entry_fx else None,
            "current_fx": round(fx_now, 6) if fx_now > 0 else None,
            "fx_change_pct": round(fx_change_pct, 2) if fx_change_pct is not None else None,
            "fx_effect_pp": round(fx_effect_pp, 2) if fx_effect_pp is not None else None,
        })

    pnl_bs_total = total_reconciled_current_bs - total_reconciled_cost_bs
    pnl_usd_total = total_value_usd - total_cost_usd if total_cost_usd > 0 else None
    return_bs_total = (total_reconciled_current_bs / total_reconciled_cost_bs - 1.0) * 100.0 if total_reconciled_cost_bs > 0 else None
    return_usd_total = (total_value_usd / total_cost_usd - 1.0) * 100.0 if total_cost_usd > 0 else None
    effective_entry_fx = total_usd_covered_cost_bs / total_cost_usd if total_cost_usd > 0 else None
    fx_change_total = (fx_now / effective_entry_fx - 1.0) * 100.0 if effective_entry_fx and fx_now > 0 else None
    fx_effect_total = return_usd_total - return_bs_total if return_usd_total is not None and return_bs_total is not None else None

    for row in details:
        if not row.get("available"):
            continue
        pnl_bs = row.get("pnl_bs")
        pnl_usd = row.get("pnl_usd")
        row["pnl_contribution_bs_pct"] = round(_f(pnl_bs) / pnl_bs_total * 100.0, 2) if abs(pnl_bs_total) > 1e-12 else None
        row["pnl_contribution_usd_pct"] = round(_f(pnl_usd) / pnl_usd_total * 100.0, 2) if pnl_usd is not None and pnl_usd_total is not None and abs(pnl_usd_total) > 1e-12 else None

    usd_rows = [r for r in details if r.get("pnl_usd") is not None]
    best = max(usd_rows, key=lambda r: _f(r.get("pnl_usd")), default=None)
    worst = min(usd_rows, key=lambda r: _f(r.get("pnl_usd")), default=None)
    fees = _fee_metrics(tx)

    return {
        "available": bool(pos),
        "method": "open_positions_fifo_historical_bcv",
        "current_fx": round(fx_now, 6) if fx_now > 0 else None,
        "declared_cost_bs": round(total_declared_cost_bs, 2),
        "market_value_bs": round(total_market_bs, 2),
        "reconciled_cost_bs": round(total_reconciled_cost_bs, 2),
        "reconciled_market_value_bs": round(total_reconciled_current_bs, 2),
        "pnl_bs": round(pnl_bs_total, 2),
        "return_bs_pct": round(return_bs_total, 2) if return_bs_total is not None else None,
        "usd_coverage_pct": round(total_usd_covered_cost_bs / max(1.0, total_reconciled_cost_bs) * 100.0, 1),
        "cost_usd_historical": round(total_cost_usd, 4) if total_cost_usd > 0 else None,
        "market_value_usd": round(total_value_usd, 4) if total_cost_usd > 0 else None,
        "pnl_usd": round(pnl_usd_total, 4) if pnl_usd_total is not None else None,
        "return_usd_pct": round(return_usd_total, 2) if return_usd_total is not None else None,
        "effective_entry_fx": round(effective_entry_fx, 6) if effective_entry_fx else None,
        "fx_change_pct": round(fx_change_total, 2) if fx_change_total is not None else None,
        "fx_effect_pp": round(fx_effect_total, 2) if fx_effect_total is not None else None,
        "best_contributor_usd": {"symbol": best["symbol"], "pnl_usd": best["pnl_usd"]} if best else None,
        "worst_contributor_usd": {"symbol": worst["symbol"], "pnl_usd": worst["pnl_usd"]} if worst else None,
        "positions": details,
        **fees,
        "notes": [
            "Costo USD usa BCV historico de cada lote FIFO abierto.",
            "Valor USD usa BCV actual; nunca se usa la tasa actual para reconstruir costo historico.",
            "FX effect pp es retorno USD menos retorno nominal Bs; es una descomposicion informativa, no una suma contable independiente.",
        ],
    }
