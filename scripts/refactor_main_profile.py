"""Deterministically replace legacy profile section with direct registration."""
from __future__ import annotations

from pathlib import Path

PATH = Path("main.py")
IMPORT_ANCHOR = "from app.routers.scoring import register_scoring_routes\n"
NEW_IMPORT = "from app.routers.profile import register_profile_routes\n"
START_MARKER = "# ── Perfil ───────────────────────────────────────────────────────────────────────\n"
END_MARKER = "# ── Telegram ─────────────────────────────────────────────────────────────────────\n"
REPLACEMENT = '''# ── Perfil ───────────────────────────────────────────────────────────────────────
register_profile_routes(app)


'''


def main() -> int:
    text = PATH.read_text(encoding="utf-8")
    if NEW_IMPORT in text and REPLACEMENT in text:
        print("profile extraction already applied")
        return 0
    if IMPORT_ANCHOR not in text:
        raise SystemExit("refactor aborted: scoring import anchor missing")
    start = text.find(START_MARKER)
    end = text.find(END_MARKER)
    if start < 0 or end < 0 or end <= start:
        raise SystemExit("refactor aborted: Perfil/Telegram markers not found")
    segment = text[start:end]
    required = (
        '@app.get("/perfil", response_class=HTMLResponse)',
        'async def ver_perfil(',
        '@app.post("/perfil/info")',
        'async def actualizar_info(',
        '@app.post("/perfil/password")',
        'async def cambiar_password(',
        '@app.post("/perfil/eliminar")',
        'async def eliminar_cuenta(',
    )
    missing = [item for item in required if item not in segment]
    if missing:
        raise SystemExit(f"refactor aborted: expected profile fragments missing: {missing}")
    old_segment = segment
    text = text.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + NEW_IMPORT, 1)
    text = text.replace(old_segment, REPLACEMENT, 1)
    PATH.write_text(text, encoding="utf-8")
    print("profile route extraction applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
