"""Registro auditable de fuentes fundamentales para Caracas Bull V5.

Jerarquía de procedencia: emisor/BVC/SUNAVAL son evidencia nivel A y siempre
tienen precedencia. Fuentes secundarias HTTPS trazables pueden aportar evidencia
nivel B con menor confianza cuando no existe una cifra nivel A utilizable.

El registro no descarga ni interpreta estados: define fuente primaria del emisor,
confianza, aliases y modelo sectorial. La admisibilidad A/B, la resolución de
conflictos y la precedencia se aplican en ``fundamental_certifier_policy_v5``;
los controles contables, de unidad y FX continúan siendo fail-closed para cada
dato fundamental, no para la elegibilidad del activo.
"""
from __future__ import annotations
from copy import deepcopy
from urllib.parse import urlparse

SOURCE_REGISTRY: dict[str, dict] = {
    # Bancos / financieras operativas
    "MVZ.A": {"issuer":"Mercantil Servicios Financieros, C.A.","aliases":["MVZ.B"],"industry_type":"financial","primary_url":"https://www.msf.com/content/inversionistas/informacion_financiera/reportes.html","source_type":"issuer_official","confidence":100,"coverage":"annual_audited+semiannual_audited+quarterly+monthly_bank_balances","latest_verified":"2026-Q2","status":"verified_primary"},
    "BNC": {"issuer":"Banco Nacional de Crédito, C.A., Banco Universal","aliases":[],"industry_type":"financial","primary_url":"https://www.bncenlinea.com/bnc/informes-anuales","document_hosts":["d3q4nr72nuserl.cloudfront.net"],"source_type":"issuer_official","confidence":100,"coverage":"annual_reports","latest_verified":"2025-12","status":"verified_primary"},
    "BVL": {"issuer":"Bancamiga Banco Universal, C.A.","aliases":[],"industry_type":"financial","primary_url":"https://bancamiga.com/informacion-financiera/","source_type":"issuer_official","confidence":100,"coverage":"financial_information","latest_verified":"2026","status":"verified_primary"},
    "BVC": {"issuer":"Bolsa de Valores de Caracas, C.A.","aliases":[],"industry_type":"financial","primary_url":"https://www.bolsadecaracas.com/","source_type":"issuer_official","confidence":100,"coverage":"issuer_site","latest_verified":"2026","status":"verified_primary"},
    "RST": {"issuer":"C.A. Ron Santa Teresa","aliases":[],"industry_type":"non_financial","primary_url":"https://www.ronsantateresa.com/","source_type":"issuer_official","confidence":100,"coverage":"issuer_site+BVC_financial_notice","latest_verified":"2025","status":"verified_primary"},
    "PIV.B": {"issuer":"Proyectos de Inversión Valores, C.A. (PIVCA)","aliases":[],"industry_type":"investment_vehicle","primary_url":"https://pivca.com/","source_type":"issuer_official","confidence":100,"coverage":"issuer_site","latest_verified":"2025","status":"verified_primary"},
    "ABC.A": {"issuer":"ABC Capital Markets, C.A.","aliases":[],"industry_type":"investment_vehicle","primary_url":"https://abccapitalmarkets.com/","document_hosts":["d3olc33sy92l9e.cloudfront.net"],"source_type":"issuer_official","confidence":100,"coverage":"issuer_site","latest_verified":"2025","status":"verified_primary"},
    "BPV": {"issuer":"Banco Provincial, S.A. Banco Universal","aliases":[],"industry_type":"financial","primary_url":"https://www.provincial.com/","source_type":"issuer_official","confidence":100,"coverage":"issuer_site","latest_verified":"2025","status":"verified_primary"},
    "IVC.A": {"issuer":"Inversiones Vencred, C.A.","aliases":[],"industry_type":"investment_vehicle","primary_url":"https://www.inversionesvencred.com/","source_type":"issuer_official","confidence":100,"coverage":"issuer_site","latest_verified":"2025","status":"verified_primary"},
    "DOM": {"issuer":"Domínguez & Cía., S.A.","aliases":[],"industry_type":"non_financial","primary_url":"https://www.domasa.com/","source_type":"issuer_official","confidence":100,"coverage":"issuer_site","latest_verified":"2025","status":"verified_primary"},
    "ENV": {"issuer":"Envases Venezolanos, S.A.","aliases":[],"industry_type":"non_financial","primary_url":"https://envasesvenezolanos.com/","source_type":"issuer_official","confidence":100,"coverage":"issuer_site","latest_verified":"2025","status":"verified_primary"},
    "FNV": {"issuer":"Fondo de Valores Inmobiliarios, SACA","aliases":[],"industry_type":"investment_vehicle","primary_url":"https://fvi.com.ve/","source_type":"issuer_official","confidence":100,"coverage":"issuer_site","latest_verified":"2025","status":"verified_primary"},
    "PGR": {"issuer":"Protinal, C.A.","aliases":[],"industry_type":"non_financial","primary_url":"https://www.protinal.com.ve/","source_type":"issuer_official","confidence":100,"coverage":"issuer_site","latest_verified":"2025","status":"verified_primary"},
    "GZL": {"issuer":"Grupo Zuliano, C.A.","aliases":[],"industry_type":"non_financial","primary_url":"https://grupozuliano.com/","source_type":"issuer_official","confidence":100,"coverage":"issuer_site","latest_verified":"2025","status":"verified_primary"},
    "CGQ": {"issuer":"Corporación Grupo Químico, C.A.","aliases":[],"industry_type":"non_financial","primary_url":"https://www.grupoquimico.com/","source_type":"issuer_official","confidence":100,"coverage":"issuer_site","latest_verified":"2025","status":"verified_primary"},
    "TPG": {"issuer":"Telares de Palo Grande, C.A.","aliases":[],"industry_type":"non_financial","primary_url":"https://telaresdepalogrande.com/","source_type":"issuer_official","confidence":100,"coverage":"issuer_site","latest_verified":"2025","status":"verified_primary"},
    "EFE": {"issuer":"Productos EFE, S.A.","aliases":[],"industry_type":"non_financial","primary_url":"https://www.productosefe.com/","source_type":"issuer_official","confidence":100,"coverage":"issuer_site+BVC","latest_verified":"2024","status":"verified_primary"},
    "TDV.D": {"issuer":"Compañía Anónima Nacional Teléfonos de Venezuela (CANTV)","aliases":[],"industry_type":"non_financial","primary_url":"https://www.cantv.com.ve/","source_type":"issuer_official","confidence":100,"coverage":"issuer_site+BVC","latest_verified":"2025","status":"verified_primary"},
    "SVS": {"issuer":"Sivensa, S.A.","aliases":[],"industry_type":"non_financial","primary_url":"https://www.sivensa.com.ve/","source_type":"issuer_official","confidence":100,"coverage":"annual_audited","latest_verified":"2025","status":"verified_primary"},
    "ICP.B": {"issuer":"Invaca, C.A.","aliases":[],"industry_type":"investment_vehicle","primary_url":"https://invaca.com/","source_type":"issuer_official","confidence":100,"coverage":"issuer_site","latest_verified":"2025","status":"verified_primary"},
    "CCP.B": {"issuer":"Clabe Capital, C.A.","aliases":[],"industry_type":"investment_vehicle","primary_url":"https://clabecapital.com/","source_type":"issuer_official","confidence":100,"coverage":"issuer_site","latest_verified":"2026","status":"registered_primary"},
    "CCR": {"issuer":"Cerámica Carabobo, S.A.C.A.","aliases":[],"industry_type":"non_financial","primary_url":"https://ceramicacarabobo.com/","source_type":"issuer_official","confidence":100,"coverage":"issuer_site","latest_verified":"2026","status":"registered_primary"},
    "FNC": {"issuer":"Fábrica Nacional de Cementos, S.A.C.A.","aliases":[],"industry_type":"non_financial","primary_url":"https://www.fnc.com.ve/","source_type":"issuer_official","confidence":100,"coverage":"issuer_site","latest_verified":"2026","status":"registered_primary"},
    "GMC.B": {"issuer":"Grupo Mantra, C.A.","aliases":[],"industry_type":"investment_vehicle","primary_url":"https://grupomantra.com/","source_type":"issuer_official","confidence":100,"coverage":"issuer_site","latest_verified":"2026","status":"registered_primary"},
    "MPA": {"issuer":"Mercantil Servicios Financieros Internacional, C.A.","aliases":[],"industry_type":"financial","primary_url":"https://www.msf.com/","source_type":"issuer_official","confidence":100,"coverage":"issuer_site","latest_verified":"2026","status":"registered_primary"},
    "MTC.B": {"issuer":"Montesco, C.A.","aliases":[],"industry_type":"investment_vehicle","primary_url":"https://montesco.com.ve/","source_type":"issuer_official","confidence":100,"coverage":"issuer_site","latest_verified":"2026","status":"registered_primary"},
    "PCP.B": {"issuer":"Páez Capital, C.A.","aliases":[],"industry_type":"investment_vehicle","primary_url":"https://paezcapital.com/","source_type":"issuer_official","confidence":100,"coverage":"issuer_site","latest_verified":"2026","status":"registered_primary"},
    "PER": {"issuer":"Promotora Empresarial, C.A.","aliases":[],"industry_type":"investment_vehicle","primary_url":"https://promotoraempresarial.com/","source_type":"issuer_official","confidence":100,"coverage":"issuer_site","latest_verified":"2026","status":"registered_primary"},
    "MVZ.B": {"issuer":"Mercantil Servicios Financieros, C.A.","aliases":["MVZ.A"],"industry_type":"financial","primary_url":"https://www.msf.com/content/inversionistas/informacion_financiera/reportes.html","source_type":"issuer_official","confidence":100,"coverage":"annual_audited+semiannual_audited+quarterly+monthly_bank_balances","latest_verified":"2026-Q2","status":"verified_primary"},
    "ABC.B": {"issuer":"ABC Capital Markets, C.A.","aliases":["ABC.A"],"industry_type":"investment_vehicle","primary_url":"https://abccapitalmarkets.com/","document_hosts":["d3olc33sy92l9e.cloudfront.net"],"source_type":"issuer_official","confidence":100,"coverage":"issuer_site","latest_verified":"2025","status":"verified_primary"},
    "IVC.B": {"issuer":"Inversiones Vencred, C.A.","aliases":["IVC.A"],"industry_type":"investment_vehicle","primary_url":"https://www.inversionesvencred.com/","source_type":"issuer_official","confidence":100,"coverage":"issuer_site","latest_verified":"2025","status":"verified_primary"},
}


