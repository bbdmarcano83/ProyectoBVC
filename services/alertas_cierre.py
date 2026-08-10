"""
Servicio de alertas Telegram al cierre del mercado BVC.
Se ejecuta a las 1:15 PM VET (17:15 UTC) vía cron o endpoint.

Según el plan del usuario:
  - Básico: resumen general (IBC, acciones top/bottom)
  - Intermedio: + scoring completo
  - Pro: + fear detector + señales de venta + dividendos
"""

from database import SessionLocal, Usuario, Suscripcion, ActivoPortafolio
from services.telegram import enviar_mensaje
from services.scoring import calcular_scoring_completo
from services.auth import suscripcion_activa, get_plan


async def generar_alerta_basico(resultados: list, deval: float) -> str:
    """Resumen general para plan Básico."""
    top3 = resultados[:3]
    bottom3 = resultados[-3:]
    
    msg = "<b>📊 Cierre BVC — Caracas Bull</b>\n\n"
    msg += f"Devaluación BCV: {deval}%\n"
    msg += f"Títulos analizados: {len(resultados)}\n\n"
    msg += "<b>Top 3 Score:</b>\n"
    for r in top3:
        msg += f"  {r['simbolo']} — {r['total']} pts\n"
    msg += "\n<b>Bottom 3:</b>\n"
    for r in bottom3:
        msg += f"  {r['simbolo']} — {r['total']} pts\n"
    return msg


async def generar_alerta_intermedio(resultados: list, deval: float) -> str:
    """Scoring completo para plan Intermedio."""
    msg = await generar_alerta_basico(resultados, deval)
    
    alto = [r for r in resultados if r['total'] >= 75]
    medio = [r for r in resultados if 50 <= r['total'] < 75]
    bajo = [r for r in resultados if 30 <= r['total'] < 50]
    
    msg += f"\n<b>📈 Score alto ({len(alto)}):</b>\n"
    for r in alto:
        msg += f"  {r['simbolo']} — {r['total']} pts (Rend:{r['rend_score']|int} Liq:{r['liq_score']} Din:{r['din_score']} Tend:{r['tend_score']})\n"
    
    msg += f"\n<b>📊 Score medio ({len(medio)}):</b>\n"
    for r in medio[:5]:
        msg += f"  {r['simbolo']} — {r['total']} pts\n"
    if len(medio) > 5:
        msg += f"  ... y {len(medio)-5} más\n"
    
    return msg


async def generar_alerta_pro(resultados: list, deval: float, usuario=None, db=None) -> str:
    """Alertas completas para plan Pro."""
    msg = await generar_alerta_intermedio(resultados, deval)
    
    # Señales de compra (Fear Detector)
    compras = [r for r in resultados if r.get('señal_compra')]
    if compras:
        msg += "\n<b>🔴 SEÑALES DE COMPRA:</b>\n"
        for r in compras:
            msg += f"  {r['simbolo']} — caída {r['caida_pct']}% (Score {r['total']})\n"
    
    # Señales de venta del portafolio
    if usuario and db:
        activos = db.query(ActivoPortafolio).filter(ActivoPortafolio.usuario_id == usuario.id).all()
        portafolio_map = {a.simbolo: a for a in activos}
        
        ventas = []
        for r in resultados:
            simb = r.get('simbolo')
            if simb not in portafolio_map:
                continue
            activo = portafolio_map[simb]
            precio_actual = r.get('precio', 0)
            precio_compra = activo.precio_promedio or 0
            if precio_compra <= 0:
                continue
            ganancia = round(((precio_actual / precio_compra) - 1) * 100, 1)
            if ganancia >= 50:
                ventas.append(f"  {simb} — +{ganancia}% (tomar ganancia)")
            elif r.get('din_score', 0) == 0:
                ventas.append(f"  {simb} — congelado (vender)")
            elif r.get('total', 0) < 30:
                ventas.append(f"  {simb} — Score {r['total']} (vender)")
        
        if ventas:
            msg += "\n<b>⚠️ SEÑALES DE VENTA:</b>\n"
            msg += "\n".join(ventas) + "\n"
    
    return msg


async def enviar_alertas_cierre():
    """
    Envía alertas a todos los usuarios con Telegram vinculado.
    Llamar desde un cron job a las 1:15 PM VET.
    """
    db = SessionLocal()
    try:
        resultados, deval, metadata = await calcular_scoring_completo()
        
        usuarios = db.query(Usuario).filter(
            Usuario.telegram_chat_id.isnot(None),
            Usuario.telegram_chat_id != "",
        ).all()
        
        enviados = 0
        errores = 0
        
        for usuario in usuarios:
            if not suscripcion_activa(usuario):
                continue
            
            plan = get_plan(usuario)
            chat_id = usuario.telegram_chat_id
            
            try:
                if plan == "pro":
                    msg = await generar_alerta_pro(resultados, deval, usuario, db)
                elif plan == "intermedio":
                    msg = await generar_alerta_intermedio(resultados, deval)
                else:
                    msg = await generar_alerta_basico(resultados, deval)
                
                ok = await enviar_mensaje(chat_id, msg)
                if ok:
                    enviados += 1
                else:
                    errores += 1
            except Exception as e:
                print(f"[Alertas] Error enviando a {usuario.email}: {e}")
                errores += 1
        
        print(f"[Alertas] Cierre BVC: {enviados} enviados, {errores} errores")
        return {"enviados": enviados, "errores": errores}
    
    finally:
        db.close()
