"""Extract Watchlist, Admin and PWA sections without changing route surface."""
from __future__ import annotations

from pathlib import Path

PATH = Path("main.py")
IMPORT_ANCHOR = "from app.routers.portfolio import register_portfolio_routes\n"
NEW_IMPORTS = (
    "from app.routers.watchlist import register_watchlist_routes\n"
    "from app.routers.admin import register_admin_routes\n"
    "from app.routers.pwa import register_pwa_routes\n"
)

SECTIONS = (
    (
        "# ── Watchlist ────────────────────────────────────────────────────────────────────\n",
        "# ── Importar portafolio ───────────────────────────────────────────────────────\n",
        '''# ── Watchlist ────────────────────────────────────────────────────────────────────
register_watchlist_routes(app)


''',
        ('@app.get("/watchlist", response_class=HTMLResponse)', '@app.post("/watchlist/agregar")', '@app.post("/watchlist/eliminar")'),
    ),
    (
        "# ── Admin ─────────────────────────────────────────────────────────────────────\n",
        "# ── PWA ───────────────────────────────────────────────────────────────────────\n",
        '''# ── Admin ─────────────────────────────────────────────────────────────────────
register_admin_routes(app)


''',
        ('@app.get("/admin", response_class=HTMLResponse)', '@app.post("/admin/activar")', '@app.post("/admin/desactivar")'),
    ),
    (
        "# ── PWA ───────────────────────────────────────────────────────────────────────\n",
        "# ── Chat Asistente ───────────────────────────────────────────────────────────────\n",
        '''# ── PWA ───────────────────────────────────────────────────────────────────────
register_pwa_routes(app)


''',
        ('@app.get("/favicon.ico")', '@app.get("/favicon.png")', '@app.get("/manifest.json")', '@app.get("/sw.js")'),
    ),
)


def main() -> int:
    text = PATH.read_text(encoding="utf-8")
    if IMPORT_ANCHOR not in text and NEW_IMPORTS not in text:
        raise SystemExit("refactor aborted: portfolio import anchor missing")
    if NEW_IMPORTS not in text:
        text = text.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + NEW_IMPORTS, 1)

    for start_marker, end_marker, replacement, required in SECTIONS:
        if replacement in text:
            continue
        start = text.find(start_marker)
        end = text.find(end_marker, start + 1) if start >= 0 else -1
        if start < 0 or end < 0 or end <= start:
            raise SystemExit(f"refactor aborted: section markers not found: {start_marker[:20]!r}")
        segment = text[start:end]
        missing = [item for item in required if item not in segment]
        if missing:
            raise SystemExit(f"refactor aborted: expected fragments missing: {missing}")
        text = text.replace(segment, replacement, 1)

    PATH.write_text(text, encoding="utf-8")
    print("watchlist + admin + pwa extraction applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
