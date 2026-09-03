"""Alertas Telegram al cierre — V3/V4/V5.

Además de alertas, registra un snapshot diario idempotente de cada cartera activa
para construir una comparación histórica real contra IBC y USD sin sesgo de
composición actual.
"""
from datetime import date

from database import SessionLocal, Usuario, ActivoPortafolio
from services.telegram import enviar_mensaje
from services.scoring import calcular_scoring_completo
from services.auth import suscripcion_activa, get_plan
from services.bvc import obtener_tasa_bcv
from services.portfolio_snapshot_v5 import save_daily_snapshot
from services.ibc_history_v5 import load_ibc_history
from services.portfolio_benchmark_v5 import normalize_ibc_points, ibc_asof


def _score(r: dict) -> float:
    """Return the active public score, preferring Caracas Bull V5 when present."""
    for key in ("philosophy_score_v5", "total", "score_v3"):
        value = r.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return 0.0


def _stage(r: dict) -> str:
    """Return the active signal stage without falling back to V3 when V5 exists."""
    if "signal_stage_v5" in r:
        return str(r.get("signal_stage_v5") or "")
    return str(r.get("signal_stage_v3") or "")


def _has_v5(resultados: list[dict], metadata: dict | None = None) -> bool:
    if isinstance((metadata or {}).get("v5"), dict):
        return True
    return any("philosophy_score_v5" in r or "signal_stage_v5" in r for r in resultados)


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

    if _has_v5(resultados, metadata):
        preparar = [r for r in resultados if _stage(r) in {"PREPARAR ENTRADA", "CANDIDATA FUNDAMENTAL"}]
        if preparar:
            msg += "\n<b>🟡 Preparar / candidatas V5:</b>\n"
            for r in preparar[:5]:
                msg += f"  {r.get('simbolo')} — {_stage(r)} | Score {_score(r):.1f}\n"
    else:
        preparar = [r for r in resultados if r.get("signal_stage_v3") == "PREPARAR COMPRA"]
        if preparar:
            msg += "\n<b>🟡 Preparar compra:</b>\n"
            for r in preparar[:5]:
                msg += f"  {r.get('simbolo')} — Opportunity {r.get('opportunity_score_v3')}\n"
    return msg


async def generar_alerta_pro(resultados: list, deval: float, metadata: dict | None = None, usuario=None, db=None) -> str:
    msg = await generar_alerta_intermedio(resultados, deval, metadata)

    if _has_v5(resultados, metadata):
        compras = [r for r in resultados if _stage(r) == "OPORTUNIDAD HÍBRIDA CONFIRMADA"]
        mercado_sin_fundamental = [
            r for r in resultados if _stage(r) == "OPORTUNIDAD DE MERCADO · SIN FUNDAMENTAL"
        ]
    else:
        compras = [r for r in resultados if r.get("señal_compra_v3") or r.get("señal_compra")]
        mercado_sin_fundamental = []

    if compras:
        msg += "\n<b>🟢 OPORTUNIDADES CONFIRMADAS:</b>\n"
        for r in compras:
            msg += (
                f"  {r.get('simbolo')} — caída {r.get('caida_pct')}% | "
                f"Score {_score(r):.1f} | Conf {r.get('confidence_score_v3', '—')}\n"
            )

    if mercado_sin_fundamental:
        msg += "\n<b>🟠 OPORTUNIDADES DE MERCADO · SIN FUNDAMENTAL:</b>\n"
        for r in mercado_sin_fundamental:
            msg += (
                f"  {r.get('simbolo')} — Score {_score(r):.1f} | "
                f"Conf {r.get('confidence_score_v3', '—')} | no confirmada por fundamental\n"
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


def _current_ibc_level() -> float | None:
    points_raw, _ = load_ibc_history()
    points = normalize_ibc_points(points_raw)
    return ibc_asof(points, date.today()) if points else None


async def enviar_alertas_cierre():
    db = SessionLocal()
    try:
        resultados, deval, metadata = await calcular_scoring_completo()
        prices = {
            str(r.get("simbolo") or "").upper(): float(r.get("precio") or 0)
            for r in resultados if r.get("simbolo")
        }
        tasa_bcv = await obtener_tasa_bcv()
        ibc_level = _current_ibc_level()

        # El snapshot no depende de Telegram: se conserva historia de toda cartera
        # activa con suscripción. Errores de snapshot no bloquean las alertas.
        usuarios_activos = db.query(Usuario).filter(Usuario.activo.is_(True)).all()
        snapshots = 0
        snapshot_errors = 0
        for usuario in usuarios_activos:
            if not suscripcion_activa(usuario):
                continue
            try:
                state = save_daily_snapshot(
                    usuario.id,
                    prices=prices,
                    fx_bcv=tasa_bcv,
                    ibc_level=ibc_level,
                    source="market_close",
                )
                if state.get("saved"):
                    snapshots += 1
            except Exception as exc:
                print(f"[PortfolioSnapshot] Error: {type(exc).__name__}")
                snapshot_errors += 1

        usuarios = [u for u in usuarios_activos if u.telegram_chat_id and suscripcion_activa(u)]
        enviados = 0
        errores = 0
        for usuario in usuarios:
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
        return {
            "enviados": enviados,
            "errores": errores,
            "snapshots": snapshots,
            "snapshot_errors": snapshot_errors,
            "engine": metadata.get("engine_version"),
        }
    finally:
        db.close()
