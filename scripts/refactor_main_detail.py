"""Deterministically replace legacy detail section with direct registration."""
from __future__ import annotations

from pathlib import Path

PATH = Path("main.py")
IMPORT_ANCHOR = "from app.routers.profile import register_profile_routes\n"
NEW_IMPORT = "from app.routers.detail import register_detail_routes\n"
START_MARKER = "# ── Detalle ───────────────────────────────────────────────────────────────────\n"
END_MARKER = "# ── Perfil ───────────────────────────────────────────────────────────────────────\n"
REPLACEMENT = '''# ── Detalle ───────────────────────────────────────────────────────────────────
register_detail_routes(app)


'''


def main() -> int:
    text = PATH.read_text(encoding="utf-8")
    if NEW_IMPORT in text and REPLACEMENT in text:
        print("detail extraction already applied")
        return 0
    if IMPORT_ANCHOR not in text:
        raise SystemExit("refactor aborted: profile import anchor missing")
    start = text.find(START_MARKER)
    end = text.find(END_MARKER)
    if start < 0 or end < 0 or end <= start:
        raise SystemExit("refactor aborted: Detalle/Perfil markers not found")
    segment = text[start:end]
    required = (
        '@app.get("/detalle/{simbolo}", response_class=HTMLResponse)',
        'async def ver_detalle(',
        'obtener_detalle_profundo',
        'obtener_historico',
    )
    missing = [item for item in required if item not in segment]
    if missing:
        raise SystemExit(f"refactor aborted: expected detail fragments missing: {missing}")
    old_segment = segment
    text = text.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + NEW_IMPORT, 1)
    text = text.replace(old_segment, REPLACEMENT, 1)
    PATH.write_text(text, encoding="utf-8")
    print("detail route extraction applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
