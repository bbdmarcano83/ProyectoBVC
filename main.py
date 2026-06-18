import uvicorn
import asyncio
import os
import json

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape

from services.bvc import (
    obtener_datos_bvc,
    obtener_detalle_profundo,
    obtener_historico,
    _to_float,
    formatear_bs,
)
from services.portafolio import (
    cargar_portafolio,
    guardar_portafolio,
    cargar_config,
    guardar_config,
    agregar_activo,
    eliminar_activo,
    editar_activo,
    calcular_fila,
    resumen_portafolio,
)

app = FastAPI(title="BVC Tracker")

# ── Archivos estáticos ────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory="static"), name="static")

# ── Jinja2 directo (sin Starlette Jinja2Templates para evitar bug de caché) ──
env = Environment(
    loader=FileSystemLoader("templates"),
    autoescape=select_autoescape(["html"]),
    auto_reload=True,
    cache_size=0,  # deshabilita caché completamente
)
env.filters["format_bs"] = formatear_bs


def render(template_name: str, context: dict) -> HTMLResponse:
    t = env.get_template(template_name)
    return HTMLResponse(t.render(**context))


# ── Rutas ─────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def pizarra(request: Request):
    datos = await obtener_datos_bvc()
    return render("pizarra.html", {
        "request": request,
        "datos": datos,
        "active": "pizarra",
    })


@app.get("/portafolio", response_class=HTMLResponse)
async def ver_portafolio(request: Request):
    datos_bolsa = await obtener_datos_bvc()
    portafolio  = cargar_portafolio()
    config      = cargar_config()
    tasa        = _to_float(config.get("tasa", 0))

    mapa_precios = {
        item["COD_SIMB"]: _to_float(item.get("PRECIO") or 0)
        for item in datos_bolsa
    }

    total_mkt = sum(
        _to_float(d.get("cantidad")) * mapa_precios.get(simb, _to_float(d.get("precio_promedio")))
        for simb, d in portafolio.items()
    )

    filas = [
        calcular_fila(
            simb, d,
            precio_actual=mapa_precios.get(simb, _to_float(d.get("precio_promedio"))),
            total_mkt=total_mkt,
            tasa=tasa,
        )
        for simb, d in portafolio.items()
    ]

    resumen = resumen_portafolio(portafolio, datos_bolsa, tasa)

    labels    = [f["simb"] for f in filas]
    valores   = [round(f["val_mkt"], 2) for f in filas]
    ganancias = [round(f["ganancia"], 2) for f in filas]

    return render("portafolio.html", {
        "request":   request,
        "filas":     filas,
        "resumen":   resumen,
        "tasa":      tasa,
        "labels":    labels,
        "valores":   valores,
        "ganancias": ganancias,
        "active":    "portafolio",
    })


@app.get("/detalle/{simbolo}", response_class=HTMLResponse)
async def ver_detalle(request: Request, simbolo: str):
    simbolo = simbolo.upper()
    datos_bolsa, prof, historico = await asyncio.gather(
        obtener_datos_bvc(),
        obtener_detalle_profundo(simbolo),
        obtener_historico(simbolo),
    )

    activo = next((i for i in datos_bolsa if i.get("COD_SIMB") == simbolo), {})

    series_data = []
    for m in reversed(historico):
        o = _to_float(m.get("PRECIO_APERT"))
        h = _to_float(m.get("PRECIO_MAX"))
        l = _to_float(m.get("PRECIO_MIN"))
        c = _to_float(m.get("PRECIO_CIE"))
        if any([o, h, l, c]):
            series_data.append({"x": m.get("FEC", ""), "y": [o, h, l, c]})

    return render("detalle.html", {
        "request":     request,
        "simbolo":     simbolo,
        "activo":      activo,
        "prof":        prof,
        "series_data": series_data,
        "active":      "",
    })


# ── Acciones del portafolio ───────────────────────────────────────────────────

@app.post("/configurar")
async def configurar(tasa: float = Form(...)):
    guardar_config(tasa)
    return RedirectResponse(url="/portafolio", status_code=303)


@app.post("/agregar")
async def agregar(
    simb:   str   = Form(...),
    cant:   float = Form(...),
    precio: float = Form(...),
    com:    float = Form(0),
    reg:    float = Form(0),
    iva:    float = Form(16),
):
    agregar_activo(simb, cant, precio, com, reg, iva)
    return RedirectResponse(url="/portafolio", status_code=303)


@app.post("/editar")
async def editar(
    simb:   str   = Form(...),
    cant:   float = Form(...),
    precio: float = Form(...),
    com:    float = Form(0),
    reg:    float = Form(0),
    iva:    float = Form(16),
):
    editar_activo(simb, cant, precio, com, reg, iva)
    return RedirectResponse(url="/portafolio", status_code=303)


@app.post("/eliminar")
async def eliminar(simb: str = Form(...)):
    eliminar_activo(simb)
    return RedirectResponse(url="/portafolio", status_code=303)


# ── Inicio ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)