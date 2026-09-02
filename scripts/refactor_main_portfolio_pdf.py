"""Deterministically replace legacy portfolio PDF section with direct registration."""
from __future__ import annotations

from pathlib import Path

PATH = Path("main.py")
IMPORT_ANCHOR = "from app.routers.portfolio_import import register_portfolio_import_routes\n"
NEW_IMPORT = "from app.routers.portfolio_pdf import register_portfolio_pdf_routes\n"
START_MARKER = "# ── Reporte PDF ──────────────────────────────────────────────────────────────────\n\n@app.get(\"/portafolio/pdf\")\n"
END_MARKER = "# ── Watchlist ────────────────────────────────────────────────────────────────────\n"
REPLACEMENT = '''# ── Reporte PDF ──────────────────────────────────────────────────────────────────
register_portfolio_pdf_routes(app)


'''


def main() -> int:
    text = PATH.read_text(encoding="utf-8")
    if NEW_IMPORT in text and REPLACEMENT in text:
        print("portfolio pdf extraction already applied")
        return 0
    if IMPORT_ANCHOR not in text:
        raise SystemExit("refactor aborted: portfolio import anchor missing")
    start = text.find(START_MARKER)
    end = text.find(END_MARKER)
    if start < 0 or end < 0 or end <= start:
        raise SystemExit("refactor aborted: portfolio PDF/Watchlist markers not found")
    segment = text[start:end]
    required = (
        '@app.get("/portafolio/pdf")',
        'async def descargar_pdf(',
        'generar_reporte(usuario, filas, resumen, config_tasa)',
        'CaracasBull_Reporte_',
    )
    missing = [item for item in required if item not in segment]
    if missing:
        raise SystemExit(f"refactor aborted: expected portfolio PDF fragments missing: {missing}")
    text = text.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + NEW_IMPORT, 1)
    text = text[:start] + REPLACEMENT + text[end:]
    PATH.write_text(text, encoding="utf-8")
    print("portfolio pdf route extraction applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
