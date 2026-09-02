"""Extract both legacy Chat route copies while preserving route order."""
from __future__ import annotations

from pathlib import Path

PATH = Path("main.py")
IMPORT_ANCHOR = "from app.routers.report_pdf import register_report_pdf_routes\n"
NEW_IMPORT = (
    "from app.routers.chat import register_primary_chat_routes, register_secondary_chat_routes\n"
)
CHAT_MARKER = "# ── Chat Asistente ───────────────────────────────────────────────────────────────\n"
REPORT_MARKER = "# ── Reporte PDF ──────────────────────────────────────────────────────────────────\n"
PRIMARY = '''# ── Chat Asistente ───────────────────────────────────────────────────────────────
register_primary_chat_routes(app)


'''
SECONDARY = '''# ── Chat Asistente ───────────────────────────────────────────────────────────────
register_secondary_chat_routes(app)


'''


def _segments(text: str):
    starts = []
    pos = 0
    while True:
        idx = text.find(CHAT_MARKER, pos)
        if idx < 0:
            break
        starts.append(idx)
        pos = idx + len(CHAT_MARKER)
    if len(starts) != 2:
        raise SystemExit(f"refactor aborted: expected 2 chat sections, found {len(starts)}")
    result = []
    for start in starts:
        end = text.find(REPORT_MARKER, start + len(CHAT_MARKER))
        if end < 0:
            raise SystemExit("refactor aborted: Reporte PDF marker after chat not found")
        segment = text[start:end]
        required = ('SYSTEM_PROMPT = """', '@app.get("/chat", response_class=HTMLResponse)', '@app.post("/chat")')
        missing = [item for item in required if item not in segment]
        if missing:
            raise SystemExit(f"refactor aborted: expected chat fragments missing: {missing}")
        result.append((start, end))
    return result


def main() -> int:
    text = PATH.read_text(encoding="utf-8")
    if NEW_IMPORT in text and PRIMARY in text and SECONDARY in text:
        print("chat extraction already applied")
        return 0
    if IMPORT_ANCHOR not in text:
        raise SystemExit("refactor aborted: report PDF import anchor missing")
    segments = _segments(text)
    replacements = (PRIMARY, SECONDARY)
    for (start, end), replacement in reversed(list(zip(segments, replacements))):
        text = text[:start] + replacement + text[end:]
    text = text.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + NEW_IMPORT, 1)
    PATH.write_text(text, encoding="utf-8")
    print("both legacy chat route sections extracted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
