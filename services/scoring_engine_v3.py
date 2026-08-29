"""Scoring Engine V3 completo y stateless.

No depende de persistencia local. Calcula V2 como baseline compatible y en la
misma corrida reconstruye métricas V3 desde los históricos BVC disponibles.
"""
from __future__ import annotations

import asyncio
import math
import statistics
from dataclasses import dataclass
from typing import Any

from services.bvc import obtener_historico, _to_float
from services.scoring_v2 import calcular_scoring_completo as calcular_scoring_v2


@dataclass(frozen=True)
class Policy:
    confidence_min: float = 70.0
    strength_min: float = 70.0
    opportunity_confirmed_min: float = 70.0
    controlled_drop_low: float = -20.0
    controlled_drop_high: float = -8.0
    risk_max_confirmed: float = 60.0


POLICY = Policy()
_LAST_SCORING_MAP: dict[str, dict] = {}
_LAST_MARKET: dict = {}


def _n(v: Any, default: float = 0.0) -> float:
    try:
        return float(v if v is not None else default)
    except (TypeError, ValueError):
        return default


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return round(max(lo, min(hi, v)), 1)


def _close(row: dict) -> float:
    return _to_float(row.get("PRECIO_CIE") or row.get("PRECIO") or row.get("PRECIO_APERT") or 0)


def _pct(a: float, b: float) -> float | None:
    if a <= 0 or b <= 0:
        return None
    return (a / b - 1.0) * 100.0


def _returns(closes: list[float]) -> list[float]:
    out: list[float] = []
    for i in range(len(closes) - 1):
        r = _pct(closes[i], closes[i + 1])
        if r is not None:
            out.append(r)
    return out


def _ret_window(closes: list[float], ruedas: int) -> float | None:
    if len(closes) <= ruedas:
        return None
    return _pct(closes[0], closes[ruedas])


def _max_drawdown(closes: list[float]) -> float:
    if len(closes) < 2:
        return 0.0
    chronological = list(reversed([c for c in closes if c > 0]))
    peak = chronological[0]
    worst = 0.0
    for price in chronological:
        peak = max(peak, price)
        dd = (price / peak - 1.0) * 100.0 if peak > 0 else 0.0
        worst = min(worst, dd)
    return round(worst, 2)


def _hist_metrics(hist: list[dict]) -> dict:
    rows = [r for r in hist if _close(r) > 0][:120]
    closes = [_close(r) for r in rows]
    daily = _returns(closes[:61])
    downs = [r for r in daily if r < 0]

    vol = statistics.pstdev(daily) * math.sqrt(252) if len(daily) >= 5 else 0.0
    downside = statistics.pstdev(downs) * math.sqrt(252) if len(downs) >= 3 else 0.0

    ops = [_n(r.get("TOT_OP_NEGOC")) for r in rows[:60]]
    amounts = [_n(r.get("TOT_MONTO_NEGOC")) for r in rows[:60]]
    trading_freq = (sum(1 for x in ops if x > 0) / len(ops) * 100.0) if ops else 0.0
    total_amt = sum(max(0.0, x) for x in amounts)
    max_day_share = (max(amounts, default=0.0) / total_amt * 100.0) if total_amt > 0 else 100.0
    top3_share = (sum(sorted(amounts, reverse=True)[:3]) / total_amt * 100.0) if total_amt > 0 else 100.0

    ret5 = _ret_window(closes, 5)
    ret20 = _ret_window(closes, 20)
    ret60 = _ret_window(closes, 60)
    accel = None
    if ret5 is not None and ret20 is not None:
        accel = ret5 - ret20 / 4.0

    # Confirmación precio/actividad: compara actividad reciente vs anterior.
    recent_amt = statistics.median(amounts[:5]) if amounts[:5] else 0.0
    prev_amt = statistics.median(amounts[5:20]) if len(amounts) >= 6 else 0.0
    volume_expansion = ((recent_amt / prev_amt) - 1.0) * 100.0 if prev_amt > 0 else 0.0
    price_volume_confirmation = 0.0
    if ret5 is not None:
        if ret5 > 0 and volume_expansion > 0:
            price_volume_confirmation = 100.0
        elif ret5 < 0 and volume_expansion > 0:
            price_volume_confirmation = 20.0
        elif ret5 > 0:
            price_volume_confirmation = 60.0
        else:
            price_volume_confirmation = 40.0

    return {
        "momentum_5d_pct": round(ret5, 2) if ret5 is not None else None,
        "momentum_20d_pct": round(ret20, 2) if ret20 is not None else None,
        "momentum_60d_pct": round(ret60, 2) if ret60 is not None else None,
        "momentum_accel": round(accel, 2) if accel is not None else None,
        "volatility_annualized_pct": round(vol, 2),
        "downside_volatility_pct": round(downside, 2),
        "max_drawdown_60d_pct": _max_drawdown(closes[:61]),
        "trading_frequency_60d_pct": round(trading_freq, 1),
        "max_day_volume_share_pct": round(max_day_share, 1),
        "top3_volume_share_pct": round(top3_share, 1),
        "volume_expansion_5v15_pct": round(volume_expansion, 1),
        "price_volume_confirmation": round(price_volume_confirmation, 1),
        "history_rows": len(rows),
    }


