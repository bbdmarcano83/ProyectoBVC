"""Deterministically replace legacy portfolio import section."""
from __future__ import annotations

from pathlib import Path

PATH = Path("main.py")
IMPORT_ANCHOR = "from app.routers.pwa import register_pwa_routes\n"
NEW_IMPORT = "from app.routers.portfolio_import import register_portfolio_import_routes\n"
START_MARKER = "# ── Importar portafolio ───────────────────────────────────────────────────────\n"
END_MARKER = "# ── Admin ─────────────────────────────────────────────────────────────────────\n"
REPLACEMENT = '''# ── Importar portafolio ───────────────────────────────────────────────────────
register_portfolio_import_routes(app)


'''


def main() -> int:
    text = PATH.read_text(encoding="utf-8")
    if NEW_IMPORT in text and REPLACEMENT in text:
        print("portfolio import extraction already applied")
        return 0
    if IMPORT_ANCHOR not in text:
        raise SystemExit("refactor aborted: pwa import anchor missing")
    start = text.find(START_MARKER)
    end = text.find(END_MARKER)
    if start < 0 or end < 0 or end <= start:
        raise SystemExit("refactor aborted: Importar/Admin markers not found")
    segment = text[start:end]
    required = (
        '@app.get("/portafolio/importar", response_class=HTMLResponse)',
        'async def importar_page(',
        '@app.post("/portafolio/importar", response_class=HTMLResponse)',
        'async def importar_post(',
        '@app.post("/portafolio/importar/confirmar")',
        'async def importar_confirmar(',
    )
    missing = [item for item in required if item not in segment]
    if missing:
        raise SystemExit(f"refactor aborted: expected import fragments missing: {missing}")
    old_segment = segment
    text = text.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + NEW_IMPORT, 1)
    text = text.replace(old_segment, REPLACEMENT, 1)
    PATH.write_text(text, encoding="utf-8")
    print("portfolio import extraction applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
