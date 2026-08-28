"""Backtesting stateless para V3.

Reconstruye señales desde históricos BVC ya descargados. No usa DB local.
El objetivo es validar thresholds y no optimizar sobre todo el histórico.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from services.scoring_engine_v3 import _hist_metrics


def _n(v: Any) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _close(row: dict) -> float:
    for key in ("PRECIO_CIE", "PRECIO", "PRECIO_APERT"):
        value = _n(row.get(key))
        if value > 0:
            return value
    return 0.0


def _forward_return(hist: list[dict], cutoff_index: int, ruedas: int) -> float | None:
    # históricos newest-first. cutoff_index apunta a la fecha simulada; el
    # futuro está hacia índices menores.
    future_index = cutoff_index - ruedas
    if future_index < 0 or cutoff_index >= len(hist):
        return None
    now = _close(hist[cutoff_index])
    future = _close(hist[future_index])
    if now <= 0 or future <= 0:
        return None
    return round((future / now - 1.0) * 100.0, 3)


def _proxy_score(metrics: dict) -> float:
    """Proxy histórico reproducible para calibrar thresholds V3.

    No pretende reconstruir el score cross-sectional exacto; sirve para medir
    persistencia y forward returns con factores históricos disponibles.
    """
    m20 = _n(metrics.get("momentum_20d_pct"))
    m60 = _n(metrics.get("momentum_60d_pct"))
    freq = _n(metrics.get("trading_frequency_60d_pct"))
    dd = abs(min(0.0, _n(metrics.get("max_drawdown_60d_pct"))))
    concentration = _n(metrics.get("max_day_volume_share_pct"), 100)
    vol = _n(metrics.get("volatility_annualized_pct"))

    mom20 = max(0.0, min(100.0, 50.0 + m20 * 2.0))
    mom60 = max(0.0, min(100.0, 50.0 + m60))
    dd_quality = max(0.0, 100.0 - dd * 3.0)
    conc_quality = max(0.0, 100.0 - max(0.0, concentration - 20.0) * 1.5)
    vol_quality = max(0.0, 100.0 - max(0.0, vol - 40.0) * 0.8)
    return round(mom20 * .25 + mom60 * .20 + freq * .20 + dd_quality * .15 + conc_quality * .10 + vol_quality * .10, 1)


def backtest_symbol(hist: list[dict], score_threshold: float = 70.0, step: int = 5) -> list[dict]:
    rows = [r for r in hist if _close(r) > 0]
    results: list[dict] = []
    # al menos 61 ruedas de pasado y hasta 60 ruedas de futuro.
    for i in range(60, max(60, len(rows) - 1), max(1, step)):
        if i >= len(rows):
            break
        past = rows[i:]
        if len(past) < 61:
            continue
        metrics = _hist_metrics(past)
        score = _proxy_score(metrics)
        rec = {
            "fecha": rows[i].get("FEC"),
            "score_proxy": score,
            "signal": score >= score_threshold,
            "ret_5d": _forward_return(rows, i, 5),
            "ret_20d": _forward_return(rows, i, 20),
            "ret_60d": _forward_return(rows, i, 60),
            "max_drawdown_60d": metrics.get("max_drawdown_60d_pct"),
        }
        results.append(rec)
    return results


def summarize(records: list[dict]) -> dict:
    signals = [r for r in records if r.get("signal")]

    def horizon(key: str) -> dict:
        vals = [_n(r.get(key)) for r in signals if r.get(key) is not None]
        if not vals:
            return {"n": 0, "avg": None, "hit_rate": None}
        return {
            "n": len(vals),
            "avg": round(sum(vals) / len(vals), 2),
            "hit_rate": round(sum(1 for v in vals if v > 0) / len(vals) * 100.0, 1),
        }

    return {
        "observations": len(records),
        "signals": len(signals),
        "ret_5d": horizon("ret_5d"),
        "ret_20d": horizon("ret_20d"),
        "ret_60d": horizon("ret_60d"),
    }


def walk_forward_threshold(records: list[dict], candidates: list[float] | None = None) -> dict:
    """Selecciona threshold en train, valida y reporta test out-of-sample."""
    candidates = candidates or [55, 60, 65, 70, 75, 80]
    ordered = list(records)
    n = len(ordered)
    if n < 30:
        return {"error": "muestra_insuficiente", "n": n}

    a = int(n * .60)
    b = int(n * .80)
    train, valid, test = ordered[:a], ordered[a:b], ordered[b:]

    def score_threshold(sample: list[dict], threshold: float) -> tuple[float, int]:
        chosen = [r for r in sample if _n(r.get("score_proxy")) >= threshold and r.get("ret_20d") is not None]
        if len(chosen) < 3:
            return (-999.0, len(chosen))
        avg = sum(_n(r.get("ret_20d")) for r in chosen) / len(chosen)
        hit = sum(1 for r in chosen if _n(r.get("ret_20d")) > 0) / len(chosen)
        return (avg * .6 + hit * 10.0 * .4, len(chosen))

    ranked = sorted(((score_threshold(train, t)[0], t) for t in candidates), reverse=True)
    best = ranked[0][1]

    def eval_set(sample: list[dict]) -> dict:
        selected = [r for r in sample if _n(r.get("score_proxy")) >= best]
        copy = [dict(r, signal=True) for r in selected]
        return summarize(copy)

    return {
        "selected_threshold": best,
        "train": eval_set(train),
        "validation": eval_set(valid),
        "test": eval_set(test),
        "method": "60/20/20 chronological walk-forward",
    }


def backtest_universe(histories: dict[str, list[dict]], threshold: float = 70.0, step: int = 5) -> dict:
    per_symbol = {}
    all_records = []
    for symbol, hist in histories.items():
        recs = backtest_symbol(hist, threshold, step)
        per_symbol[symbol] = summarize(recs)
        all_records.extend(dict(r, simbolo=symbol) for r in recs)
    return {
        "threshold": threshold,
        "per_symbol": per_symbol,
        "aggregate": summarize(all_records),
        "walk_forward": walk_forward_threshold(all_records),
        "storage": "stateless",
    }
