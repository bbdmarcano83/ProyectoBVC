"""Post-proceso V3: sectores, eventos y compatibilidad con UI legacy."""
from __future__ import annotations

import json
import os
from collections import defaultdict
from typing import Any


def _n(v: Any) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _events_from_env() -> dict[str, list[dict]]:
    raw = os.environ.get("CORPORATE_EVENTS_JSON", "").strip()
    if not raw:
        return {}
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _legacy_action_from_v3(score: float) -> dict:
    if score >= 75:
        return {"label": "Score alto", "color": "#0F6E56", "bg": "rgba(27,175,122,0.12)"}
    if score >= 50:
        return {"label": "Score medio", "color": "#185FA5", "bg": "rgba(42,120,214,0.12)"}
    if score >= 30:
        return {"label": "Score bajo", "color": "#854F0B", "bg": "rgba(237,161,0,0.12)"}
    return {"label": "Score mínimo", "color": "#d03b3b", "bg": "rgba(208,59,59,0.12)"}


def apply_sector_and_events(rows: list[dict], metadata: dict | None = None) -> tuple[list[dict], dict]:
    groups: dict[str, list[float]] = defaultdict(list)
    for r in rows:
        sector = str(r.get("sector") or "SIN SECTOR")
        groups[sector].append(_n(r.get("score_v3", r.get("total"))))

    sector_scores = {s: round(sum(v) / len(v), 1) for s, v in groups.items() if v}
    ordered = sorted(sector_scores.items(), key=lambda x: x[1], reverse=True)
    sector_rank = {sector: i + 1 for i, (sector, _) in enumerate(ordered)}
    events = _events_from_env()

    out = []
    event_blocks = 0
    for base in rows:
        r = dict(base)
        sym = str(r.get("simbolo", ""))
        sector = str(r.get("sector") or "SIN SECTOR")
        r["sector_score_v3"] = sector_scores.get(sector, 0.0)
        r["sector_rank_v3"] = sector_rank.get(sector)
        ev = events.get(sym, [])
        if isinstance(ev, dict):
            ev = [ev]
        r["corporate_events_v3"] = ev if isinstance(ev, list) else []
        blocking = any(bool(e.get("blocking", False)) for e in r["corporate_events_v3"] if isinstance(e, dict))
        if blocking:
            event_blocks += 1
            r["signal_stage_v3"] = "OBSERVAR"
            r["señal_compra_v3"] = False
            r.setdefault("quality_flags_v3", []).append("evento_corporativo")

        # main.py y templates existentes todavía leen estos campos V2.
        r["legacy_señal_compra_v2"] = bool(r.get("señal_compra", False))
        r["legacy_accion_label_v2"] = r.get("accion_label")
        r["señal_compra"] = bool(r.get("señal_compra_v3", False))
        action = _legacy_action_from_v3(_n(r.get("score_v3", r.get("total"))))
        r["accion_label"] = action["label"]
        r["accion_color"] = action["color"]
        r["accion_bg"] = action["bg"]
        out.append(r)

    meta = dict(metadata or {})
    meta["sector_scores_v3"] = sector_scores
    meta["sector_ranking_v3"] = [s for s, _ in ordered]
    meta["corporate_event_blocks_v3"] = event_blocks
    meta["legacy_ui_contract_synced"] = True
    return out, meta
