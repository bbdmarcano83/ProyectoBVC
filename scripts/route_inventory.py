"""Print the FastAPI route surface in a stable JSON form.

Used only as a refactor guardrail. It imports the application without running
startup events and records user-defined HTTP routes (static mount included).
"""
from __future__ import annotations

import json

import main


def inventory(app) -> list[dict]:
    rows = []
    for route in app.routes:
        path = str(getattr(route, "path", ""))
        name = str(getattr(route, "name", ""))
        methods = sorted(str(x) for x in (getattr(route, "methods", None) or []))
        # Ignore FastAPI-generated docs/OpenAPI routes; they are framework surface.
        if path in {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}:
            continue
        rows.append({"path": path, "methods": methods, "name": name})
    return sorted(rows, key=lambda x: (x["path"], x["methods"], x["name"]))


if __name__ == "__main__":
    print(json.dumps(inventory(main.app), ensure_ascii=False, indent=2))
