import uvicorn
import asyncio
import os
import json
import httpx

from fastapi import FastAPI, Form, Request, Depends, Response
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.orm import Session

from database import init_db, get_db, SessionLocal, AlertaPrecio, TransaccionHistorial
from services.alertas_worker import loop_alertas
from services.bvc import obtener_datos_bvc, obtener_detalle_profundo, obtener_historico, _to_float, formatear_bs, formatear_entero, formatear_millones, mercado_abierto, obtener_tasa_bcv
from services.portafolio import calcular_fila, resumen_portafolio
from services.auth import (
    crear_usuario, autenticar_usuario, crear_token,
    get_usuario_actual, require_usuario, require_suscripcion,
    suscripcion_activa, dias_restantes, hash_password
)
from services.pagos import crear_pago, verificar_firma_ipn, procesar_webhook, verificar_estado_pago
from services.importador import importar_archivo
import httpx as httpx_client
from services.pdf_reporte import generar_reporte
from services.email import email_recuperar_password, email_bienvenida
from database import ActivoPortafolio, Watchlist

app = FastAPI(title="Caracas Bull")

# ── Init DB al arrancar ────────────────────────────────────────────────────────
@app.on_event("startup")
async def startup():
    init_db()
    _migrar_db()
    _crear_admin_si_no_existe()
    # Arrancar worker de alertas en background
    asyncio.create_task(loop_alertas())
    # Registrar webhook de Telegram
    await registrar_webhook_telegram()


def _migrar_db():
    """Agrega columnas nuevas a tablas existentes sin borrar datos."""
    from sqlalchemy import text
    migraciones = [
        "ALTER TABLE usuarios ADD COLUMN telegram_chat_id VARCHAR(50)",
        "ALTER TABLE usuarios ADD COLUMN telegram_codigo VARCHAR(10)",
        "ALTER TABLE usuarios ADD COLUMN broker VARCHAR(50)",
        "ALTER TABLE usuarios ADD COLUMN token_recuperacion VARCHAR(100)",
        "ALTER TABLE usuarios ADD COLUMN token_expira DATETIME",
        """CREATE TABLE IF NOT EXISTS transacciones (
            id INTEGER PRIMARY KEY,
            usuario_id INTEGER REFERENCES usuarios(id),
            simbolo VARCHAR(20),
            tipo VARCHAR(10),
            cantidad FLOAT,
            precio FLOAT,
            comision FLOAT DEFAULT 0,
            registro FLOAT DEFAULT 0,
            iva FLOAT DEFAULT 16,
            fecha DATETIME DEFAULT CURRENT_TIMESTAMP,
            notas VARCHAR(200)
        )""",
    ]
    with SessionLocal() as db:
        for sql in migraciones:
            try:
                db.execute(text(sql))
                db.commit()
                print(f"[Migración] OK: {sql}")
            except Exception:
                pass  # La columna ya existe, ignorar


def _crear_admin_si_no_existe():
    """Crea la cuenta admin en producción si no existe. Lee credenciales de variables de entorno."""
    import os
    from datetime import datetime, timedelta
    from services.auth import hash_password

    email    = os.environ.get("ADMIN_EMAIL", "")
    password = os.environ.get("ADMIN_PASSWORD", "")
    nombre   = os.environ.get("ADMIN_NOMBRE", "Admin")

    if not email or not password:
        return  # No configurado, saltar

    db = SessionLocal()
    try:
        from database import Usuario, Suscripcion
        if db.query(Usuario).filter(Usuario.email == email).first():
            return  # Ya existe

        usuario = Usuario(
            nombre=nombre,
            email=email,
            password_hash=hash_password(password),
            es_admin=True,
            activo=True,
        )
        db.add(usuario)
        db.flush()

        suscripcion = Suscripcion(
            usuario_id=usuario.id,
            plan="pro",
            activa=True,
            fecha_inicio=datetime.utcnow(),
            fecha_vence=datetime.utcnow() + timedelta(days=365 * 100),
        )
        db.add(suscripcion)
        db.commit()
        print(f"[startup] Admin creado: {email}")
    except Exception as e:
        print(f"[startup] Error creando admin: {e}")
        db.rollback()
    finally:
        db.close()

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
        "mercado": mercado_abierto(),
    })

