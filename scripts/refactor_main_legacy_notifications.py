"""Extract duplicated Telegram/Alertas routes and webhook setup from legacy main.py."""
from __future__ import annotations

from pathlib import Path

PATH = Path("main.py")
IMPORT_ANCHOR = "from app.routers.index_market import register_index_market_routes\n"
NEW_IMPORT = (
    "from app.routers.legacy_notifications import "
    "register_legacy_notification_routes, registrar_webhook_telegram\n"
)
ROUTE_START = "# ── Telegram ─────────────────────────────────────────────────────────────────────\n"
ROUTE_END = "# ── API endpoints ────────────────────────────────────────────────────────────────\n"
ROUTE_REPLACEMENT = '''# ── Telegram / Alertas legacy ───────────────────────────────────────────────────
register_legacy_notification_routes(app)


'''
SETUP_START = "# ── Setup Telegram webhook ───────────────────────────────────────────────────────\n"
SETUP_END = "# ── Inicio ─────────────────────────────────────────────────────────────────────\n"


def main() -> int:
    text = PATH.read_text(encoding="utf-8")
    if NEW_IMPORT in text and ROUTE_REPLACEMENT in text and SETUP_START not in text:
        print("legacy notifications extraction already applied")
        return 0
    if IMPORT_ANCHOR not in text:
        raise SystemExit("refactor aborted: index market import anchor missing")

    route_start = text.find(ROUTE_START)
    route_end = text.find(ROUTE_END)
    if route_start < 0 or route_end < 0 or route_end <= route_start:
        raise SystemExit("refactor aborted: Telegram/API markers not found")
    route_segment = text[route_start:route_end]
    required = (
        '@app.post("/telegram/vincular")',
        '@app.post("/webhook/telegram")',
        '@app.get("/alertas", response_class=HTMLResponse)',
        '@app.post("/alertas/crear")',
        '@app.post("/alertas/eliminar")',
        '@app.post("/alertas/reset")',
    )
    for fragment in required:
        if route_segment.count(fragment) != 2:
            raise SystemExit(
                f"refactor aborted: expected exactly two legacy copies of {fragment!r}, "
                f"found {route_segment.count(fragment)}"
            )

    text = text[:route_start] + ROUTE_REPLACEMENT + text[route_end:]

    setup_start = text.find(SETUP_START)
    setup_end = text.find(SETUP_END)
    if setup_start < 0 or setup_end < 0 or setup_end <= setup_start:
        raise SystemExit("refactor aborted: Telegram setup/Inicio markers not found")
    setup_segment = text[setup_start:setup_end]
    if "async def registrar_webhook_telegram():" not in setup_segment:
        raise SystemExit("refactor aborted: Telegram setup function missing")
    text = text[:setup_start] + text[setup_end:]
    text = text.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + NEW_IMPORT, 1)
    PATH.write_text(text, encoding="utf-8")
    print("legacy Telegram/Alertas routes and webhook setup extraction applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