def _percentiles(rows: list[dict], key: str) -> dict[str, float]:
    pairs = [(str(r.get("simbolo", "")), _n(r.get(key))) for r in rows if r.get("simbolo") and r.get(key) is not None]
    vals = sorted(v for _, v in pairs)
    if not vals:
        return {}
    if len(vals) == 1:
        return {pairs[0][0]: 100.0}
    out = {}
    for sym, v in pairs:
        below = sum(1 for x in vals if x < v)
        equal = sum(1 for x in vals if x == v)
        rank = below + (equal - 1) / 2.0
        out[sym] = round(rank / (len(vals) - 1) * 100.0, 1)
    return out


def _quality(row: dict) -> tuple[float, list[str]]:
    flags: list[str] = []
    h = row.get("history_v3", {})
    hist = int(_n(h.get("history_rows")))
    freq = _n(h.get("trading_frequency_60d_pct"))
    concentration = _n(h.get("max_day_volume_share_pct"), 100)
    spread = _n(row.get("din_spread_pct"))
    liq = _n(row.get("liq_vol"))

    if _n(row.get("precio")) <= 0:
        flags.append("sin_precio")
    if hist < 20:
        flags.append("historial_corto")
    if freq < 30:
        flags.append("baja_frecuencia")
    if concentration > 55:
        flags.append("volumen_concentrado")
    if spread > 12:
        flags.append("spread_extremo")
    if liq <= 0:
        flags.append("sin_liquidez")
    if row.get("din_label") in {"CONGELADO", "MUERTO"}:
        flags.append("no_operable")

    history_score = min(100.0, hist / 60.0 * 100.0)
    freq_score = min(100.0, freq)
    concentration_score = max(0.0, 100.0 - max(0.0, concentration - 20.0) * 1.5)
    spread_score = max(0.0, 100.0 - spread * 5.0)
    liq_score = min(100.0, _n(row.get("liq_score")) / 25.0 * 100.0)
    score = history_score * .25 + freq_score * .25 + concentration_score * .20 + spread_score * .15 + liq_score * .15
    if "no_operable" in flags or "sin_precio" in flags:
        score = min(score, 20.0)
    return _clamp(score), flags


def _risk(row: dict, liq_pct: float) -> float:
    h = row.get("history_v3", {})
    dd = abs(min(0.0, _n(h.get("max_drawdown_60d_pct"))))
    vol = _n(h.get("volatility_annualized_pct"))
    dvol = _n(h.get("downside_volatility_pct"))
    spread = _n(row.get("din_spread_pct"))
    concentration = _n(h.get("max_day_volume_share_pct"), 100)
    risk = (
        min(100.0, dd / 35.0 * 100.0) * .25
        + min(100.0, vol / 120.0 * 100.0) * .15
        + min(100.0, dvol / 90.0 * 100.0) * .15
        + min(100.0, spread / 15.0 * 100.0) * .15
        + max(0.0, 100.0 - liq_pct) * .15
        + min(100.0, concentration) * .15
    )
    if row.get("din_label") in {"CONGELADO", "MUERTO"}:
        risk = max(risk, 92.0)
    if row.get("tend_trend") == "crash":
        risk = max(risk, 88.0)
    return _clamp(risk)


def _strength(row: dict, ret_pct: float, liq_pct: float, mom20_pct: float, mom60_pct: float) -> float:
    h = row.get("history_v3", {})
    pv = _n(h.get("price_volume_confirmation"))
    trend = min(100.0, _n(row.get("tend_score")) / 15.0 * 100.0)
    return _clamp(ret_pct * .25 + liq_pct * .20 + mom20_pct * .20 + mom60_pct * .15 + pv * .10 + trend * .10)


