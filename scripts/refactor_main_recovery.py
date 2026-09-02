"""Deterministically replace legacy password recovery section with direct registration."""
from __future__ import annotations

from pathlib import Path

PATH = Path("main.py")
IMPORT_ANCHOR = "from app.routers.api_misc import register_misc_api_routes\n"
NEW_IMPORT = "from app.routers.recovery import register_recovery_routes\n"
START_MARKER = "# ── Recuperar contraseña ─────────────────────────────────────────────────────────\n"
END_MARKER = "# ── Chat Asistente ───────────────────────────────────────────────────────────────\n"
REPLACEMENT = '''# ── Recuperar contraseña ─────────────────────────────────────────────────────────
register_recovery_routes(app)


'''


def main() -> int:
    text = PATH.read_text(encoding="utf-8")
    if NEW_IMPORT in text and REPLACEMENT in text:
        print("recovery extraction already applied")
        return 0
    if IMPORT_ANCHOR not in text:
        raise SystemExit("refactor aborted: misc api import anchor missing")
    start = text.find(START_MARKER)
    end = text.find(END_MARKER)
    if start < 0 or end < 0 or end <= start:
        raise SystemExit("refactor aborted: Recuperar/Chat markers not found")
    segment = text[start:end]
    required = (
        '@app.get("/recuperar", response_class=HTMLResponse)',
        'async def recuperar_page(',
        '@app.post("/recuperar", response_class=HTMLResponse)',
        'async def recuperar_post(',
        '@app.get("/recuperar/{token}", response_class=HTMLResponse)',
        'async def recuperar_token_page(',
        '@app.post("/recuperar/{token}", response_class=HTMLResponse)',
        'async def recuperar_token_post(',
    )
    missing = [item for item in required if item not in segment]
    if missing:
        raise SystemExit(f"refactor aborted: expected recovery fragments missing: {missing}")
    old_segment = segment
    text = text.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + NEW_IMPORT, 1)
    text = text.replace(old_segment, REPLACEMENT, 1)
    PATH.write_text(text, encoding="utf-8")
    print("recovery route extraction applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
