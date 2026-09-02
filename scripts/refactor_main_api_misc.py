"""Deterministically replace legacy misc API section with direct registration."""
from __future__ import annotations

from pathlib import Path

PATH = Path("main.py")
IMPORT_ANCHOR = "from app.routers.detail import register_detail_routes\n"
NEW_IMPORT = "from app.routers.api_misc import register_misc_api_routes\n"
START_MARKER = "# ── API endpoints ────────────────────────────────────────────────────────────────\n"
END_MARKER = "# ── Recuperar contraseña ─────────────────────────────────────────────────────────\n"
REPLACEMENT = '''# ── API endpoints ────────────────────────────────────────────────────────────────
register_misc_api_routes(app)


'''


def main() -> int:
    text = PATH.read_text(encoding="utf-8")
    if NEW_IMPORT in text and REPLACEMENT in text:
        print("misc api extraction already applied")
        return 0
    if IMPORT_ANCHOR not in text:
        raise SystemExit("refactor aborted: detail import anchor missing")
    start = text.find(START_MARKER)
    end = text.find(END_MARKER)
    if start < 0 or end < 0 or end <= start:
        raise SystemExit("refactor aborted: API/Recuperar markers not found")
    segment = text[start:end]
    required = (
        '@app.get("/api/tasa")',
        'async def api_tasa(',
        '@app.get("/api/precio/{simbolo}")',
        'async def api_precio(',
    )
    missing = [item for item in required if item not in segment]
    if missing:
        raise SystemExit(f"refactor aborted: expected misc api fragments missing: {missing}")
    old_segment = segment
    text = text.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + NEW_IMPORT, 1)
    text = text.replace(old_segment, REPLACEMENT, 1)
    PATH.write_text(text, encoding="utf-8")
    print("misc api extraction applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