def _opportunity(row: dict, strength: float, confidence: float, risk: float) -> float:
    drop = _n(row.get("caida_pct"))
    h = row.get("history_v3", {})
    accel = _n(h.get("momentum_accel"))
    if POLICY.controlled_drop_low <= drop <= POLICY.controlled_drop_high:
        pullback = 100.0
    elif -25 <= drop < POLICY.controlled_drop_low:
        pullback = 45.0
    elif POLICY.controlled_drop_high < drop <= -3:
        pullback = 65.0
    elif drop < -25:
        pullback = 15.0
    else:
        pullback = 35.0
    accel_score = _clamp(50.0 + accel * 3.0)
    return _clamp(strength * .30 + confidence * .20 + pullback * .25 + (100.0 - risk) * .15 + accel_score * .10)


def _market_regime(rows: list[dict]) -> dict:
    if not rows:
        return {"regime": "SIN DATOS", "breadth_score": 0.0}
    n = len(rows)
    high = sum(1 for r in rows if _n(r.get("strength_score_v3")) >= 70) / n * 100
    up = sum(1 for r in rows if (_n(r.get("history_v3", {}).get("momentum_20d_pct")) > 0)) / n * 100
    liquid = sum(1 for r in rows if _n(r.get("confidence_score_v3")) >= 60) / n * 100
    frozen = sum(1 for r in rows if r.get("din_label") in {"CONGELADO", "MUERTO"}) / n * 100
    breadth = _clamp(high * .35 + up * .35 + liquid * .30 - frozen * .25)
    if breadth >= 70:
        regime = "RISK-ON"
    elif breadth >= 50:
        regime = "NEUTRAL"
    elif breadth >= 30:
        regime = "DEFENSIVO"
    else:
        regime = "ESTRES"
    return {
        "regime": regime,
        "breadth_score": breadth,
        "pct_strength_ge_70": round(high, 1),
        "pct_momentum20_positive": round(up, 1),
        "pct_confidence_ge_60": round(liquid, 1),
        "pct_frozen": round(frozen, 1),
    }


def _final_score(row: dict, regime: str) -> float:
    strength = _n(row.get("strength_score_v3"))
    opp = _n(row.get("opportunity_score_v3"))
    conf = _n(row.get("confidence_score_v3"))
    inv_risk = 100.0 - _n(row.get("risk_score_v3"))
    if regime == "RISK-ON":
        return _clamp(strength * .45 + opp * .25 + conf * .15 + inv_risk * .15)
    if regime == "ESTRES":
        return _clamp(strength * .25 + opp * .15 + conf * .30 + inv_risk * .30)
    if regime == "DEFENSIVO":
        return _clamp(strength * .30 + opp * .20 + conf * .25 + inv_risk * .25)
    return _clamp(strength * .35 + opp * .25 + conf * .20 + inv_risk * .20)


def _signal(row: dict) -> str:
    drop = _n(row.get("caida_pct"))
    controlled = POLICY.controlled_drop_low <= drop <= POLICY.controlled_drop_high
    if (
        _n(row.get("opportunity_score_v3")) >= POLICY.opportunity_confirmed_min
        and _n(row.get("confidence_score_v3")) >= POLICY.confidence_min
        and _n(row.get("strength_score_v3")) >= POLICY.strength_min
        and _n(row.get("risk_score_v3")) < POLICY.risk_max_confirmed
        and controlled
        and row.get("data_quality_ok_v3")
        and row.get("tend_trend") != "crash"
    ):
        return "OPORTUNIDAD CONFIRMADA"
    if _n(row.get("opportunity_score_v3")) >= 60 and _n(row.get("confidence_score_v3")) >= 55:
        return "PREPARAR COMPRA"
    return "OBSERVAR"


