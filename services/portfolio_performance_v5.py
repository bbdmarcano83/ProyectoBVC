"""Performance temporal de cartera V5 con flujos externos explícitos.

Usa Modified Dietz entre snapshots para evitar atribuir a rendimiento compras o
ventas realizadas dentro de la ventana. Para comparar contra IBC crea un
benchmark sintético que recibe los mismos flujos en las mismas fechas.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Iterable

from services.portfolio_benchmark_v5 import normalize_ibc_points, ibc_asof


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
    try:
        return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _tx_flow_bs(tx: dict) -> float:
    kind = str(tx.get("tipo") or "").lower()
    neto = _f(tx.get("neto"))
    if neto <= 0:
        qty = _f(tx.get("cantidad")); price = _f(tx.get("precio")); fee = _f(tx.get("fee_total"))
        gross = qty * price
        neto = gross + fee if kind == "compra" else max(0.0, gross - fee)
    if kind == "compra":
        return neto
    if kind == "venta":
        return -neto
    return 0.0


def _normalize_snapshots(rows: Iterable[dict]) -> list[dict]:
    out = []
    for raw in rows or []:
        d = _date(raw.get("as_of"))
        value = _f(raw.get("total_market_bs"))
        if d and value >= 0:
            item = dict(raw); item["_date"] = d; item["_value"] = value
            out.append(item)
    out.sort(key=lambda x: x["_date"])
    return out


def modified_dietz_return(start_value: float, end_value: float, start: date, end: date, flows: list[tuple[date, float]]) -> float | None:
    """Retorno % Modified Dietz para un intervalo con flujos fechados."""
    start_value = _f(start_value); end_value = _f(end_value)
    days = (end - start).days
    if start_value <= 0 or days <= 0:
        return None
    total_flow = 0.0
    weighted_flow = 0.0
    for d, flow in flows:
        if d <= start or d > end:
            continue
        f = _f(flow)
        weight = max(0.0, min(1.0, (end - d).days / days))
        total_flow += f
        weighted_flow += weight * f
    denominator = start_value + weighted_flow
    if abs(denominator) < 1e-12:
        return None
    return (end_value - start_value - total_flow) / denominator * 100.0


def _window_start(today: date, name: str) -> date:
    if name == "1M": return today - timedelta(days=31)
    if name == "3M": return today - timedelta(days=92)
    if name == "6M": return today - timedelta(days=183)
    if name == "1Y": return today - timedelta(days=366)
    if name == "YTD": return date(today.year, 1, 1)
    return today


def _asof_snapshot(snaps: list[dict], target: date) -> dict | None:
    best = None
    for s in snaps:
        if s["_date"] > target:
            break
        best = s
    if best is not None:
        return best
    return snaps[0] if snaps else None


def max_drawdown(values: Iterable[float]) -> float | None:
    peak = None
    worst = 0.0
    count = 0
    for raw in values or []:
        v = _f(raw)
        if v <= 0:
            continue
        count += 1
        peak = v if peak is None else max(peak, v)
        dd = (v / peak - 1.0) * 100.0
        worst = min(worst, dd)
    return round(worst, 2) if count >= 2 else None


def _normalize_transactions(transactions: Iterable[dict]) -> list[dict]:
    out = []
    for tx in transactions or []:
        d = _date(tx.get("fecha"))
        flow = _tx_flow_bs(tx)
        if not d or abs(flow) <= 1e-12:
            continue
        item = dict(tx)
        item["_date"] = d
        item["_flow_bs"] = flow
        fx = _f(tx.get("tasa_bcv"))
        item["_fx"] = fx if fx > 0 else None
        out.append(item)
    return out


def _synthetic_ibc_terminal_bs(start_value: float, start: date, end: date, flows: list[dict], ibc: list[tuple[date, float]]) -> float | None:
    start_level = ibc_asof(ibc, start)
    end_level = ibc_asof(ibc, end)
    if not start_level or not end_level or start_value <= 0:
        return None
    units = start_value / start_level
    for tx in flows:
        d = tx["_date"]
        if d <= start or d > end:
            continue
        level = ibc_asof(ibc, d)
        if not level or level <= 0:
            return None
        units += tx["_flow_bs"] / level
    if units < -1e-9:
        return None
    return max(0.0, units) * end_level


def analyze_snapshot_performance(
    snapshots: Iterable[dict],
    transactions: Iterable[dict],
    *,
    ibc_points: Iterable[dict] | None = None,
    as_of: date | None = None,
) -> dict:
    snaps = _normalize_snapshots(snapshots)
    if len(snaps) < 2:
        return {"available": False, "reason": "historia_snapshot_insuficiente", "windows": {}}
    terminal = snaps[-1]
    today = as_of or terminal["_date"]
    txs = _normalize_transactions(transactions)
    ibc = normalize_ibc_points(ibc_points or [])

    windows = {}
    for name in ("1M", "3M", "6M", "YTD", "1Y"):
        target = _window_start(today, name)
        start_snap = _asof_snapshot(snaps, target)
        if not start_snap or start_snap["_date"] >= terminal["_date"]:
            windows[name] = {"available": False, "reason": "sin_historia_suficiente"}
            continue

        start_day = start_snap["_date"]
        end_day = terminal["_date"]
        window_txs = [tx for tx in txs if start_day < tx["_date"] <= end_day]
        flows_bs = [(tx["_date"], tx["_flow_bs"]) for tx in window_txs]
        portfolio_ret = modified_dietz_return(start_snap["_value"], terminal["_value"], start_day, end_day, flows_bs)
        row = {
            "available": portfolio_ret is not None,
            "return_bs_pct": round(portfolio_ret, 2) if portfolio_ret is not None else None,
            "start_date": start_day.isoformat(),
            "end_date": end_day.isoformat(),
            "flows_count": len(window_txs),
            "method": "modified_dietz",
        }

        if ibc and portfolio_ret is not None:
            ibc_terminal = _synthetic_ibc_terminal_bs(start_snap["_value"], start_day, end_day, window_txs, ibc)
            ibc_ret = modified_dietz_return(start_snap["_value"], ibc_terminal, start_day, end_day, flows_bs) if ibc_terminal is not None else None
            row["ibc_return_bs_pct"] = round(ibc_ret, 2) if ibc_ret is not None else None
            row["alpha_bs_pp"] = round(portfolio_ret - ibc_ret, 2) if ibc_ret is not None else None
            row["beats_ibc_bs"] = portfolio_ret > ibc_ret if ibc_ret is not None else None
        else:
            row.update({"ibc_return_bs_pct": None, "alpha_bs_pp": None, "beats_ibc_bs": None})

        # USD sólo si snapshots inicial/final y todos los flujos tienen FX histórico.
        start_usd = _f(start_snap.get("total_market_usd"))
        end_usd = _f(terminal.get("total_market_usd"))
        end_fx = _f(terminal.get("fx_bcv"))
        all_flow_fx = all(tx.get("_fx") and tx["_fx"] > 0 for tx in window_txs)
        if start_usd > 0 and end_usd > 0 and all_flow_fx:
            flows_usd = [(tx["_date"], tx["_flow_bs"] / tx["_fx"]) for tx in window_txs]
            portfolio_usd = modified_dietz_return(start_usd, end_usd, start_day, end_day, flows_usd)
            row["return_usd_pct"] = round(portfolio_usd, 2) if portfolio_usd is not None else None
            if ibc and end_fx > 0:
                ibc_terminal_bs = _synthetic_ibc_terminal_bs(start_snap["_value"], start_day, end_day, window_txs, ibc)
                ibc_terminal_usd = ibc_terminal_bs / end_fx if ibc_terminal_bs is not None else None
                ibc_usd = modified_dietz_return(start_usd, ibc_terminal_usd, start_day, end_day, flows_usd) if ibc_terminal_usd is not None else None
                row["ibc_return_usd_pct"] = round(ibc_usd, 2) if ibc_usd is not None else None
                row["alpha_usd_pp"] = round(portfolio_usd - ibc_usd, 2) if portfolio_usd is not None and ibc_usd is not None else None
                row["beats_ibc_usd"] = portfolio_usd > ibc_usd if portfolio_usd is not None and ibc_usd is not None else None
            else:
                row.update({"ibc_return_usd_pct": None, "alpha_usd_pp": None, "beats_ibc_usd": None})
        else:
            row.update({
                "return_usd_pct": None,
                "ibc_return_usd_pct": None,
                "alpha_usd_pp": None,
                "beats_ibc_usd": None,
            })
        windows[name] = row

    usd_values = [s.get("total_market_usd") for s in snaps if _f(s.get("total_market_usd")) > 0]
    ibc_levels = [ibc_asof(ibc, s["_date"]) for s in snaps] if ibc else []
    return {
        "available": True,
        "snapshot_count": len(snaps),
        "from": snaps[0]["_date"].isoformat(),
        "to": terminal["_date"].isoformat(),
        "windows": windows,
        "max_drawdown_bs_pct": max_drawdown([s["_value"] for s in snaps]),
        "max_drawdown_usd_observed_pct": max_drawdown(usd_values),
        "ibc_max_drawdown_pct": max_drawdown([v for v in ibc_levels if v is not None]),
        "note": "Ventanas corrigen flujos con Modified Dietz; benchmark IBC recibe los mismos flujos y fechas. Drawdown de cartera sobre valor observado puede reflejar flujos.",
    }
