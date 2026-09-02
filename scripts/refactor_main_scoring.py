"""Deterministically replace legacy scoring section with direct registration."""
from __future__ import annotations

from pathlib import Path

PATH = Path("main.py")
IMPORT_ANCHOR = "from app.routers.alerts import register_alert_routes\n"
NEW_IMPORT = "from app.routers.scoring import register_scoring_routes\n"
START_MARKER = "# ── Scoring (Rotación Sectorial) ──────────────────────────────────────────────\n"
END_MARKER = "# ── Alertas de cierre Telegram ────────────────────────────────────────────────\n"
REPLACEMENT = '''# ── Scoring (Rotación Sectorial) ──────────────────────────────────────────────
register_scoring_routes(app)


'''


def main() -> int:
    text = PATH.read_text(encoding="utf-8")
    if NEW_IMPORT in text and REPLACEMENT in text:
        print("scoring extraction already applied")
        return 0
    if IMPORT_ANCHOR not in text:
        raise SystemExit("refactor aborted: alerts import anchor missing")
    start = text.find(START_MARKER)
    end = text.find(END_MARKER)
    if start < 0 or end < 0 or end <= start:
        raise SystemExit("refactor aborted: Scoring/Alertas markers not found")
    segment = text[start:end]
    required = (
        'from services.scoring import calcular_scoring_completo',
        '@app.get("/scoring", response_class=HTMLResponse)',
        'async def ver_scoring(',
        '@app.get("/api/scoring", response_class=JSONResponse)',
        'async def api_scoring(',
    )
    missing = [item for item in required if item not in segment]
    if missing:
        raise SystemExit(f"refactor aborted: expected scoring fragments missing: {missing}")
    old_segment = segment
    text = text.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + NEW_IMPORT, 1)
    text = text.replace(old_segment, REPLACEMENT, 1)
    PATH.write_text(text, encoding="utf-8")
    print("scoring route extraction applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