def get_source(symbol: str) -> dict | None:
    key = str(symbol or "").upper().strip()
    source = SOURCE_REGISTRY.get(key)
    return deepcopy(source) if source else None


def _host(url: str) -> str:
    return (urlparse(str(url or "")).hostname or "").lower().strip(".")


def source_url_allowed(symbol: str, url: str) -> bool:
    source = get_source(symbol)
    if not source:
        return False
    target = _host(url)
    allowed = {_host(source.get("primary_url", ""))}
    allowed.update(str(x).lower().strip(".") for x in source.get("document_hosts", []))
    allowed.discard("")
    return any(target == host or target.endswith("." + host) for host in allowed)


def source_audit_summary(symbols: list[str]) -> dict:
    mapped = []
    unmapped = []
    for raw in symbols:
        symbol = str(raw or "").upper().strip()
        source = get_source(symbol)
        if source:
            mapped.append({
                "symbol": symbol,
                "issuer": source.get("issuer"),
                "industry_type": source.get("industry_type"),
                "source_type": source.get("source_type"),
                "confidence": source.get("confidence"),
                "status": source.get("status"),
                "primary_url": source.get("primary_url"),
            })
        else:
            unmapped.append(symbol)
    return {"mapped": mapped, "unmapped": unmapped, "mapped_count": len(mapped), "unmapped_count": len(unmapped)}
