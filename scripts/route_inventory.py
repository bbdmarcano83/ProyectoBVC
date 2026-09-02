"""Print the FastAPI route surface in a stable JSON form or SHA-256 digest.

Used only as a refactor guardrail. It imports the application without running
startup events and records user-defined HTTP routes (static mount included).
The frozen digest is intentionally verified after every structural extraction.
"""
from __future__ import annotations

import hashlib
import json
import sys

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


def canonical_json(app) -> str:
    return json.dumps(inventory(app), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(app) -> str:
    return hashlib.sha256(canonical_json(app).encode("utf-8")).hexdigest()


if __name__ == "__main__":
    if "--hash" in sys.argv:
        print(digest(main.app))
    else:
        print(json.dumps(inventory(main.app), ensure_ascii=False, indent=2))
