"""Alertas Telegram al cierre — V3/V4.

Consume el scoring runtime activo. No persiste snapshots; todas las alertas se
construyen con la corrida actual y las posiciones disponibles en la instancia.
"""
from database import SessionLocal, Usuario, ActivoPortafolio
from services.telegram import enviar_mensaje
from services.scoring import calcular_scoring_completo
from services.auth import suscripcion_activa, get_plan


def _score(r: dict) -> float:
    try:
        return float(r.get("score_v3", r.get("total", 0)) or 0)
    except (TypeError, ValueError):
        return 0.0


async def generar_alerta_basico(resultados: list, deval: float, metadata: dict | None = None) -> str:
    top3 = resultados[:3]
    bottom3 = resultados[-3:]
    market = (metadata or {}).get("market", {})
    msg = "<b>📊 Cierre BVC — Caracas Bull</b>\n\n"
    msg += f"Devaluación BCV: {deval}%\n"
    if market:
        msg += f"Régimen: <b>{market.get('regime', 'N/A')}</b> | Breadth: {market.get('breadth_score', 0)}\n"
    msg += f"Títulos analizados: {len(resultados)}\n\n"
    msg += "<b>Top 3:</b>\n"
    for r in top3:
        msg += f"  {r.get('simbolo')} — {_score(r):.1f} pts\n"
    msg += "\n<b>Bottom 3:</b>\n"
    for r in bottom3:
        msg += f"  {r.get('simbolo')} — {_score(r):.1f} pts\n"
    return msg


async def generar_alerta_intermedio(resultados: list, deval: float, metadata: dict | None = None) -> str:
    msg = await generar_alerta_basico(resultados, deval, metadata)
    alto = [r for r in resultados if _score(r) >= 75]
    msg += f"\n<b>📈 Score alto ({len(alto)}):</b>\n"
    for r in alto[:10]:
        msg += (
            f"  {r.get('simbolo')} — {_score(r):.1f} | "
            f"Conf {r.get('confidence_score_v3', '—')} | "
            f"Risk {r.get('risk_score_v3', '—')}\n"
        )
    preparar = [r for r in resultados if r.get("signal_stage_v3") == "PREPARAR COMPRA"]
    if preparar:
        msg += "\n<b>🟡 Preparar compra:</b>\n"
        for r in preparar[:5]:
            msg += f"  {r.get('simbolo')} — Opportunity {r.get('opportunity_score_v3')}\n"
    return msg


async def generar_alerta_pro(resultados: list, deval: float, metadata: dict | None = None, usuario=None, db=None) -> str:
    msg = await generar_alerta_intermedio(resultados, deval, metadata)
    compras = [r for r in resultados if r.get("señal_compra_v3") or r.get("señal_compra")]
    if compras:
        msg += "\n<b>🟢 OPORTUNIDADES CONFIRMADAS:</b>\n"
        for r in compras:
            msg += (
                f"  {r.get('simbolo')} — caída {r.get('caida_pct')}% | "
                f"Score {_score(r):.1f} | Conf {r.get('confidence_score_v3', '—')}\n"
            )

    if usuario and db:
        activos = db.query(ActivoPortafolio).filter(ActivoPortafolio.usuario_id == usuario.id).all()
        portafolio_map = {a.simbolo: a for a in activos}
        ventas = []
        for r in resultados:
            simb = r.get("simbolo")
            if simb not in portafolio_map:
                continue
            activo = portafolio_map[simb]
            precio_actual = float(r.get("precio", 0) or 0)
            precio_compra = float(activo.precio_promedio or 0)
            if precio_compra <= 0:
                continue
            ganancia = round(((precio_actual / precio_compra) - 1) * 100, 1)
            risk = float(r.get("risk_score_v3", 0) or 0)
            conf = float(r.get("confidence_score_v3", 0) or 0)
            motivos = []
            if ganancia >= 50:
                motivos.append(f"+{ganancia}% toma de ganancia")
            if r.get("din_label") in {"CONGELADO", "MUERTO"}:
                motivos.append("liquidez deteriorada")
            if _score(r) < 30:
                motivos.append(f"score {_score(r):.1f}")
            if risk >= 75:
                motivos.append(f"risk {risk:.0f}")
            if conf < 40:
                motivos.append(f"confidence {conf:.0f}")
            if motivos:
                ventas.append(f"  {simb} — " + "; ".join(motivos))
        if ventas:
            msg += "\n<b>⚠️ REVISAR CARTERA:</b>\n" + "\n".join(ventas) + "\n"
    return msg


async def enviar_alertas_cierre():
    db = SessionLocal()
    try:
        resultados, deval, metadata = await calcular_scoring_completo()
        usuarios = db.query(Usuario).filter(
            Usuario.telegram_chat_id.isnot(None),
            Usuario.telegram_chat_id != "",
            Usuario.activo.is_(True),
        ).all()
        enviados = 0
        errores = 0
        for usuario in usuarios:
            if not suscripcion_activa(usuario):
                continue
            plan = get_plan(usuario)
            try:
                if plan == "pro":
                    msg = await generar_alerta_pro(resultados, deval, metadata, usuario, db)
                elif plan == "intermedio":
                    msg = await generar_alerta_intermedio(resultados, deval, metadata)
                else:
                    msg = await generar_alerta_basico(resultados, deval, metadata)
                if await enviar_mensaje(usuario.telegram_chat_id, msg):
                    enviados += 1
                else:
                    errores += 1
            except Exception as exc:
                print(f"[Alertas] Error: {type(exc).__name__}")
                errores += 1
        return {"enviados": enviados, "errores": errores, "engine": metadata.get("engine_version")}
    finally:
        db.close()
