"""Performance temporal de cartera V5 con flujos externos explícitos.

Usa Modified Dietz entre snapshots para evitar atribuir a rendimiento compras o
ventas realizadas dentro de la ventana. No reconstruye períodos sin snapshots.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Iterable


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


def analyze_snapshot_performance(snapshots: Iterable[dict], transactions: Iterable[dict], *, as_of: date | None = None) -> dict:
    snaps = _normalize_snapshots(snapshots)
    if len(snaps) < 2:
        return {"available": False, "reason": "historia_snapshot_insuficiente", "windows": {}}
    terminal = snaps[-1]
    today = as_of or terminal["_date"]
    txs: list[tuple[date, float]] = []
    for tx in transactions or []:
        d = _date(tx.get("fecha"))
        flow = _tx_flow_bs(tx)
        if d and abs(flow) > 1e-12:
            txs.append((d, flow))

    windows = {}
    for name in ("1M", "3M", "6M", "YTD", "1Y"):
        target = _window_start(today, name)
        start_snap = _asof_snapshot(snaps, target)
        if not start_snap or start_snap["_date"] >= terminal["_date"]:
            windows[name] = {"available": False, "reason": "sin_historia_suficiente"}
            continue
        flows = [(d, f) for d, f in txs if start_snap["_date"] < d <= terminal["_date"]]
        ret = modified_dietz_return(
            start_snap["_value"], terminal["_value"], start_snap["_date"], terminal["_date"], flows,
        )
        windows[name] = {
            "available": ret is not None,
            "return_bs_pct": round(ret, 2) if ret is not None else None,
            "start_date": start_snap["_date"].isoformat(),
            "end_date": terminal["_date"].isoformat(),
            "flows_count": len(flows),
            "method": "modified_dietz",
        }

    usd_values = [s.get("total_market_usd") for s in snaps if _f(s.get("total_market_usd")) > 0]
    return {
        "available": True,
        "snapshot_count": len(snaps),
        "from": snaps[0]["_date"].isoformat(),
        "to": terminal["_date"].isoformat(),
        "windows": windows,
        "max_drawdown_bs_pct": max_drawdown([s["_value"] for s in snaps]),
        "max_drawdown_usd_observed_pct": max_drawdown(usd_values),
        "note": "Drawdown sobre valor observado puede reflejar flujos; retorno de ventanas corrige flujos con Modified Dietz.",
    }
