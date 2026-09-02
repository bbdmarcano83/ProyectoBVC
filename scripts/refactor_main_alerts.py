"""Deterministically replace legacy alert-dispatch section with direct registration."""
from __future__ import annotations

from pathlib import Path

PATH = Path("main.py")
IMPORT_ANCHOR = "from app.routers.bitacora import register_bitacora_routes\n"
NEW_IMPORT = "from app.routers.alerts import register_alert_routes\n"
START_MARKER = "# ── Alertas de cierre Telegram ────────────────────────────────────────────────\n"
END_MARKER = "# ── Bitácora ──────────────────────────────────────────────────────────────────\n"
REPLACEMENT = '''# ── Alertas de cierre Telegram ────────────────────────────────────────────────
register_alert_routes(app)


'''


def main() -> int:
    text = PATH.read_text(encoding="utf-8")
    if NEW_IMPORT in text and REPLACEMENT in text:
        print("alerts extraction already applied")
        return 0
    if IMPORT_ANCHOR not in text:
        raise SystemExit("refactor aborted: bitacora import anchor missing")
    start = text.find(START_MARKER)
    end = text.find(END_MARKER)
    if start < 0 or end < 0 or end <= start:
        raise SystemExit("refactor aborted: Alertas/Bitácora markers not found")
    segment = text[start:end]
    required = (
        '@app.get("/api/alertas-cierre", response_class=JSONResponse)',
        'async def disparar_alertas_cierre(',
        'enviar_alertas_cierre',
    )
    missing = [item for item in required if item not in segment]
    if missing:
        raise SystemExit(f"refactor aborted: expected alert fragments missing: {missing}")
    old_segment = segment
    text = text.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + NEW_IMPORT, 1)
    text = text.replace(old_segment, REPLACEMENT, 1)
    PATH.write_text(text, encoding="utf-8")
    print("alert route extraction applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
