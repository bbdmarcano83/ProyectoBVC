"""Benchmark de cartera abierta vs IBC para Caracas Bull V5.

Objetivo: responder si el portafolio abierto agrega valor frente al Índice
Bursátil Caracas usando períodos comparables y, cuando hay FX histórico, tanto
Bs nominales como USD.

El motor es puro: no descarga datos ni modifica posiciones. Recibe:
- posiciones actuales con valor de mercado/costo;
- transacciones históricas del usuario;
- serie histórica IBC validada;
- FX histórico por transacción y FX actual.

Para posiciones con bitácora completa reconstruye lotes FIFO remanentes. Si la
bitácora no reconcilia con la cantidad abierta, hace fail-closed para el detalle
de esa posición y permite un fallback explícito por fecha de creación.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Iterable


@dataclass
class Lot:
    symbol: str
    qty: float
    cost_bs: float
    acquired_on: date
    fx_start: float | None = None


def _f(v: Any, default: float = 0.0) -> float:
    try:
        return float(v if v is not None else default)
    except (TypeError, ValueError):
        return default


def _date(v: Any) -> date | None:
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if not v:
        return None
    s = str(v).strip()[:10]
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def normalize_ibc_points(points: Iterable[dict]) -> list[tuple[date, float]]:
    """Normaliza/ordena una serie IBC y elimina puntos inválidos/duplicados."""
    by_day: dict[date, float] = {}
    for p in points or []:
        d = _date(p.get("date") or p.get("fecha") or p.get("as_of"))
        level = _f(p.get("close") or p.get("cierre") or p.get("value") or p.get("nivel"))
        if d and level > 0:
            by_day[d] = level
    return sorted(by_day.items(), key=lambda x: x[0])


def ibc_asof(points: list[tuple[date, float]], target: date) -> float | None:
    """Último cierre IBC conocido <= target (útil para fines de semana/feriados)."""
    out = None
    for d, level in points:
        if d > target:
            break
        out = level
    return out


def _transaction_net_cost(tx: dict) -> float:
    """Costo desembolsado de compra; usa `neto` si ya fue calculado por bitácora."""
    neto = _f(tx.get("neto"))
    if neto > 0:
        return neto
    qty = _f(tx.get("cantidad")); price = _f(tx.get("precio"))
    gross = qty * price
    fee = _f(tx.get("fee_total"))
    if fee > 0:
        return gross + fee
    return gross


def reconstruct_open_lots(transactions: Iterable[dict], symbol: str) -> list[Lot]:
    """Reconstruye lotes abiertos FIFO para un símbolo a partir de la bitácora."""
    symbol = str(symbol or "").upper()
    txs = []
    for raw in transactions or []:
        if str(raw.get("simbolo") or "").upper() != symbol:
            continue
        d = _date(raw.get("fecha"))
        if not d:
            continue
        txs.append((d, raw))
    txs.sort(key=lambda x: x[0])

    lots: list[Lot] = []
    for d, tx in txs:
        kind = str(tx.get("tipo") or "").lower()
        qty = max(0.0, _f(tx.get("cantidad")))
        if qty <= 0:
            continue
        if kind == "compra":
            cost = _transaction_net_cost(tx)
            fx = _f(tx.get("tasa_bcv")) or None
            lots.append(Lot(symbol, qty, cost, d, fx))
            continue
        if kind != "venta":
            continue

        remaining = qty
        while remaining > 1e-9 and lots:
            lot = lots[0]
            used = min(remaining, lot.qty)
            ratio = used / lot.qty if lot.qty > 0 else 0.0
            lot.qty -= used
            lot.cost_bs *= max(0.0, 1.0 - ratio)
            remaining -= used
            if lot.qty <= 1e-9:
                lots.pop(0)
    return lots


def _fallback_lot(position: dict) -> Lot | None:
    symbol = str(position.get("simb") or position.get("simbolo") or "").upper()
    qty = max(0.0, _f(position.get("cantidad")))
    cost_bs = max(0.0, _f(position.get("costo_total")))
    d = _date(position.get("creado_en") or position.get("fecha_inicio"))
    fx = _f(position.get("fx_inicio") or position.get("tasa_bcv_inicio")) or None
    if not symbol or qty <= 0 or cost_bs <= 0 or not d:
        return None
    return Lot(symbol, qty, cost_bs, d, fx)


def compare_open_portfolio_to_ibc(
    positions: Iterable[dict],
    transactions: Iterable[dict],
    ibc_points: Iterable[dict],
    *,
    current_ibc: float | None = None,
    current_fx: float | None = None,
    qty_tolerance_pct: float = 1.0,
) -> dict:
    """Compara cartera abierta con un benchmark IBC de flujos/fechas equivalentes.

    Retornos Bs usan el costo histórico de los lotes remanentes. Retornos USD
    sólo se calculan cuando cada lote tiene FX histórico y existe FX actual.
    """
    pos = [dict(p) for p in positions or []]
    tx = [dict(t) for t in transactions or []]
    points = normalize_ibc_points(ibc_points)
    if not pos:
        return {"available": False, "reason": "sin_posiciones", "coverage_pct": 0.0}
    if not points:
        return {"available": False, "reason": "sin_historia_ibc", "coverage_pct": 0.0}

    terminal_ibc = _f(current_ibc)
    if terminal_ibc <= 0:
        terminal_ibc = points[-1][1]

    total_cost_bs = 0.0
    total_current_bs = 0.0
    ibc_terminal_bs = 0.0
    total_initial_usd = 0.0
    total_current_usd = 0.0
    ibc_terminal_usd = 0.0
    usd_cost_covered_bs = 0.0
    benchmark_cost_covered_bs = 0.0
    details: list[dict] = []

    for p in pos:
        symbol = str(p.get("simb") or p.get("simbolo") or "").upper()
        qty_now = max(0.0, _f(p.get("cantidad")))
        current_value = max(0.0, _f(p.get("val_mkt") or p.get("valor_actual")))
        position_cost = max(0.0, _f(p.get("costo_total")))
        if not symbol or qty_now <= 0 or current_value < 0:
            continue

        lots = reconstruct_open_lots(tx, symbol)
        lot_qty = sum(l.qty for l in lots)
        tolerance = max(1e-8, qty_now * qty_tolerance_pct / 100.0)
        source = "bitacora_fifo"
        if not lots or abs(lot_qty - qty_now) > tolerance:
            fallback = _fallback_lot(p)
            lots = [fallback] if fallback else []
            source = "position_created_fallback" if fallback else "unreconciled"

        if not lots:
            details.append({"symbol": symbol, "available": False, "reason": "sin_fecha_entrada_reconciliable"})
            total_current_bs += current_value
            total_cost_bs += position_cost
            continue

        lot_total_cost = sum(max(0.0, l.cost_bs) for l in lots)
        if lot_total_cost <= 0:
            details.append({"symbol": symbol, "available": False, "reason": "costo_lotes_invalido"})
            continue

        # Si bitácora y costo actual difieren sólo por redondeo/edición, el benchmark
        # conserva el costo de los lotes; el P/L mostrado por cartera sigue intacto.
        pos_ibc_terminal = 0.0
        pos_initial_usd = 0.0
        pos_ibc_terminal_usd = 0.0
        all_usd = bool(current_fx and _f(current_fx) > 0)
        weighted_start_num = 0.0
        weighted_start_den = 0.0

        for lot in lots:
            start_ibc = ibc_asof(points, lot.acquired_on)
            if not start_ibc or start_ibc <= 0:
                continue
            benchmark_cost_covered_bs += lot.cost_bs
            terminal = lot.cost_bs * terminal_ibc / start_ibc
            pos_ibc_terminal += terminal
            weighted_start_num += start_ibc * lot.cost_bs
            weighted_start_den += lot.cost_bs

            if lot.fx_start and lot.fx_start > 0 and current_fx and _f(current_fx) > 0:
                initial_usd = lot.cost_bs / lot.fx_start
                terminal_usd = terminal / _f(current_fx)
                pos_initial_usd += initial_usd
                pos_ibc_terminal_usd += terminal_usd
                usd_cost_covered_bs += lot.cost_bs
            else:
                all_usd = False

        if pos_ibc_terminal <= 0:
            details.append({"symbol": symbol, "available": False, "reason": "sin_ibc_para_fecha_entrada"})
            continue

        total_cost_bs += lot_total_cost
        total_current_bs += current_value
        ibc_terminal_bs += pos_ibc_terminal

        current_usd = current_value / _f(current_fx) if all_usd and _f(current_fx) > 0 else None
        if all_usd and pos_initial_usd > 0 and current_usd is not None:
            total_initial_usd += pos_initial_usd
            total_current_usd += current_usd
            ibc_terminal_usd += pos_ibc_terminal_usd

        weighted_start = weighted_start_num / weighted_start_den if weighted_start_den else None
        details.append({
            "symbol": symbol,
            "available": True,
            "source": source,
            "cost_bs": round(lot_total_cost, 2),
            "current_value_bs": round(current_value, 2),
            "ibc_terminal_equivalent_bs": round(pos_ibc_terminal, 2),
            "weighted_ibc_start": round(weighted_start, 4) if weighted_start else None,
            "ibc_current": round(terminal_ibc, 4),
            "usd_comparable": bool(all_usd and pos_initial_usd > 0),
        })

    if total_cost_bs <= 0 or ibc_terminal_bs <= 0:
        return {
            "available": False,
            "reason": "cobertura_insuficiente",
            "coverage_pct": round(benchmark_cost_covered_bs / max(1.0, total_cost_bs) * 100.0, 1),
            "positions": details,
        }

    portfolio_return_bs = (total_current_bs / total_cost_bs - 1.0) * 100.0
    ibc_return_bs = (ibc_terminal_bs / total_cost_bs - 1.0) * 100.0
    out = {
        "available": True,
        "benchmark": "IBC",
        "method": "open_positions_cashflow_matched_fifo",
        "portfolio_return_bs_pct": round(portfolio_return_bs, 2),
        "ibc_return_bs_pct": round(ibc_return_bs, 2),
        "alpha_bs_pp": round(portfolio_return_bs - ibc_return_bs, 2),
        "beats_ibc_bs": portfolio_return_bs > ibc_return_bs,
        "coverage_pct": round(benchmark_cost_covered_bs / max(1.0, total_cost_bs) * 100.0, 1),
        "ibc_current": round(terminal_ibc, 4),
        "positions": details,
    }

    if total_initial_usd > 0 and total_current_usd > 0 and ibc_terminal_usd > 0:
        portfolio_return_usd = (total_current_usd / total_initial_usd - 1.0) * 100.0
        ibc_return_usd = (ibc_terminal_usd / total_initial_usd - 1.0) * 100.0
        out.update({
            "portfolio_return_usd_pct": round(portfolio_return_usd, 2),
            "ibc_return_usd_pct": round(ibc_return_usd, 2),
            "alpha_usd_pp": round(portfolio_return_usd - ibc_return_usd, 2),
            "beats_ibc_usd": portfolio_return_usd > ibc_return_usd,
            "usd_coverage_pct": round(usd_cost_covered_bs / max(1.0, total_cost_bs) * 100.0, 1),
        })
    else:
        out.update({
            "portfolio_return_usd_pct": None,
            "ibc_return_usd_pct": None,
            "alpha_usd_pp": None,
            "beats_ibc_usd": None,
            "usd_coverage_pct": 0.0,
        })
    return out