@app.post("/suscripcion/pagar")
async def suscripcion_pagar(
    request: Request,
    plan: str = Form(...),
    db: Session = Depends(get_db),
):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)

    pago = await crear_pago(usuario.id, plan, usuario.email)
    mensaje_error = None

    if not pago:
        mensaje_error = "Error al conectar con el sistema de pagos. Verifica que NOWPAYMENTS_API_KEY esté configurada en Render."

    return render("suscripcion.html", {
        "request": request,
        "usuario": usuario,
        "activa": suscripcion_activa(usuario),
        "dias": dias_restantes(usuario),
        "pago": pago,
        "mensaje": mensaje_error,
        "active": "",
        "mercado": mercado_abierto(),
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

@app.api_route("/", methods=["GET", "HEAD"], response_class=HTMLResponse)
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
    # Tasa BCV automática con fallback a la configurada manualmente
    tasa_auto = await obtener_tasa_bcv()
    config_tasa = tasa_auto if tasa_auto > 0 else float(os.environ.get("TASA_BCV", "0"))

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
        # Promediar precio y sumar cantidades automaticamente
        cant_total = existente.cantidad + cant
        precio_prom = ((existente.precio_promedio * existente.cantidad) + (precio * cant)) / cant_total
        existente.cantidad = cant_total
        existente.precio_promedio = round(precio_prom, 2)
        existente.comision = existente.comision + com
        existente.registro = existente.registro + reg
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
    volume_data = []
    for m in reversed(historico):
        o = _to_float(m.get("PRECIO_APERT"))
        h = _to_float(m.get("PRECIO_MAX"))
        l = _to_float(m.get("PRECIO_MIN"))
        c = _to_float(m.get("PRECIO_CIE"))
        # TOT_ACC_NEGOC = titulos negociados, TOT_MONTO_NEGOC = monto en Bs
        v     = _to_float(m.get("TOT_ACC_NEGOC") or 0)
        monto = _to_float(m.get("TOT_MONTO_NEGOC") or 0)
        ops   = _to_float(m.get("TOT_OP_NEGOC") or 0)
        fecha = m.get("FEC", "")
        if any([o, h, l, c]):
            series_data.append({"x": fecha, "y": [o, h, l, c]})
            volume_data.append({"x": fecha, "y": v, "monto": monto, "ops": int(ops), "isUp": c >= o})

    # Vela del dia en curso
    from datetime import datetime
    try:
        import pytz
        vet = pytz.timezone("America/Caracas")
        hoy = datetime.now(vet).strftime("%d/%m/%Y")
    except Exception:
        from datetime import timezone, timedelta
        hoy = datetime.now(timezone(timedelta(hours=-4))).strftime("%d/%m/%Y")

    precio_actual = _to_float(activo.get("PRECIO"))
    apert  = _to_float(prof.get("HOY_APERT") or precio_actual)
    maximo = _to_float(prof.get("HOY_MAX")   or precio_actual)
    minimo = _to_float(prof.get("HOY_MIN")   or precio_actual)
    vol_hoy = _to_float(activo.get("VOLUMEN") or 0)

    vela_hoy = None
    if precio_actual > 0:
        vela_hoy = {"x": hoy, "y": [apert, maximo, minimo, precio_actual]}

    vol_hoy_data = None
    if vol_hoy > 0:
        vol_hoy_data = {"x": hoy, "y": vol_hoy, "isUp": precio_actual >= apert}

    return render("detalle.html", {
        "request": request, "simbolo": simbolo, "activo": activo,
        "prof": prof, "series_data": series_data,
        "volume_data": volume_data,
        "vela_hoy": vela_hoy,
        "vol_hoy_data": vol_hoy_data,
        "active": "",
        "usuario": usuario, "dias": dias_restantes(usuario),
        "mercado": mercado_abierto(),
    })


# ── Perfil ───────────────────────────────────────────────────────────────────────

@app.get("/perfil", response_class=HTMLResponse)
async def ver_perfil(request: Request, db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    return render("perfil.html", {
        "request": request,
        "usuario": usuario,
        "dias": dias_restantes(usuario),
        "mercado": mercado_abierto(),
        "active": "",
        "msg_info": None, "msg_pass": None,
        "error_pass": False,
    })


@app.post("/perfil/info")
async def actualizar_info(
    request: Request,
    nombre: str = Form(...),
    email: str = Form(...),
    broker: str = Form(""),
    db: Session = Depends(get_db),
):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    usuario.nombre = nombre.strip()
    usuario.email  = email.strip().lower()
    db.commit()
    return render("perfil.html", {
        "request": request, "usuario": usuario,
        "dias": dias_restantes(usuario), "mercado": mercado_abierto(),
        "active": "", "msg_info": "Datos actualizados correctamente",
        "msg_pass": None, "error_pass": False,
    })


@app.post("/perfil/password")
async def cambiar_password(
    request: Request,
    password_actual: str = Form(...),
    password_nueva: str = Form(...),
    password_nueva2: str = Form(...),
    db: Session = Depends(get_db),
):
    from services.auth import verificar_password, hash_password
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)

    if not verificar_password(password_actual, usuario.password_hash):
        return render("perfil.html", {
            "request": request, "usuario": usuario,
            "dias": dias_restantes(usuario), "mercado": mercado_abierto(),
            "active": "", "msg_info": None,
            "msg_pass": "Contraseña actual incorrecta", "error_pass": True,
        })
    if password_nueva != password_nueva2:
        return render("perfil.html", {
            "request": request, "usuario": usuario,
            "dias": dias_restantes(usuario), "mercado": mercado_abierto(),
            "active": "", "msg_info": None,
            "msg_pass": "Las contraseñas nuevas no coinciden", "error_pass": True,
        })
    if len(password_nueva) < 8:
        return render("perfil.html", {
            "request": request, "usuario": usuario,
            "dias": dias_restantes(usuario), "mercado": mercado_abierto(),
            "active": "", "msg_info": None,
            "msg_pass": "La contraseña debe tener al menos 8 caracteres", "error_pass": True,
        })

    usuario.password_hash = hash_password(password_nueva)
    db.commit()
    return render("perfil.html", {
        "request": request, "usuario": usuario,
        "dias": dias_restantes(usuario), "mercado": mercado_abierto(),
        "active": "", "msg_info": None,
        "msg_pass": "Contraseña cambiada correctamente", "error_pass": False,
    })


@app.post("/perfil/eliminar")
async def eliminar_cuenta(
    request: Request,
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    from services.auth import verificar_password
    usuario = get_usuario_actual(request, db)
    if not usuario or not verificar_password(password, usuario.password_hash):
        return RedirectResponse(url="/perfil", status_code=302)
    db.delete(usuario)
    db.commit()
    response = RedirectResponse(url="/", status_code=302)
    response.delete_cookie("access_token")
    return response


# ── Telegram ─────────────────────────────────────────────────────────────────────

@app.post("/telegram/vincular")
async def vincular_telegram(request: Request, db: Session = Depends(get_db)):
    import random, string
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return JSONResponse({"error": "no autorizado"}, status_code=401)
    # Generar código de 6 dígitos
    codigo = "".join(random.choices(string.digits, k=6))
    usuario.telegram_codigo = codigo
    db.commit()
    return JSONResponse({"codigo": codigo, "bot": "@CaracasBullBot"})


@app.post("/webhook/telegram")
async def webhook_telegram(request: Request, db: Session = Depends(get_db)):
    from services.telegram import verificar_codigo
    datos = await request.json()
    mensaje = datos.get("message", {})
    chat_id = str(mensaje.get("chat", {}).get("id", ""))
    texto   = mensaje.get("text", "").strip()

    if not chat_id:
        return JSONResponse({"ok": True})

    if texto.startswith("/start "):
        codigo = texto.replace("/start ", "").strip()
        await verificar_codigo(chat_id, codigo, db)
    elif texto == "/start":
        from services.telegram import enviar_mensaje
        msg = "Bienvenido a CaracasBull. Ve a tu perfil y haz clic en Vincular Telegram."
        await enviar_mensaje(chat_id, msg)
    elif texto == "/status":
        from services.telegram import enviar_mensaje
        from database import Usuario as UsuarioModel
        u = db.query(UsuarioModel).filter(UsuarioModel.telegram_chat_id == chat_id).first()
        if u:
            plan = u.suscripcion.plan if u.suscripcion else "trial"
            await enviar_mensaje(chat_id, f"Cuenta vinculada: {u.nombre} | Plan: {plan}")
        else:
            await enviar_mensaje(chat_id, "No hay cuenta vinculada a este chat.")

    return JSONResponse({"ok": True})


# ── Alertas ───────────────────────────────────────────────────────────────────────

@app.get("/alertas", response_class=HTMLResponse)
async def ver_alertas(request: Request, db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    alertas = db.query(AlertaPrecio).filter(
        AlertaPrecio.usuario_id == usuario.id
    ).order_by(AlertaPrecio.creado_en.desc()).all()
    datos_bolsa = await obtener_datos_bvc()
    simbolos = sorted([item["COD_SIMB"] for item in datos_bolsa])
    return render("alertas.html", {
        "request": request, "usuario": usuario,
        "alertas": alertas, "simbolos": simbolos,
        "dias": dias_restantes(usuario),
        "mercado": mercado_abierto(), "active": "",
    })


@app.post("/alertas/crear")
async def crear_alerta(
    request: Request,
    simbolo:    str   = Form(...),
    tipo:       str   = Form(...),
    porcentaje: float = Form(...),
    db: Session = Depends(get_db),
):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    db.add(AlertaPrecio(
        usuario_id=usuario.id,
        simbolo=simbolo.upper(),
        tipo=tipo,
        porcentaje=porcentaje,
        activa=True,
        disparada=False,
    ))
    db.commit()
    return RedirectResponse(url="/alertas", status_code=303)


@app.post("/alertas/eliminar")
async def eliminar_alerta(
    request: Request,
    alerta_id: int = Form(...),
    db: Session = Depends(get_db),
):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    alerta = db.query(AlertaPrecio).filter(
        AlertaPrecio.id == alerta_id,
        AlertaPrecio.usuario_id == usuario.id,
    ).first()
    if alerta:
        db.delete(alerta)
        db.commit()
    return RedirectResponse(url="/alertas", status_code=303)


@app.post("/alertas/reset")
async def reset_alerta(
    request: Request,
    alerta_id: int = Form(...),
    db: Session = Depends(get_db),
):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    alerta = db.query(AlertaPrecio).filter(
        AlertaPrecio.id == alerta_id,
        AlertaPrecio.usuario_id == usuario.id,
    ).first()
    if alerta:
        alerta.disparada = False
        db.commit()
    return RedirectResponse(url="/alertas", status_code=303)


# ── Telegram ─────────────────────────────────────────────────────────────────────

@app.post("/telegram/vincular")
async def vincular_telegram(request: Request, db: Session = Depends(get_db)):
    import random, string
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return JSONResponse({"error": "no autorizado"}, status_code=401)
    codigo = "".join(random.choices(string.digits, k=6))
    usuario.telegram_codigo = codigo
    db.commit()
    return JSONResponse({"codigo": codigo, "bot": "@CaracasBullBot"})


@app.post("/webhook/telegram")
async def webhook_telegram(request: Request, db: Session = Depends(get_db)):
    from services.telegram import verificar_codigo, enviar_mensaje
    from database import Usuario as UsuarioModel
    datos = await request.json()
    mensaje = datos.get("message", {})
    chat_id = str(mensaje.get("chat", {}).get("id", ""))
    texto   = mensaje.get("text", "").strip()
    if not chat_id:
        return JSONResponse({"ok": True})
    if texto.startswith("/start "):
        codigo = texto.replace("/start ", "").strip()
        await verificar_codigo(chat_id, codigo, db)
    elif texto == "/start":
        bienvenida = "Bienvenido a CaracasBull. Ve a tu perfil y haz clic en Vincular Telegram."
        await enviar_mensaje(chat_id, bienvenida)
    elif texto == "/status":
        u = db.query(UsuarioModel).filter(UsuarioModel.telegram_chat_id == chat_id).first()
        if u:
            plan = u.suscripcion.plan if u.suscripcion else "trial"
            await enviar_mensaje(chat_id, f"Cuenta vinculada: {u.nombre} | Plan: {plan}")
        else:
            await enviar_mensaje(chat_id, "No hay cuenta vinculada a este chat.")
    return JSONResponse({"ok": True})


# ── Alertas ───────────────────────────────────────────────────────────────────────

@app.get("/alertas", response_class=HTMLResponse)
async def ver_alertas(request: Request, db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    alertas = db.query(AlertaPrecio).filter(
        AlertaPrecio.usuario_id == usuario.id
    ).order_by(AlertaPrecio.creado_en.desc()).all()
    datos_bolsa = await obtener_datos_bvc()
    simbolos = sorted([item["COD_SIMB"] for item in datos_bolsa])
    return render("alertas.html", {
        "request": request, "usuario": usuario,
        "alertas": alertas, "simbolos": simbolos,
        "dias": dias_restantes(usuario),
        "mercado": mercado_abierto(), "active": "",
    })


@app.post("/alertas/crear")
async def crear_alerta(
    request: Request,
    simbolo:    str   = Form(...),
    tipo:       str   = Form(...),
    porcentaje: float = Form(...),
    db: Session = Depends(get_db),
):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    db.add(AlertaPrecio(
        usuario_id=usuario.id,
        simbolo=simbolo.upper(),
        tipo=tipo,
        porcentaje=porcentaje,
        activa=True,
        disparada=False,
    ))
    db.commit()
    return RedirectResponse(url="/alertas", status_code=303)


@app.post("/alertas/eliminar")
async def eliminar_alerta(
    request: Request,
    alerta_id: int = Form(...),
    db: Session = Depends(get_db),
):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    alerta = db.query(AlertaPrecio).filter(
        AlertaPrecio.id == alerta_id,
        AlertaPrecio.usuario_id == usuario.id,
    ).first()
    if alerta:
        db.delete(alerta)
        db.commit()
    return RedirectResponse(url="/alertas", status_code=303)


@app.post("/alertas/reset")
async def reset_alerta(
    request: Request,
    alerta_id: int = Form(...),
    db: Session = Depends(get_db),
):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    alerta = db.query(AlertaPrecio).filter(
        AlertaPrecio.id == alerta_id,
        AlertaPrecio.usuario_id == usuario.id,
    ).first()
    if alerta:
        alerta.disparada = False
        db.commit()
    return RedirectResponse(url="/alertas", status_code=303)


# ── API endpoints ────────────────────────────────────────────────────────────────

@app.get("/api/tasa")
async def api_tasa():
    """Devuelve la tasa BCV actual."""
    tasa = await obtener_tasa_bcv()
    return JSONResponse({"tasa": tasa, "fuente": "BCV" if tasa > 0 else "manual"})


@app.get("/api/precio/{simbolo}")
async def api_precio(simbolo: str, request: Request, db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return JSONResponse({"error": "no autorizado"}, status_code=401)
    datos = await obtener_datos_bvc()
    activo = next((i for i in datos if i.get("COD_SIMB") == simbolo.upper()), None)
    if not activo:
        return JSONResponse({"error": "no encontrado"}, status_code=404)
    return JSONResponse({
        "precio":  _to_float(activo.get("PRECIO")),
        "var_rel": _to_float(activo.get("VAR_REL")),
        "var_abs": _to_float(activo.get("VAR_ABS")),
    })


# ── Recuperar contraseña ─────────────────────────────────────────────────────────

@app.get("/recuperar", response_class=HTMLResponse)
async def recuperar_page(request: Request):
    return render("recuperar.html", {"request": request, "modo": "solicitar", "error": None, "mensaje": None, "token": None})

@app.post("/recuperar", response_class=HTMLResponse)
async def recuperar_post(request: Request, email: str = Form(...), db: Session = Depends(get_db)):
    import secrets
    from datetime import datetime, timedelta
    from database import Usuario as UsuarioModel
    usuario = db.query(UsuarioModel).filter(UsuarioModel.email == email.lower().strip()).first()
    if usuario:
        token = secrets.token_urlsafe(32)
        usuario.token_recuperacion = token
        usuario.token_expira = datetime.utcnow() + timedelta(minutes=30)
        db.commit()
        app_url = os.environ.get("APP_URL", "https://caracasbull.com")
        import asyncio
        asyncio.create_task(asyncio.to_thread(email_recuperar_password, usuario.email, usuario.nombre, token, app_url))
    return render("recuperar.html", {
        "request": request, "modo": "solicitar", "error": None,
        "mensaje": "Si el email existe, recibirás un enlace en minutos.", "token": None
    })

@app.get("/recuperar/{token}", response_class=HTMLResponse)
async def recuperar_token_page(request: Request, token: str, db: Session = Depends(get_db)):
    from datetime import datetime
    from database import Usuario as UsuarioModel
    usuario = db.query(UsuarioModel).filter(UsuarioModel.token_recuperacion == token).first()
    if not usuario or not usuario.token_expira or datetime.utcnow() > usuario.token_expira:
        return render("recuperar.html", {"request": request, "modo": "expirado", "error": None, "mensaje": None, "token": None})
    return render("recuperar.html", {"request": request, "modo": "nueva", "error": None, "mensaje": None, "token": token})

@app.post("/recuperar/{token}", response_class=HTMLResponse)
async def recuperar_token_post(
    request: Request, token: str,
    password: str = Form(...), password2: str = Form(...),
    db: Session = Depends(get_db)
):
    from datetime import datetime
    from database import Usuario as UsuarioModel
    from services.auth import hash_password
    usuario = db.query(UsuarioModel).filter(UsuarioModel.token_recuperacion == token).first()
    if not usuario or not usuario.token_expira or datetime.utcnow() > usuario.token_expira:
        return render("recuperar.html", {"request": request, "modo": "expirado", "error": None, "mensaje": None, "token": None})
    if password != password2:
        return render("recuperar.html", {"request": request, "modo": "nueva", "error": "Las contraseñas no coinciden", "mensaje": None, "token": token})
    if len(password) < 8:
        return render("recuperar.html", {"request": request, "modo": "nueva", "error": "Mínimo 8 caracteres", "mensaje": None, "token": token})
    usuario.password_hash = hash_password(password)
    usuario.token_recuperacion = None
    usuario.token_expira = None
    db.commit()
    return render("recuperar.html", {"request": request, "modo": "ok", "error": None, "mensaje": None, "token": None})


# ── Chat Asistente ───────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Eres el asistente virtual de Caracas Bull, una plataforma de INFORMACION y ANALISIS del mercado bursatil de Caracas (BVC).

IMPORTANTE:
- NO somos broker, NO realizamos operaciones bursatiles
- NO damos asesoria de inversion ni recomendaciones para comprar/vender
- Solo proporcionamos informacion y herramientas de analisis

Puedes ayudar con:
- Como usar las funciones de la app (pizarra, portafolio, alertas, watchlist, comparador, ISLR, historial)
- Informacion general sobre la BVC y como funciona
- Problemas tecnicos con la plataforma
- Dudas sobre pagos y suscripciones (planes: Basico 1.5 USDT/mes, Pro 2.99 USDT/mes lanzamiento)
- Como vincular Telegram para alertas
- Como importar portafolio desde Excel/CSV

Si el usuario tiene un problema urgente de pago o tecnico grave, dile que escribe "soporte" para notificar al equipo.

Responde siempre en español, de forma amigable y concisa. Maximo 3 parrafos."""


@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request, db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    return render("chat.html", {
        "request": request, "usuario": usuario,
        "dias": dias_restantes(usuario), "mercado": mercado_abierto(), "active": "",
    })


@app.post("/chat")
async def chat_api(request: Request, db: Session = Depends(get_db)):
    import os
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return JSONResponse({"error": "no autorizado"}, status_code=401)

    body = await request.json()
    messages = body.get("messages", [])
    necesita_soporte = body.get("necesita_soporte", False)

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    respuesta = ""

    if api_key:
        try:
            async with httpx_client.AsyncClient(timeout=30.0) as client:
                r = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": "claude-haiku-4-5-20251001",
                        "max_tokens": 500,
                        "system": SYSTEM_PROMPT,
                        "messages": messages[-10:],  # últimos 10 mensajes
                    }
                )
                if r.status_code == 200:
                    respuesta = r.json()["content"][0]["text"]
                else:
                    respuesta = "Lo siento, tuve un problema técnico. Intenta de nuevo en un momento."
        except Exception as e:
            print(f"[Chat] Error: {e}")
            respuesta = "Lo siento, no puedo responder en este momento. Escribe 'soporte' para contactar al equipo."
    else:
        respuesta = "El asistente de IA no está configurado aún. Por favor contacta al soporte."

    # Notificar por Telegram si necesita soporte humano
    soporte_notificado = False
    if necesita_soporte and usuario.telegram_chat_id:
        from services.telegram import enviar_mensaje, TELEGRAM_TOKEN
        import os
        # Notificar al admin
        admin_chat = os.environ.get("ADMIN_TELEGRAM_CHAT_ID", "")
        if admin_chat:
            from services.telegram import enviar_mensaje
            await enviar_mensaje(admin_chat,
                f"🆘 <b>Soporte requerido</b>\n"
                f"Usuario: <b>{usuario.nombre}</b> ({usuario.email})\n"
                f"Mensaje: {messages[-1]['content'] if messages else 'N/A'}"
            )
            soporte_notificado = True

    return JSONResponse({"respuesta": respuesta, "soporte_notificado": soporte_notificado})


# ── Reporte PDF ──────────────────────────────────────────────────────────────────

@app.get("/portafolio/pdf")
async def descargar_pdf(request: Request, db: Session = Depends(get_db)):
    from fastapi.responses import StreamingResponse
    import io
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)

    datos_bolsa = await obtener_datos_bvc()
    tasa_auto   = await obtener_tasa_bcv()
    config_tasa = tasa_auto if tasa_auto > 0 else 0

    from database import ActivoPortafolio as AP
    activos_db = db.query(AP).filter(AP.usuario_id == usuario.id).all()
    portafolio = {
        a.simbolo: {"cantidad": a.cantidad, "precio_promedio": a.precio_promedio,
                    "comision": a.comision, "registro": a.registro, "iva": a.iva}
        for a in activos_db
    }
    mapa_precios = {i["COD_SIMB"]: _to_float(i.get("PRECIO") or 0) for i in datos_bolsa}
    total_mkt = sum(
        _to_float(d["cantidad"]) * mapa_precios.get(s, _to_float(d["precio_promedio"]))
        for s, d in portafolio.items()
    )
    from services.portafolio import resumen_portafolio
    filas   = [calcular_fila(s, d, mapa_precios.get(s, _to_float(d["precio_promedio"])), total_mkt, config_tasa)
               for s, d in portafolio.items()]
    resumen = resumen_portafolio(portafolio, datos_bolsa, config_tasa)

    pdf_bytes = generar_reporte_pdf(usuario, filas, resumen, config_tasa)
    from datetime import datetime
    nombre = f"CaracasBull_Reporte_{datetime.now().strftime('%Y%m')}.pdf"

    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={nombre}"}
    )


# ── Watchlist ────────────────────────────────────────────────────────────────────

@app.get("/watchlist", response_class=HTMLResponse)
async def ver_watchlist(request: Request, db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    simbolos_wl = [w.simbolo for w in usuario.watchlist]
    datos_bolsa = await obtener_datos_bvc()
    items = [i for i in datos_bolsa if i.get("COD_SIMB") in simbolos_wl]
    return render("watchlist.html", {
        "request": request, "usuario": usuario,
        "items": items, "dias": dias_restantes(usuario),
        "mercado": mercado_abierto(), "active": "",
    })

@app.post("/watchlist/agregar")
async def agregar_watchlist(request: Request, simbolo: str = Form(...), db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return JSONResponse({"ok": False}, status_code=401)
    existe = db.query(Watchlist).filter(
        Watchlist.usuario_id == usuario.id,
        Watchlist.simbolo == simbolo.upper()
    ).first()
    if not existe:
        db.add(Watchlist(usuario_id=usuario.id, simbolo=simbolo.upper()))
        db.commit()
    return JSONResponse({"ok": True})

@app.post("/watchlist/eliminar")
async def eliminar_watchlist(request: Request, simbolo: str = Form(...), db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    item = db.query(Watchlist).filter(
        Watchlist.usuario_id == usuario.id,
        Watchlist.simbolo == simbolo.upper()
    ).first()
    if item:
        db.delete(item)
        db.commit()
    ref = request.headers.get("referer", "/watchlist")
    return RedirectResponse(url=ref, status_code=303)


# ── Importar portafolio ───────────────────────────────────────────────────────

@app.get("/portafolio/importar", response_class=HTMLResponse)
async def importar_page(request: Request, db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    return render("importar.html", {
        "request": request, "usuario": usuario,
        "dias": dias_restantes(usuario), "mercado": mercado_abierto(),
        "active": "", "error": None, "activos_preview": None, "activos_json": None,
    })

@app.post("/portafolio/importar", response_class=HTMLResponse)
async def importar_post(request: Request, db: Session = Depends(get_db)):
    import json as json_mod
    from fastapi import UploadFile, File
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    form = await request.form()
    archivo = form.get("archivo")
    if not archivo or not archivo.filename:
        return render("importar.html", {
            "request": request, "usuario": usuario,
            "dias": dias_restantes(usuario), "mercado": mercado_abierto(),
            "active": "", "error": "Selecciona un archivo", "activos_preview": None, "activos_json": None,
        })
    try:
        contenido = await archivo.read()
        activos = importar_archivo(contenido, archivo.filename)
        if not activos:
            raise ValueError("No se encontraron activos en el archivo")
        return render("importar.html", {
            "request": request, "usuario": usuario,
            "dias": dias_restantes(usuario), "mercado": mercado_abierto(),
            "active": "", "error": None,
            "activos_preview": activos,
            "activos_json": json_mod.dumps(activos),
        })
    except Exception as e:
        return render("importar.html", {
            "request": request, "usuario": usuario,
            "dias": dias_restantes(usuario), "mercado": mercado_abierto(),
            "active": "", "error": str(e), "activos_preview": None, "activos_json": None,
        })

@app.post("/portafolio/importar/confirmar")
async def importar_confirmar(request: Request, datos: str = Form(...), db: Session = Depends(get_db)):
    import json as json_mod
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    activos = json_mod.loads(datos)
    for a in activos:
        existente = db.query(ActivoPortafolio).filter(
            ActivoPortafolio.usuario_id == usuario.id,
            ActivoPortafolio.simbolo == a["simbolo"]
        ).first()
        if existente:
            existente.cantidad = a["cantidad"]
            existente.precio_promedio = a["precio_promedio"]
        else:
            db.add(ActivoPortafolio(
                usuario_id=usuario.id,
                simbolo=a["simbolo"],
                cantidad=a["cantidad"],
                precio_promedio=a["precio_promedio"],
                comision=a.get("comision", 0),
                registro=a.get("registro", 0),
                iva=a.get("iva", 16),
            ))
    db.commit()
    return RedirectResponse(url="/portafolio", status_code=303)


# ── Admin ─────────────────────────────────────────────────────────────────────

@app.get("/admin", response_class=HTMLResponse)
async def admin_panel(request: Request, db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    if not usuario or not usuario.es_admin:
        return RedirectResponse(url="/", status_code=302)
    from database import Usuario as UsuarioModel, Suscripcion
    usuarios = db.query(UsuarioModel).order_by(UsuarioModel.creado_en.desc()).all()
    total = len(usuarios)
    activas   = sum(1 for u in usuarios if u.suscripcion and u.suscripcion.activa)
    plan_pro  = sum(1 for u in usuarios if u.suscripcion and u.suscripcion.plan == "pro")
    plan_bas  = sum(1 for u in usuarios if u.suscripcion and u.suscripcion.plan == "basico")
    trial     = sum(1 for u in usuarios if u.suscripcion and u.suscripcion.plan == "trial")
    con_tg    = sum(1 for u in usuarios if u.telegram_chat_id)
    return render("admin.html", {
        "request": request, "usuario": usuario,
        "usuarios": usuarios,
        "dias": dias_restantes(usuario), "mercado": mercado_abierto(), "active": "",
        "stats": {
            "total_usuarios": total, "activas": activas,
            "plan_pro": plan_pro, "plan_basico": plan_bas,
            "trial": trial, "con_telegram": con_tg,
        }
    })

@app.post("/admin/activar")
async def admin_activar(
    request: Request,
    usuario_id: int = Form(...),
    plan: str = Form("pro"),
    db: Session = Depends(get_db),
):
    admin = get_usuario_actual(request, db)
    if not admin or not admin.es_admin:
        return RedirectResponse(url="/", status_code=302)
    from database import Suscripcion
    from datetime import datetime, timedelta
    sus = db.query(Suscripcion).filter(Suscripcion.usuario_id == usuario_id).first()
    if sus:
        sus.plan = plan
        sus.activa = True
        sus.fecha_vence = datetime.utcnow() + timedelta(days=30)
    db.commit()
    return RedirectResponse(url="/admin", status_code=303)

@app.post("/admin/desactivar")
async def admin_desactivar(request: Request, usuario_id: int = Form(...), db: Session = Depends(get_db)):
    admin = get_usuario_actual(request, db)
    if not admin or not admin.es_admin:
        return RedirectResponse(url="/", status_code=302)
    from database import Suscripcion
    sus = db.query(Suscripcion).filter(Suscripcion.usuario_id == usuario_id).first()
    if sus:
        sus.activa = False
        db.commit()
    return RedirectResponse(url="/admin", status_code=303)


# ── PWA ───────────────────────────────────────────────────────────────────────

@app.get("/favicon.ico")
async def favicon_ico():
    from fastapi.responses import FileResponse
    return FileResponse("static/favicon.svg", media_type="image/svg+xml")

@app.get("/favicon.svg")
async def favicon_svg():
    from fastapi.responses import FileResponse
    return FileResponse("static/favicon.svg", media_type="image/svg+xml")


@app.get("/manifest.json")
async def manifest():
    from fastapi.responses import FileResponse
    return FileResponse("static/manifest.json", media_type="application/manifest+json")

@app.get("/sw.js")
async def service_worker():
    from fastapi.responses import FileResponse
    return FileResponse("static/sw.js", media_type="application/javascript")


# ── Chat Asistente ───────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """Eres el asistente virtual de Caracas Bull, una plataforma de INFORMACION y ANALISIS del mercado bursatil de Caracas (BVC).

IMPORTANTE:
- NO somos broker, NO realizamos operaciones bursatiles
- NO damos asesoria de inversion ni recomendaciones para comprar/vender
- Solo proporcionamos informacion y herramientas de analisis

Puedes ayudar con:
- Como usar las funciones de la app (pizarra, portafolio, alertas, watchlist, comparador, ISLR, historial)
- Informacion general sobre la BVC y como funciona
- Problemas tecnicos con la plataforma
- Dudas sobre pagos y suscripciones (planes: Basico 1.5 USDT/mes, Pro 2.99 USDT/mes lanzamiento)
- Como vincular Telegram para alertas
- Como importar portafolio desde Excel/CSV

Si el usuario tiene un problema urgente de pago o tecnico grave, dile que escribe "soporte" para notificar al equipo.

Responde siempre en español, de forma amigable y concisa. Maximo 3 parrafos."""


@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request, db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    return render("chat.html", {
        "request": request, "usuario": usuario,
        "dias": dias_restantes(usuario), "mercado": mercado_abierto(), "active": "",
    })


@app.post("/chat")
async def chat_api(request: Request, db: Session = Depends(get_db)):
    import os
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return JSONResponse({"error": "no autorizado"}, status_code=401)

    body = await request.json()
    messages = body.get("messages", [])
    necesita_soporte = body.get("necesita_soporte", False)

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    respuesta = ""

    if api_key:
        try:
            async with httpx_client.AsyncClient(timeout=30.0) as client:
                r = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": "claude-haiku-4-5-20251001",
                        "max_tokens": 500,
                        "system": SYSTEM_PROMPT,
                        "messages": messages[-10:],  # últimos 10 mensajes
                    }
                )
                if r.status_code == 200:
                    respuesta = r.json()["content"][0]["text"]
                else:
                    respuesta = "Lo siento, tuve un problema técnico. Intenta de nuevo en un momento."
        except Exception as e:
            print(f"[Chat] Error: {e}")
            respuesta = "Lo siento, no puedo responder en este momento. Escribe 'soporte' para contactar al equipo."
    else:
        respuesta = "El asistente de IA no está configurado aún. Por favor contacta al soporte."

    # Notificar por Telegram si necesita soporte humano
    soporte_notificado = False
    if necesita_soporte and usuario.telegram_chat_id:
        from services.telegram import enviar_mensaje, TELEGRAM_TOKEN
        import os
        # Notificar al admin
        admin_chat = os.environ.get("ADMIN_TELEGRAM_CHAT_ID", "")
        if admin_chat:
            from services.telegram import enviar_mensaje
            await enviar_mensaje(admin_chat,
                f"🆘 <b>Soporte requerido</b>\n"
                f"Usuario: <b>{usuario.nombre}</b> ({usuario.email})\n"
                f"Mensaje: {messages[-1]['content'] if messages else 'N/A'}"
            )
            soporte_notificado = True

    return JSONResponse({"respuesta": respuesta, "soporte_notificado": soporte_notificado})


# ── Reporte PDF ──────────────────────────────────────────────────────────────────

@app.get("/reporte/pdf")
async def descargar_reporte(request: Request, db: Session = Depends(get_db)):
    from fastapi.responses import Response
    from datetime import datetime
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)

    datos_bolsa = await obtener_datos_bvc()
    tasa_auto   = await obtener_tasa_bcv()
    config_tasa = tasa_auto if tasa_auto > 0 else 0

    from database import ActivoPortafolio as AP
    activos_db = db.query(AP).filter(AP.usuario_id == usuario.id).all()
    portafolio = {
        a.simbolo: {"cantidad": a.cantidad, "precio_promedio": a.precio_promedio,
                    "comision": a.comision, "registro": a.registro, "iva": a.iva}
        for a in activos_db
    }

    mapa_precios = {i["COD_SIMB"]: _to_float(i.get("PRECIO")) for i in datos_bolsa}
    total_mkt = sum(
        _to_float(d["cantidad"]) * mapa_precios.get(s, _to_float(d["precio_promedio"]))
        for s, d in portafolio.items()
    )

    from services.portafolio import calcular_fila, resumen_portafolio
    filas   = [calcular_fila(s, d, mapa_precios.get(s, _to_float(d["precio_promedio"])), total_mkt, config_tasa)
               for s, d in portafolio.items()]
    resumen = resumen_portafolio(portafolio, datos_bolsa, config_tasa)

    plan = usuario.suscripcion.plan if usuario.suscripcion else "trial"
    mes  = datetime.now().strftime("%B %Y")

    pdf_bytes = generar_reporte(
        usuario_nombre=usuario.nombre,
        usuario_email=usuario.email,
        plan=plan,
        filas=filas,
        resumen=resumen,
        tasa=config_tasa,
        mes=mes,
    )

    filename = f"reporte_caracasbull_{datetime.now().strftime('%Y%m')}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


# ── Historial de transacciones ───────────────────────────────────────────────────

@app.get("/historial", response_class=HTMLResponse)
async def ver_historial(request: Request, db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    from datetime import datetime
    txs = db.query(TransaccionHistorial).filter(
        TransaccionHistorial.usuario_id == usuario.id
    ).order_by(TransaccionHistorial.fecha.desc()).all()
    datos_bolsa = await obtener_datos_bvc()
    simbolos = sorted([i["COD_SIMB"] for i in datos_bolsa])
    compras = sum(1 for t in txs if t.tipo == "compra")
    ventas  = sum(1 for t in txs if t.tipo == "venta")
    # Ganancia realizada = suma de ventas - suma de compras del mismo simbolo
    ganancia_total = sum(
        t.cantidad * t.precio if t.tipo == "venta" else -(t.cantidad * t.precio)
        for t in txs
    )
    return render("historial.html", {
        "request": request, "usuario": usuario,
        "transacciones": txs, "simbolos": simbolos,
        "compras": compras, "ventas": ventas,
        "ganancia_total": ganancia_total,
        "hoy": datetime.now().strftime("%Y-%m-%d"),
        "dias": dias_restantes(usuario), "mercado": mercado_abierto(), "active": "",
    })

@app.post("/historial/agregar")
async def agregar_historial(
    request: Request,
    simbolo: str = Form(...), tipo: str = Form(...),
    fecha: str = Form(...), cantidad: float = Form(...),
    precio: float = Form(...), comision: float = Form(0),
    notas: str = Form(""),
    db: Session = Depends(get_db),
):
    from datetime import datetime
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    fecha_dt = datetime.strptime(fecha, "%Y-%m-%d")
    db.add(TransaccionHistorial(
        usuario_id=usuario.id, simbolo=simbolo.upper(), tipo=tipo,
        cantidad=cantidad, precio=precio, comision=comision,
        notas=notas, fecha=fecha_dt,
    ))
    db.commit()
    return RedirectResponse(url="/historial", status_code=303)

@app.post("/historial/eliminar")
async def eliminar_historial(request: Request, tx_id: int = Form(...), db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    tx = db.query(TransaccionHistorial).filter(
        TransaccionHistorial.id == tx_id,
        TransaccionHistorial.usuario_id == usuario.id
    ).first()
    if tx:
        db.delete(tx)
        db.commit()
    return RedirectResponse(url="/historial", status_code=303)


# ── Comparador de acciones ────────────────────────────────────────────────────

@app.get("/comparador", response_class=HTMLResponse)
async def comparador(request: Request, s1: str = "", s2: str = "", s3: str = "", db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    datos_bolsa = await obtener_datos_bvc()
    simbolos = sorted([i["COD_SIMB"] for i in datos_bolsa])
    mapa = {i["COD_SIMB"]: i for i in datos_bolsa}
    datos_comparacion = []
    for s in [s1, s2, s3]:
        if s and s in mapa:
            item = mapa[s]
            datos_comparacion.append({
                "simbolo":     s,
                "precio":      _to_float(item.get("PRECIO")),
                "var_rel":     _to_float(item.get("VAR_REL")),
                "vol_transado":_to_float(item.get("MONTO_EFECTIVO")),
                "titulos":     item.get("VOLUMEN", "—"),
                "p_compra":    _to_float(item.get("PRE_CMP_1")),
                "p_venta":     _to_float(item.get("PRE_VTA_1")),
            })
    return render("comparador.html", {
        "request": request, "usuario": usuario, "simbolos": simbolos,
        "seleccionados": [s1, s2, s3],
        "datos_comparacion": datos_comparacion if datos_comparacion else None,
        "dias": dias_restantes(usuario), "mercado": mercado_abierto(), "active": "",
    })


# ── Calculadora ISLR ──────────────────────────────────────────────────────────

@app.get("/islr", response_class=HTMLResponse)
async def islr_page(request: Request, db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    # Calcular ganancia del portafolio actual para precargar
    datos_bolsa = await obtener_datos_bvc()
    from database import ActivoPortafolio as AP
    activos = db.query(AP).filter(AP.usuario_id == usuario.id).all()
    mapa = {i["COD_SIMB"]: _to_float(i.get("PRECIO")) for i in datos_bolsa}
    ganancia = sum(
        (mapa.get(a.simbolo, a.precio_promedio) - a.precio_promedio) * a.cantidad
        for a in activos
    )
    return render("islr.html", {
        "request": request, "usuario": usuario,
        "ganancia_portafolio": max(0, ganancia),
        "ut_actual": 9600,  # UT 2024 referencial
        "dias": dias_restantes(usuario), "mercado": mercado_abierto(), "active": "",
    })


# ── Índice vs Mercado ─────────────────────────────────────────────────────────

@app.get("/indice", response_class=HTMLResponse)
async def indice_mercado(request: Request, db: Session = Depends(get_db)):
    usuario = get_usuario_actual(request, db)
    if not usuario:
        return RedirectResponse(url="/login", status_code=302)
    datos_bolsa = await obtener_datos_bvc()
    tasa_auto = await obtener_tasa_bcv()
    config_tasa = tasa_auto if tasa_auto > 0 else 0
    from database import ActivoPortafolio as AP
    activos_db = db.query(AP).filter(AP.usuario_id == usuario.id).all()
    portafolio = {a.simbolo: {"cantidad": a.cantidad, "precio_promedio": a.precio_promedio,
                               "comision": a.comision, "registro": a.registro, "iva": a.iva}
                  for a in activos_db}
    mapa_precios = {i["COD_SIMB"]: _to_float(i.get("PRECIO")) for i in datos_bolsa}
    vars_hoy     = {i["COD_SIMB"]: _to_float(i.get("VAR_REL")) for i in datos_bolsa}
    total_mkt = sum(
        _to_float(d["cantidad"]) * mapa_precios.get(s, _to_float(d["precio_promedio"]))
        for s, d in portafolio.items()
    )
    filas = [
        calcular_fila(s, d, mapa_precios.get(s, _to_float(d["precio_promedio"])), total_mkt, config_tasa)
        for s, d in portafolio.items()
    ]
    # Rendimiento ponderado del portafolio
    rend_port = sum(f["rend_pct"] * f["peso_pct"] / 100 for f in filas) if filas else 0
    # Promedio del mercado (variación promedio de todas las acciones)
    todas_vars = [_to_float(i.get("VAR_REL")) for i in datos_bolsa]
    rend_mercado = sum(todas_vars) / len(todas_vars) if todas_vars else 0

    return render("indice.html", {
        "request": request, "usuario": usuario, "filas": filas,
        "rend_port": rend_port, "rend_mercado": rend_mercado,
        "vars_hoy": vars_hoy,
        "vars_hoy_list": [vars_hoy.get(f["simb"], 0) for f in filas],
        "dias": dias_restantes(usuario), "mercado": mercado_abierto(), "active": "",
    })


# ── Setup Telegram webhook ───────────────────────────────────────────────────────

async def registrar_webhook_telegram():
    """Registra el webhook de Telegram al arrancar la app."""
    import os
    app_url = os.environ.get("APP_URL", "")
    if not app_url:
        return
    webhook_url = f"{app_url}/webhook/telegram"
    from services.telegram import TELEGRAM_API
    async with httpx.AsyncClient() as client:
        try:
            r = await client.post(f"{TELEGRAM_API}/setWebhook", json={"url": webhook_url})
            if r.status_code == 200:
                print(f"[Telegram] Webhook registrado: {webhook_url}")
        except Exception as e:
            print(f"[Telegram] Error registrando webhook: {e}")


# ── Inicio ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
