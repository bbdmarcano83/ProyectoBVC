"""Post-proceso V3: fuerza sectorial y eventos corporativos stateless."""
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
        out.append(r)

    meta = dict(metadata or {})
    meta["sector_scores_v3"] = sector_scores
    meta["sector_ranking_v3"] = [s for s, _ in ordered]
    meta["corporate_event_blocks_v3"] = event_blocks
    return out, meta
