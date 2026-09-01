"""Backfill auditable y persistente del IBC V5.

Cada punto conserva su URL de origen y pasa por ``persist_ibc_points``. La
política de persistencia impide degradar un dato BVC oficial con una fuente de
menor prioridad. Este módulo no ofrece dry-run: si se ejecuta, persiste.
"""
from __future__ import annotations

import re
from datetime import date
from html import unescape

import httpx

from database import DB_PERSISTENCE_MODE
from services.ibc_store_v5 import persist_ibc_points

DATOSMACRO_BASE = "https://datosmacro.expansion.com/bolsa/venezuela"
_TEXT_ROW_RE = re.compile(
    r"(?P<day>\d{2}/\d{2}/\d{4})\s+(?P<level>\d{1,3}(?:\.\d{3})*(?:,\d+)?|\d+(?:,\d+)?)"
)
_TAG_RE = re.compile(r"<[^>]+>")


def _require_external_db() -> None:
    if DB_PERSISTENCE_MODE != "external":
        raise RuntimeError("external_database_required_for_persistent_backfill")


def month_url(year: int, month: int) -> str:
    if year < 2000 or not 1 <= month <= 12:
        raise ValueError("invalid_year_month")
    return f"{DATOSMACRO_BASE}?dr={year:04d}-{month:02d}"


def _level(raw: str) -> float | None:
    try:
        return float(raw.replace(".", "").replace(",", "."))
    except (TypeError, ValueError):
        return None


def parse_datosmacro_history(html: str, *, source_url: str) -> list[dict]:
    """Extrae filas fecha/nivel sin confiar en scripts/gráficos embebidos."""
    if "datosmacro.expansion.com" not in str(source_url).lower():
        return []
    raw = unescape(str(html or ""))
    text = " ".join(_TAG_RE.sub(" ", raw).split())
    by_date: dict[str, dict] = {}
    for match in _TEXT_ROW_RE.finditer(text):
        day_raw = match.group("day")
        value = _level(match.group("level"))
        if value is None or value <= 0:
            continue
        dd, mm, yyyy = map(int, day_raw.split("/"))
        try:
            iso = date(yyyy, mm, dd).isoformat()
        except ValueError:
            continue
        by_date.setdefault(iso, {"date": iso, "close": value, "source_url": source_url})
    return [by_date[k] for k in sorted(by_date)]


def fetch_month(year: int, month: int, *, timeout: float = 20.0) -> tuple[list[dict], dict]:
    url = month_url(year, month)
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            response = client.get(url, headers={"User-Agent": "CaracasBull-V5/1.0"})
            response.raise_for_status()
    except Exception as exc:
        return [], {"ok": False, "url": url, "error": type(exc).__name__}
    points = parse_datosmacro_history(response.text, source_url=url)
    return points, {"ok": bool(points), "url": url, "points": len(points)}


def backfill_range(start_year: int, start_month: int, end_year: int, end_month: int) -> dict:
    """Descarga y persiste el rango solicitado en una DB externa."""
    _require_external_db()
    start = date(start_year, start_month, 1)
    end = date(end_year, end_month, 1)
    if start > end:
        raise ValueError("start_after_end")

    months = []
    y, m = start.year, start.month
    all_points: list[dict] = []
    while (y, m) <= (end.year, end.month):
        points, meta = fetch_month(y, m)
        months.append(meta)
        all_points.extend(points)
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1

    by_date = {p["date"]: p for p in all_points}
    ordered = [by_date[k] for k in sorted(by_date)]
    state = persist_ibc_points(ordered) if ordered else {"inserted": 0, "updated": 0, "rejected": 0, "unchanged": 0}
    return {
        "ok": bool(ordered),
        "from": start.isoformat(),
        "to": end.isoformat(),
        "months": months,
        "points": len(ordered),
        "persisted": state,
        "database_mode": DB_PERSISTENCE_MODE,
    }