def _explain(row: dict) -> list[str]:
    h = row.get("history_v3", {})
    reasons: list[str] = []
    if _n(row.get("return_percentile_v3")) >= 80:
        reasons.append("+ top 20% en retorno relativo")
    if _n(row.get("liquidity_percentile_v3")) >= 80:
        reasons.append("+ top 20% en liquidez")
    if _n(h.get("trading_frequency_60d_pct")) >= 70:
        reasons.append("+ alta frecuencia de negociación")
    if _n(h.get("momentum_60d_pct")) > 0:
        reasons.append("+ momentum 60d positivo")
    if _n(h.get("price_volume_confirmation")) >= 80:
        reasons.append("+ precio confirmado por actividad")
    if _n(row.get("risk_score_v3")) >= 70:
        reasons.append("- riesgo elevado")
    if _n(h.get("max_day_volume_share_pct")) > 55:
        reasons.append("- volumen concentrado en pocas ruedas")
    if _n(row.get("din_spread_pct")) > 8:
        reasons.append("- spread elevado")
    return reasons[:6]


async def calcular_scoring_completo(devaluacion_pct: float | None = None) -> tuple[list[dict], float, dict]:
    legacy, deval, meta = await calcular_scoring_v2(devaluacion_pct)
    if not legacy:
        return legacy, deval, {**(meta or {}), "engine_version": "v3"}

    async def fetch(sym: str):
        try:
            return await obtener_historico(sym)
        except Exception:
            return []

    histories = await asyncio.gather(*[fetch(str(r.get("simbolo", ""))) for r in legacy])
    rows: list[dict] = []
    for base, hist in zip(legacy, histories):
        r = dict(base)
        r["legacy_score_v2"] = _n(base.get("total"))
        r["history_v3"] = _hist_metrics(hist)
        rows.append(r)

    ret_pct = _percentiles(rows, "rend_pct")
    liq_pct = _percentiles(rows, "liq_vol")
    # Percentiles históricos multi-horizonte
    for r in rows:
        sym = str(r.get("simbolo", ""))
        r["return_percentile_v3"] = ret_pct.get(sym, 0.0)
        r["liquidity_percentile_v3"] = liq_pct.get(sym, 0.0)
        r["momentum20_raw_v3"] = r["history_v3"].get("momentum_20d_pct")
        r["momentum60_raw_v3"] = r["history_v3"].get("momentum_60d_pct")

    mom20_pct = _percentiles(rows, "momentum20_raw_v3")
    mom60_pct = _percentiles(rows, "momentum60_raw_v3")

    for r in rows:
        sym = str(r.get("simbolo", ""))
        confidence, flags = _quality(r)
        risk = _risk(r, liq_pct.get(sym, 0.0))
        strength = _strength(r, ret_pct.get(sym, 0.0), liq_pct.get(sym, 0.0), mom20_pct.get(sym, 0.0), mom60_pct.get(sym, 0.0))
        opportunity = _opportunity(r, strength, confidence, risk)
        r.update({
            "confidence_score_v3": confidence,
            "strength_score_v3": strength,
            "opportunity_score_v3": opportunity,
            "risk_score_v3": risk,
            "quality_flags_v3": flags,
            "data_quality_ok_v3": len(flags) == 0,
            "momentum20_percentile_v3": mom20_pct.get(sym, 0.0),
            "momentum60_percentile_v3": mom60_pct.get(sym, 0.0),
        })

    market = _market_regime(rows)
    for r in rows:
        r["market_regime_v3"] = market["regime"]
        r["score_v3"] = _final_score(r, market["regime"])
        r["signal_stage_v3"] = _signal(r)
        r["señal_compra_v3"] = r["signal_stage_v3"] == "OPORTUNIDAD CONFIRMADA"
        r["explain_v3"] = _explain(r)
        # Campos legacy visibles se conservan; total pasa a V3 sólo porque este
        # módulo se usa cuando el motor V3 está activado explícitamente.
        r["total"] = r["score_v3"]

    rows.sort(key=lambda x: _n(x.get("score_v3")), reverse=True)
    global _LAST_SCORING_MAP, _LAST_MARKET
    _LAST_SCORING_MAP = {str(r.get("simbolo")): dict(r) for r in rows}
    _LAST_MARKET = dict(market)

    metadata = dict(meta or {})
    metadata.update({
        "engine_version": "v3-stateless-full",
        "market": market,
        "confirmed_opportunities": sum(1 for r in rows if r.get("señal_compra_v3")),
        "data_quality_issues": sum(1 for r in rows if not r.get("data_quality_ok_v3")),
        "storage": "stateless",
    })
    return rows, deval, metadata


def get_last_scoring_map() -> dict[str, dict]:
    return {k: dict(v) for k, v in _LAST_SCORING_MAP.items()}


def get_last_market_snapshot() -> dict:
    return dict(_LAST_MARKET)
