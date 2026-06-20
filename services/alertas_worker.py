"""
Worker de alertas — corre en background cada 5 minutos durante el horario de mercado.
Compara precios actuales con las alertas configuradas y dispara notificaciones.
"""
import asyncio
from services.bvc import obtener_datos_bvc, _to_float, mercado_abierto
from services.telegram import enviar_alerta_precio
from database import SessionLocal, AlertaPrecio, Usuario


async def revisar_alertas():
    """Revisa todas las alertas activas y dispara las que correspondan."""
    if not mercado_abierto():
        return

    datos = await obtener_datos_bvc()
    mapa  = {item["COD_SIMB"]: _to_float(item.get("VAR_REL")) for item in datos}
    precios = {item["COD_SIMB"]: _to_float(item.get("PRECIO")) for item in datos}

    db = SessionLocal()
    try:
        alertas = db.query(AlertaPrecio).filter(
            AlertaPrecio.activa == True,
            AlertaPrecio.disparada == False,
        ).all()

        for alerta in alertas:
            var_actual = mapa.get(alerta.simbolo)
            precio_actual = precios.get(alerta.simbolo)
            if var_actual is None or precio_actual is None:
                continue

            disparar = False
            if alerta.tipo == "subida"  and var_actual >= alerta.porcentaje:
                disparar = True
            elif alerta.tipo == "bajada" and var_actual <= -alerta.porcentaje:
                disparar = True

            if disparar:
                usuario = db.query(Usuario).filter(Usuario.id == alerta.usuario_id).first()
                if usuario and usuario.telegram_chat_id:
                    await enviar_alerta_precio(
                        usuario.telegram_chat_id,
                        alerta.simbolo,
                        precio_actual,
                        var_actual,
                        alerta.tipo,
                    )
                    alerta.disparada = True
                    print(f"[Alertas] Disparada: {usuario.email} → {alerta.simbolo} {var_actual:.2f}%")

        db.commit()
    except Exception as e:
        print(f"[Alertas] Error: {e}")
    finally:
        db.close()


async def loop_alertas():
    """Loop infinito que revisa alertas cada 5 minutos."""
    print("[Alertas] Worker iniciado")
    while True:
        try:
            await revisar_alertas()
        except Exception as e:
            print(f"[Alertas] Error en loop: {e}")
        await asyncio.sleep(300)  # 5 minutos
