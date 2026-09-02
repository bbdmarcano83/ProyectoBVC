"""Deterministically replace legacy bitácora section with direct registration."""
from __future__ import annotations

from pathlib import Path

PATH = Path("main.py")
IMPORT_ANCHOR = "from app.routers.market import register_market_routes\n"
NEW_IMPORT = "from app.routers.bitacora import register_bitacora_routes\n"
START_MARKER = "# ── Bitácora ──────────────────────────────────────────────────────────────────\n"
END_MARKER = "# ── Portafolio ────────────────────────────────────────────────────────────────\n"
REPLACEMENT = '''# ── Bitácora ──────────────────────────────────────────────────────────────────
register_bitacora_routes(app)


'''


def main() -> int:
    text = PATH.read_text(encoding="utf-8")
    if NEW_IMPORT in text and REPLACEMENT in text:
        print("bitacora extraction already applied")
        return 0
    if IMPORT_ANCHOR not in text:
        raise SystemExit("refactor aborted: market import anchor missing")
    start = text.find(START_MARKER)
    end = text.find(END_MARKER)
    if start < 0 or end < 0 or end <= start:
        raise SystemExit("refactor aborted: Bitácora/Portafolio markers not found")
    segment = text[start:end]
    required = (
        '@app.get("/bitacora", response_class=HTMLResponse)',
        'async def ver_bitacora(',
        '@app.post("/api/bitacora", response_class=JSONResponse)',
        'async def crear_entrada_bitacora(',
        '@app.delete("/api/bitacora/{tx_id}", response_class=JSONResponse)',
        'async def eliminar_bitacora(',
    )
    missing = [item for item in required if item not in segment]
    if missing:
        raise SystemExit(f"refactor aborted: expected bitacora fragments missing: {missing}")
    old_segment = segment
    text = text.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + NEW_IMPORT, 1)
    text = text.replace(old_segment, REPLACEMENT, 1)
    PATH.write_text(text, encoding="utf-8")
    print("bitacora route extraction applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
