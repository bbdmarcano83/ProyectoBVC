"""Shared Jinja rendering for Caracas Bull."""
from __future__ import annotations

from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader, select_autoescape

from services.bvc import formatear_bs, formatear_entero, formatear_millones


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
    template = env.get_template(template_name)
    return HTMLResponse(template.render(**context))
