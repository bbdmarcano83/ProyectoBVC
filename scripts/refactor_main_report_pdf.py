"""Deterministically replace legacy /reporte/pdf section with direct registration."""
from __future__ import annotations

from pathlib import Path

PATH = Path("main.py")
IMPORT_ANCHOR = "from app.routers.portfolio_pdf import register_portfolio_pdf_routes\n"
NEW_IMPORT = "from app.routers.report_pdf import register_report_pdf_routes\n"
START_MARKER = "# ── Reporte PDF ──────────────────────────────────────────────────────────────────\n\n@app.get(\"/reporte/pdf\")\n"
END_MARKER = "# ── Historial de transacciones ───────────────────────────────────────────────────\n"
REPLACEMENT = '''# ── Reporte PDF ──────────────────────────────────────────────────────────────────
register_report_pdf_routes(app)


'''


def main() -> int:
    text = PATH.read_text(encoding="utf-8")
    if NEW_IMPORT in text and REPLACEMENT in text:
        print("report pdf extraction already applied")
        return 0
    if IMPORT_ANCHOR not in text:
        raise SystemExit("refactor aborted: portfolio PDF import anchor missing")
    start = text.find(START_MARKER)
    end = text.find(END_MARKER)
    if start < 0 or end < 0 or end <= start:
        raise SystemExit("refactor aborted: /reporte/pdf or Historial markers not found")
    segment = text[start:end]
    required = (
        '@app.get("/reporte/pdf")',
        'async def descargar_reporte(',
        'usuario_nombre=usuario.nombre',
        'reporte_caracasbull_',
    )
    missing = [item for item in required if item not in segment]
    if missing:
        raise SystemExit(f"refactor aborted: expected report PDF fragments missing: {missing}")
    text = text[:start] + REPLACEMENT + text[end:]
    text = text.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + NEW_IMPORT, 1)
    PATH.write_text(text, encoding="utf-8")
    print("report pdf route extraction applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
