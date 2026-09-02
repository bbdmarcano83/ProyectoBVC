"""Deterministically replace Auth + Subscription sections with routers."""
from __future__ import annotations

from pathlib import Path

PATH = Path("main.py")
IMPORT_ANCHOR = "from app.templating import render\n"
NEW_IMPORTS = (
    "from app.routers.auth import router as auth_router\n"
    "from app.routers.subscription import router as subscription_router\n"
)
AUTH_MARKER = "# ── Auth ──────────────────────────────────────────────────────────────────────\n"
PIZARRA_MARKER = "# ── Pizarra ───────────────────────────────────────────────────────────────────\n"
REPLACEMENT = '''# ── Auth / Suscripción ─────────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(subscription_router)


'''


def main() -> int:
    text = PATH.read_text(encoding="utf-8")
    if REPLACEMENT in text and NEW_IMPORTS in text:
        print("auth/subscription extraction already applied")
        return 0
    if IMPORT_ANCHOR not in text:
        raise SystemExit("refactor aborted: templating import anchor missing")
    start = text.find(AUTH_MARKER)
    end = text.find(PIZARRA_MARKER)
    if start < 0 or end < 0 or end <= start:
        raise SystemExit("refactor aborted: exact Auth/Pizarra section markers not found")
    segment = text[start:end]
    required_fragments = (
        '@app.get("/landing"',
        '@app.get("/login"',
        '@app.post("/login"',
        '@app.get("/registro"',
        '@app.post("/registro"',
        '@app.get("/logout"',
        '@app.get("/suscripcion"',
        '@app.post("/suscripcion/pagar"',
        '@app.get("/suscripcion/estado/{payment_id}"',
        '@app.get("/suscripcion/exitosa"',
        '@app.post("/webhook/nowpayments"',
    )
    missing = [item for item in required_fragments if item not in segment]
    if missing:
        raise SystemExit(f"refactor aborted: expected route fragments missing: {missing}")
    text = text.replace(IMPORT_ANCHOR, IMPORT_ANCHOR + NEW_IMPORTS, 1)
    text = text[:start] + REPLACEMENT + text[end:]
    PATH.write_text(text, encoding="utf-8")
    print("auth + subscription router extraction applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
