"""Registro auditable de fuentes fundamentales para Caracas Bull V5.

Prioridad: emisor oficial > BVC/regulador > espejo sólo para discovery.
El registro no descarga ni interpreta estados: define fuente, confianza,
aliases y modelo sectorial. Una fuente secundaria nunca basta por sí sola para
confirmar una señal V5.
"""
from __future__ import annotations
from copy import deepcopy

SOURCE_REGISTRY: dict[str, dict] = {
    "MVZ.A": {"issuer":"Mercantil Servicios Financieros, C.A.","aliases":["MVZ.B"],"industry_type":"financial","primary_url":"https://www.msf.com/content/inversionistas/informacion_financiera/reportes.html","source_type":"issuer_official","confidence":100,"coverage":"annual_audited+semiannual_audited+quarterly+monthly_bank_balances","latest_verified":"2026-Q2","status":"verified_primary"},
    "BNC": {"issuer":"Banco Nacional de Crédito, C.A., Banco Universal","aliases":[],"industry_type":"financial","primary_url":"https://www.bncenlinea.com/bnc/informes-anuales","source_type":"issuer_official","confidence":100,"coverage":"annual_reports","latest_verified":"2025-12","status":"verified_primary"},
    "BPV": {"issuer":"Banco Provincial, S.A. Banco Universal","aliases":[],"industry_type":"financial","primary_url":"https://www.provincial.com/","source_type":"issuer_official","confidence":100,"coverage":"semiannual_financial_reports+audited_statements","latest_verified":"2025-H2","status":"verified_primary"},
    "BVL": {"issuer":"Banco de Venezuela, S.A. Banco Universal","aliases":[],"industry_type":"financial","primary_url":"https://www.bancodevenezuela.com/","source_type":"issuer_official","confidence":100,"coverage":"management_reports+published_balances+audited_statements+dividends","latest_verified":"2026","status":"verified_primary"},
    "ABC.A": {"issuer":"Banco del Caribe, C.A., Banco Universal (Bancaribe)","aliases":[],"industry_type":"financial","primary_url":"https://www.bancaribe.com.ve/cifras-e-informes","source_type":"issuer_official","confidence":100,"coverage":"monthly_balances+semiannual_management+external_auditor_reports","latest_verified":"2025-H2","status":"verified_primary"},

    "SVS": {"issuer":"Sivensa, S.A.","aliases":[],"industry_type":"non_financial","primary_url":"https://sivensa.com.ve/inversionistas/","source_type":"issuer_official","confidence":100,"coverage":"annual_audited+quarterly","latest_verified":"2025","status":"verified_primary"},
    "ENV": {"issuer":"Envases Venezolanos, S.A.","aliases":[],"industry_type":"non_financial","primary_url":"https://envasesvenezolanos.com.ve/estados-financieros/","source_type":"issuer_official","confidence":100,"coverage":"annual_financial_statements","latest_verified":"2023","status":"verified_primary"},
    "CRM.A": {"issuer":"Corimon, C.A.","aliases":[],"industry_type":"non_financial","primary_url":"https://www.corimon.com/estados-financieros-2026/","source_type":"issuer_official","confidence":100,"coverage":"consolidated_financial_statements+commissioner_reports","latest_verified":"2025-03","status":"verified_primary"},
    "DOM": {"issuer":"Domínguez & Cía., S.A.","aliases":[],"industry_type":"non_financial","primary_url":"https://domcia.com/informacion-financiera/","source_type":"issuer_official","confidence":100,"coverage":"financial_information+shareholder_notices","latest_verified":"2026","status":"verified_primary"},
    "PIV.B": {"issuer":"PIVCA Promotora de Inversiones y Valores, C.A.","aliases":["PIV.A"],"industry_type":"non_financial","primary_url":"https://pivca.com/prospectos/","source_type":"issuer_official","confidence":100,"coverage":"audited_financial_statements+prospectuses","latest_verified":"2025","status":"verified_primary"},
    "MPA": {"issuer":"Manufacturas de Papel, C.A. (MANPA), S.A.C.A.","aliases":[],"industry_type":"non_financial","primary_url":"https://www.bolsadecaracas.com/","source_type":"bvc_primary_fallback","confidence":90,"coverage":"audited_financial_statements+market_disclosures","latest_verified":"2024","status":"verified_manual_route"},
    "BVCC": {"issuer":"Bolsa de Valores de Caracas, C.A.","aliases":[],"industry_type":"non_financial","primary_url":"https://www.bolsadecaracas.com/","source_type":"issuer_official","confidence":90,"coverage":"financial_statements+shareholder_assembly_materials","latest_verified":"2025-12","status":"verified_manual_route"},
    "RST": {"issuer":"C.A. Ron Santa Teresa, S.A.C.A.","aliases":["RST.B"],"industry_type":"non_financial","primary_url":"https://www.bolsadecaracas.com/","source_type":"bvc_primary_fallback","confidence":85,"coverage":"audited_statements_available_via_market_disclosures","latest_verified":"2025-06","status":"needs_stable_issuer_url"},
    "TDV.D": {"issuer":"C.A. Nacional Teléfonos de Venezuela (CANTV)","aliases":[],"industry_type":"non_financial","primary_url":"https://www.bolsadecaracas.com/","source_type":"bvc_primary_fallback","confidence":85,"coverage":"annual_financial_statements+shareholder_materials","latest_verified":"2024-12","status":"needs_stable_issuer_url"},
}

def _alias_map() -> dict[str, str]:
    out: dict[str, str] = {}
    for canonical, item in SOURCE_REGISTRY.items():
        out[canonical.upper()] = canonical
        for alias in item.get("aliases", []):
            out[str(alias).upper()] = canonical
    return out

ALIASES = _alias_map()

def get_source(symbol: str) -> dict | None:
    canonical = ALIASES.get(str(symbol or "").upper())
    if not canonical:
        return None
    out = deepcopy(SOURCE_REGISTRY[canonical])
    out["canonical_symbol"] = canonical
    return out

def source_confidence(symbol: str) -> int:
    src = get_source(symbol)
    return int(src.get("confidence", 0)) if src else 0

def source_audit_summary(symbols: list[str] | None = None) -> dict:
    universe = [str(s).upper() for s in symbols] if symbols else sorted(ALIASES)
    rows = []
    for symbol in universe:
        src = get_source(symbol)
        rows.append({"symbol":symbol,"covered":bool(src),"status":src.get("status") if src else "unmapped","confidence":src.get("confidence",0) if src else 0,"industry_type":src.get("industry_type") if src else None})
    covered = sum(1 for r in rows if r["covered"])
    verified = sum(1 for r in rows if r["status"] == "verified_primary")
    return {"symbols":len(rows),"covered":covered,"verified_primary":verified,"coverage_pct":round(covered/max(1,len(rows))*100.0,1),"rows":rows}
