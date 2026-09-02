"""Replace APIRouter include calls with direct app registration helpers."""
from __future__ import annotations

from pathlib import Path

PATH = Path("main.py")
OLD_IMPORTS = (
    "from app.routers.auth import router as auth_router\n"
    "from app.routers.subscription import router as subscription_router\n"
)
NEW_IMPORTS = (
    "from app.routers.auth import register_auth_routes\n"
    "from app.routers.subscription import register_subscription_routes\n"
)
OLD_CALLS = "app.include_router(auth_router)\napp.include_router(subscription_router)\n"
NEW_CALLS = "register_auth_routes(app)\nregister_subscription_routes(app)\n"


def main() -> int:
    text = PATH.read_text(encoding="utf-8")
    if NEW_IMPORTS in text and NEW_CALLS in text:
        print("direct registration already applied")
        return 0
    if OLD_IMPORTS not in text or OLD_CALLS not in text:
        raise SystemExit("refactor aborted: expected APIRouter registration not found")
    text = text.replace(OLD_IMPORTS, NEW_IMPORTS, 1)
    text = text.replace(OLD_CALLS, NEW_CALLS, 1)
    PATH.write_text(text, encoding="utf-8")
    print("direct route registration applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
