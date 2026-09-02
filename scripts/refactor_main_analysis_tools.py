"""Extract Historial, Comparador, ISLR and Índice routes from legacy main.py."""
from __future__ import annotations

from pathlib import Path

PATH = Path("main.py")
IMPORT_ANCHOR = "from app.routers.report_pdf import register_report_pdf_routes\n"
NEW_IMPORTS = (
    "from app.routers.history import register_history_routes\n"
    "from app.routers.comparator import register_comparator_routes\n"
    "from app.routers.islr import register_islr_routes\n"
    "from app.routers.index_market import register_index_market_routes\n"
)
START_MARKER = "# ── Historial de transacciones ───────────────────────────────────────────────────\n"
END_MARKER = "# ── Setup Telegram webhook ───────────────────────────────────────────────────────\n"
REPLACEMENT = '''# ── Historial de transacciones ───────────────────────────────────────────────────
register_history_routes(app)


# ── Comparador de acciones ────────────────────────────────────────────────────
register_comparator_routes(app)


# ── Calculadora ISLR ──────────────────────────────────────────────────────────
register_islr_routes(app)


# ── Índice vs Mercado ─────────────────────────────────────────────────────────
register_index_market_routes(app)


'''


def main() -> int:
    text = PATH.read_text(encoding="utf-8")
    if NEW_IMPORTS in text and REPLACEMENT in text:
        print("analysis tools extraction already applied")
        return 0
    if IMPORT_ANCHOR not in text:
        raise SystemExit("refactor aborted: report PDF import anchor missing")
    start = text.find(START_MARKER)
    end = text.find(END_MARKER)
    if start < 0 or end < 0 or end <= start:
        raise SystemExit("refactor aborted: history/setup Telegram markers not found")
    segment = text[start:end]
    required = (
        '@app.get("/historial", response_class=HTMLResponse)',
        '@app.post("/historial/agregar")',
        '@app.post("/historial/eliminar")',
        '@app.get("/comparador", response_class=HTMLResponse)',
        '@app.get("/islr", response_class=HTMLResponse)',
        '@app.get("/indice", response_class=HTMLResponse)',
    )
    missing = [item for item in required if item not in segment]
    if missing:
        raise SystemExit(f"refactor aborted: expected analysis tool fragments missing: {missing}")
    text = text[:start] + REPLACEMENT + text[end:]
    text = text.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + NEW_IMPORTS, 1)
    PATH.write_text(text, encoding="utf-8")
    print("history/comparator/islr/index extraction applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
