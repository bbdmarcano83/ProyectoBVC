import uvicorn
import asyncio
import os
import json

from fastapi import FastAPI, Form, Request, Depends, Response
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.orm import Session

from database import init_db, get_db
from services.bvc import obtener_datos_bvc, obtener_detalle_profundo, obtener_historico, _to_float, formatear_bs, formatear_entero, formatear_millones, mercado_abierto
from services.portafolio import calcular_fila, resumen_portafolio
from services.auth import (
    crear_usuario, autenticar_usuario, crear_token,
    get_usuario_actual, require_usuario, require_suscripcion,
    suscripcion_activa, dias_restantes, hash_password
)
from services.pagos import crear_pago, verificar_firma_ipn, procesar_webhook, verificar_estado_pago
from database import ActivoPortafolio, Watchlist

app = FastAPI(title="Caracas Bull")

# ── Init DB al arrancar ────────────────────────────────────────────────────────
@app.on_event("startup")
def startup():
    init_db()

# ── Archivos estáticos ─────────────────────────────────────────────────────────
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


# ── Auth ──────────────────────────────────────────────────────────────────────

@app.get("/landing", response_class=HTMLResponse)
async def landing_page(request: Request, db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    return render("landing.html", {"request": request, "usuario": usuario})


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request, db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    if usuario:
        return RedirectResponse(url="/", status_code=302)
    return render("login.html", {"request": request, "error": None})

@app.post("/login", response_class=HTMLResponse)
async def login_post(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    usuario = autenticar_usuario(db, email, password)
    if not usuario:
        return render("login.html", {"request": request, "error": "Email o contraseña incorrectos"})
    
    token = crear_token({"sub": str(usuario.id)})
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie("access_token", token, httponly=True, max_age=60*60*24*7, samesite="lax")
    return response

@app.get("/registro", response_class=HTMLResponse)
async def registro_page(request: Request, db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    if usuario:
        return RedirectResponse(url="/", status_code=302)
    return render("registro.html", {"request": request, "error": None})

@app.post("/registro", response_class=HTMLResponse)
async def registro_post(
    request: Request,
    nombre: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    password2: str = Form(...),
    db: Session = Depends(get_db),
):
    if password != password2:
        return render("registro.html", {"request": request, "error": "Las contraseñas no coinciden"})
    if len(password) < 8:
        return render("registro.html", {"request": request, "error": "La contraseña debe tener al menos 8 caracteres"})
    try:
        usuario = crear_usuario(db, nombre, email, password)
    except ValueError as e:
        return render("registro.html", {"request": request, "error": str(e)})
    
    token = crear_token({"sub": str(usuario.id)})
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie("access_token", token, httponly=True, max_age=60*60*24*7, samesite="lax")
    return response

@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie("access_token")
    return response


# ── Suscripción ───────────────────────────────────────────────────────────────

@app.get("/suscripcion", response_class=HTMLResponse)
async def suscripcion_page(request: Request, mensaje: str = None, db: Session = Depends(get_db)):
    usuario = require_usuario(request, db)
    if isinstance(usuario, RedirectResponse):
        return usuario
    return render("suscripcion.html", {
        "request": request,
        "usuario": usuario,
        "activa": suscripcion_activa(usuario),
        "dias": dias_restantes(usuario),
        "pago": None,
        "mensaje": mensaje,
        "active": "",
    })

@app.post("/suscripcion/pagar")
async def suscripcion_pagar(
    request: Request,
    plan: str = Form(...),
    db: Session = Depends(get_db),
):
    usuario = require_usuario(request, db)
    if isinstance(usuario, RedirectResponse):
        return usuario

    pago = await crear_pago(usuario.id, plan, usuario.email)

    return render("suscripcion.html", {
        "request": request,
        "usuario": usuario,
        "activa": suscripcion_activa(usuario),
        "dias": dias_restantes(usuario),
        "pago": pago,
        "mensaje": None,
        "active": "",
    })

@app.get("/suscripcion/estado/{payment_id}")
async def estado_pago(payment_id: str):
    datos = await verificar_estado_pago(payment_id)
    if datos:
        return JSONResponse({"status": datos.get("payment_status", "waiting")})
    return JSONResponse({"status": "waiting"})

@app.get("/suscripcion/exitosa", response_class=HTMLResponse)
async def suscripcion_exitosa(request: Request, db: Session = Depends(get_db)):
    return RedirectResponse(url="/suscripcion?mensaje=¡Pago recibido! Tu suscripción será activada en minutos.", status_code=302)

@app.post("/webhook/nowpayments")
async def webhook_nowpayments(request: Request, db: Session = Depends(get_db)):
    body = await request.body()
    firma = request.headers.get("x-nowpayments-sig", "")
    if not verificar_firma_ipn(body, firma):
        return JSONResponse({"error": "firma inválida"}, status_code=400)
    datos = json.loads(body)
    procesar_webhook(db, datos)
    return JSONResponse({"ok": True})


# ── Pizarra ───────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index(request: Request, db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    return render("landing.html", {"request": request, "usuario": usuario})


@app.get("/pizarra", response_class=HTMLResponse)
async def pizarra(request: Request, db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/", status_code=302)
    if not suscripcion_activa(usuario):
        return RedirectResponse(url="/suscripcion", status_code=302)

    datos = await obtener_datos_bvc()
    return render("pizarra.html", {
        "request": request,
        "datos": datos,
        "active": "pizarra",
        "usuario": usuario,
        "dias": dias_restantes(usuario),
        "mercado": mercado_abierto(),
    })


# ── Portafolio ────────────────────────────────────────────────────────────────

@app.get("/portafolio", response_class=HTMLResponse)
async def ver_portafolio(request: Request, db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    if not suscripcion_activa(usuario):
        return RedirectResponse(url="/suscripcion", status_code=302)

    datos_bolsa = await obtener_datos_bvc()
    config_tasa = float(os.environ.get("TASA_BCV", "0"))

    activos_db = db.query(ActivoPortafolio).filter(ActivoPortafolio.usuario_id == usuario.id).all()
    portafolio = {
        a.simbolo: {
            "cantidad": a.cantidad,
            "precio_promedio": a.precio_promedio,
            "comision": a.comision,
            "registro": a.registro,
            "iva": a.iva,
        }
        for a in activos_db
    }

    mapa_precios = {item["COD_SIMB"]: _to_float(item.get("PRECIO") or 0) for item in datos_bolsa}
    total_mkt = sum(
        _to_float(d.get("cantidad")) * mapa_precios.get(simb, _to_float(d.get("precio_promedio")))
        for simb, d in portafolio.items()
    )

    filas = [
        calcular_fila(simb, d, mapa_precios.get(simb, _to_float(d.get("precio_promedio"))), total_mkt, config_tasa)
        for simb, d in portafolio.items()
    ]
    resumen = resumen_portafolio(portafolio, datos_bolsa, config_tasa)

    return render("portafolio.html", {
        "request": request,
        "filas": filas,
        "resumen": resumen,
        "tasa": config_tasa,
        "labels": [f["simb"] for f in filas],
        "valores": [round(f["val_mkt"], 2) for f in filas],
        "ganancias": [round(f["ganancia"], 2) for f in filas],
        "active": "portafolio",
        "usuario": usuario,
        "dias": dias_restantes(usuario),
        "mercado": mercado_abierto(),
    })

@app.post("/configurar")
async def configurar(tasa: float = Form(...), request: Request = None, db: Session = Depends(get_db)):
    os.environ["TASA_BCV"] = str(tasa)
    return RedirectResponse(url="/portafolio", status_code=303)

@app.post("/agregar")
async def agregar(
    request: Request,
    simb: str = Form(...), cant: float = Form(...), precio: float = Form(...),
    com: float = Form(0), reg: float = Form(0), iva: float = Form(16),
    db: Session = Depends(get_db),
):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    existente = db.query(ActivoPortafolio).filter(
        ActivoPortafolio.usuario_id == usuario.id,
        ActivoPortafolio.simbolo == simb.upper()
    ).first()
    if existente:
        existente.cantidad = cant
        existente.precio_promedio = precio
        existente.comision = com
        existente.registro = reg
        existente.iva = iva
    else:
        db.add(ActivoPortafolio(
            usuario_id=usuario.id, simbolo=simb.upper(),
            cantidad=cant, precio_promedio=precio, comision=com, registro=reg, iva=iva
        ))
    db.commit()
    return RedirectResponse(url="/portafolio", status_code=303)

@app.post("/editar")
async def editar(
    request: Request,
    simb: str = Form(...), cant: float = Form(...), precio: float = Form(...),
    com: float = Form(0), reg: float = Form(0), iva: float = Form(16),
    db: Session = Depends(get_db),
):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    activo = db.query(ActivoPortafolio).filter(
        ActivoPortafolio.usuario_id == usuario.id,
        ActivoPortafolio.simbolo == simb.upper()
    ).first()
    if activo:
        activo.cantidad = cant
        activo.precio_promedio = precio
        activo.comision = com
        activo.registro = reg
        activo.iva = iva
        db.commit()
    return RedirectResponse(url="/portafolio", status_code=303)

@app.post("/eliminar")
async def eliminar(request: Request, simb: str = Form(...), db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    activo = db.query(ActivoPortafolio).filter(
        ActivoPortafolio.usuario_id == usuario.id,
        ActivoPortafolio.simbolo == simb.upper()
    ).first()
    if activo:
        db.delete(activo)
        db.commit()
    return RedirectResponse(url="/portafolio", status_code=303)


# ── Detalle ───────────────────────────────────────────────────────────────────

@app.get("/detalle/{simbolo}", response_class=HTMLResponse)
async def ver_detalle(request: Request, simbolo: str, db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    if not suscripcion_activa(usuario):
        return RedirectResponse(url="/suscripcion", status_code=302)

    simbolo = simbolo.upper()
    datos_bolsa, prof, historico = await asyncio.gather(
        obtener_datos_bvc(), obtener_detalle_profundo(simbolo), obtener_historico(simbolo)
    )
    activo = next((i for i in datos_bolsa if i.get("COD_SIMB") == simbolo), {})
    series_data = []
    for m in reversed(historico):
        o, h, l, c = _to_float(m.get("PRECIO_APERT")), _to_float(m.get("PRECIO_MAX")), _to_float(m.get("PRECIO_MIN")), _to_float(m.get("PRECIO_CIE"))
        if any([o, h, l, c]):
            series_data.append({"x": m.get("FEC", ""), "y": [o, h, l, c]})

    return render("detalle.html", {
        "request": request, "simbolo": simbolo, "activo": activo,
        "prof": prof, "series_data": series_data, "active": "",
        "usuario": usuario, "dias": dias_restantes(usuario),
    })


# ── Inicio ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
