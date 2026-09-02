"""Deterministically replace legacy portfolio section with direct registration."""
from __future__ import annotations

from pathlib import Path

PATH = Path("main.py")
IMPORT_ANCHOR = "from app.routers.recovery import register_recovery_routes\n"
NEW_IMPORT = "from app.routers.portfolio import register_portfolio_routes\n"
START_MARKER = "# ── Portafolio ────────────────────────────────────────────────────────────────\n"
END_MARKER = "# ── Detalle ───────────────────────────────────────────────────────────────────\n"
REPLACEMENT = '''# ── Portafolio ────────────────────────────────────────────────────────────────
register_portfolio_routes(app)


'''


def main() -> int:
    text = PATH.read_text(encoding="utf-8")
    if NEW_IMPORT in text and REPLACEMENT in text:
        print("portfolio extraction already applied")
        return 0
    if IMPORT_ANCHOR not in text:
        raise SystemExit("refactor aborted: recovery import anchor missing")
    start = text.find(START_MARKER)
    end = text.find(END_MARKER)
    if start < 0 or end < 0 or end <= start:
        raise SystemExit("refactor aborted: Portafolio/Detalle markers not found")
    segment = text[start:end]
    required = (
        '@app.get("/portafolio", response_class=HTMLResponse)',
        'async def ver_portafolio(',
        '@app.post("/configurar")',
        'async def configurar(',
        '@app.post("/agregar")',
        'async def agregar(',
        '@app.post("/editar")',
        'async def editar(',
        '@app.post("/eliminar")',
        'async def eliminar(',
    )
    missing = [item for item in required if item not in segment]
    if missing:
        raise SystemExit(f"refactor aborted: expected portfolio fragments missing: {missing}")
    old_segment = segment
    text = text.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + NEW_IMPORT, 1)
    text = text.replace(old_segment, REPLACEMENT, 1)
    PATH.write_text(text, encoding="utf-8")
    print("portfolio route extraction applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
