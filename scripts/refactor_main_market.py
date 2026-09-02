"""Deterministically replace legacy home/pizarra section with direct registration."""
from __future__ import annotations

from pathlib import Path

PATH = Path("main.py")
IMPORT_ANCHOR = "from app.routers.subscription import register_subscription_routes\n"
NEW_IMPORT = "from app.routers.market import register_market_routes\n"
START_MARKER = "# ── Pizarra ───────────────────────────────────────────────────────────────────\n"
END_MARKER = "# ── Scoring (Rotación Sectorial) ──────────────────────────────────────────────\n"
REPLACEMENT = '''# ── Inicio / Pizarra ───────────────────────────────────────────────────────────
register_market_routes(app)


'''


def main() -> int:
    text = PATH.read_text(encoding="utf-8")
    if NEW_IMPORT in text and REPLACEMENT in text:
        print("market extraction already applied")
        return 0
    if IMPORT_ANCHOR not in text:
        raise SystemExit("refactor aborted: subscription import anchor missing")
    start = text.find(START_MARKER)
    end = text.find(END_MARKER)
    if start < 0 or end < 0 or end <= start:
        raise SystemExit("refactor aborted: Pizarra/Scoring markers not found")
    segment = text[start:end]
    required = (
        '@app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)',
        'async def index(',
        '@app.get("/pizarra", response_class=HTMLResponse)',
        'async def pizarra(',
    )
    missing = [item for item in required if item not in segment]
    if missing:
        raise SystemExit(f"refactor aborted: expected market fragments missing: {missing}")
    old_segment = segment
    text = text.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + NEW_IMPORT, 1)
    text = text.replace(old_segment, REPLACEMENT, 1)
    PATH.write_text(text, encoding="utf-8")
    print("market route extraction applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
