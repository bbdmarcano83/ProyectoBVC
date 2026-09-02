"""Deterministically extract app construction and Jinja runtime from main.py."""
from __future__ import annotations

from pathlib import Path

PATH = Path("main.py")
IMPORT_ANCHOR = "from app.startup import run_startup\n"
NEW_IMPORTS = "from app.factory import create_app\nfrom app.templating import render\n"
OLD_APP = 'app = FastAPI(title="Caracas Bull")\n'
NEW_APP = "app = create_app()\n"

OLD_RUNTIME = '''# ── Archivos estáticos ─────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory="static"), name="static")

# ── Jinja2 ────────────────────────────────────────────────────────────────────
env = Environment(
    loader=FileSystemLoader("templates"),
    autoescape=select_autoescape(["html"]),
    auto_reload=True,
    cache_size=0,
)
env.filters["format_bs"] = formatear_bs
env.filters["format_entero"] = formatear_entero
env.filters["format_millones"] = formatear_millones

def render(template_name: str, context: dict) -> HTMLResponse:
    t = env.get_template(template_name)
    return HTMLResponse(t.render(**context))


'''


def main() -> int:
    text = PATH.read_text(encoding="utf-8")
    already = NEW_APP in text and NEW_IMPORTS in text and OLD_RUNTIME not in text
    if already:
        print("runtime extraction already applied")
        return 0
    if IMPORT_ANCHOR not in text:
        raise SystemExit("refactor aborted: startup import anchor missing")
    if OLD_APP not in text:
        raise SystemExit("refactor aborted: exact FastAPI construction missing")
    if OLD_RUNTIME not in text:
        raise SystemExit("refactor aborted: exact static/Jinja runtime block missing")
    text = text.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + NEW_IMPORTS, 1)
    text = text.replace(OLD_APP, NEW_APP, 1)
    text = text.replace(OLD_RUNTIME, "", 1)
    PATH.write_text(text, encoding="utf-8")
    print("app factory + templating extraction applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
