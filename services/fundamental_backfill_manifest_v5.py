"""Manifiesto auditable de backfill fundamental V5.

No contiene cifras financieras ni las inventa. Sólo define documentos/períodos
a buscar en fuentes oficiales del emisor y su prioridad de ingestión.
"""
from __future__ import annotations

PILOT_BACKFILL_V5 = {
    "MVZ.A": {
        "issuer": "Mercantil Servicios Financieros, C.A.",
        "industry_type": "financial",
        "discovery_url": "https://www.msf.com/content/inversionistas/informacion_financiera/reportes.html",
        "documents": [
            {
                "fiscal_period": "FY2025",
                "as_of": "2025-12-31",
                "audited": True,
                "document_type": "annual_audited",
                "url": "https://www.msf.com/content/pdfs/historicos/mercantil_servicios_financieros/efsa_cnv/esp/EEFF_2S_MSF_2025.pdf",
            },
            {
                "fiscal_period": "FY2024",
                "as_of": "2024-12-31",
                "audited": True,
                "document_type": "annual_audited",
                "url": "https://msf.com/content/pdfs/historicos/mercantil_servicios_financieros/efsa_cnv/esp/MSFConsolidado31_12_2024conInformedelosauditoresindependientes.pdf",
            },
            {
                "fiscal_period": "FY2023",
                "as_of": "2023-12-31",
                "audited": True,
                "document_type": "annual_audited",
                "url": "https://msf.com/content/pdfs/historicos/mercantil_servicios_financieros/efsa_cnv/esp/MSFConsolidado31_12_2023conInformedelosauditoresindependientes.pdf",
            },
            {
                "fiscal_period": "FY2022",
                "as_of": "2022-12-31",
                "audited": True,
                "document_type": "annual_audited",
                "url": "https://msf.com/content/pdfs/historicos/mercantil_servicios_financieros/efsa_cnv/esp/MSF_diciembre_2022.pdf",
            },
        ],
    },
    "SVS": {
        "issuer": "Siderúrgica Venezolana Sivensa, S.A.",
        "industry_type": "non_financial",
        "discovery_url": "https://sivensa.com.ve/inversionistas/reportes-anuales/",
        "documents": [
            {
                "fiscal_period": "FY2025",
                "as_of": "2025-09-30",
                "audited": True,
                "document_type": "annual_audited",
                "url": "https://sivensa.com.ve/wp-content/uploads/2025/12/2025.12.08-SIVENSA-Informe-Auditores-PwC.pdf",
            },
            {
                "fiscal_period": "FY2024",
                "as_of": "2024-09-30",
                "audited": True,
                "document_type": "annual_audited",
                "url": "https://sivensa.com.ve/wp-content/uploads/2024/11/2024.11.18-SIVENSA-Informe-Auditores-PwC.pdf",
            },
            {
                "fiscal_period": "FY2023",
                "as_of": "2023-09-30",
                "audited": True,
                "document_type": "annual_audited",
                "url": "https://sivensa.com.ve/wp-content/uploads/2023/11/2023.11.13-SIVENSA-Informe-Auditores-PwC.pdf",
            },
            {
                "fiscal_period": "FY2022",
                "as_of": "2022-09-30",
                "audited": True,
                "document_type": "annual_audited",
                "url": "https://sivensa.com.ve/wp-content/uploads/2023/04/20221114SIVENSAInformeContadoresPublicosIndependientesPwC.pdf",
            },
        ],
    },
    "ICP.B": {
        "issuer": "Inversiones CrecePymes, C.A.",
        "industry_type": "investment_vehicle",
        "discovery_url": "https://www.crecepymes.com/report.html",
        "documents": [
            {
                "fiscal_period": "FY2025",
                "as_of": "2025-12-31",
                "audited": True,
                "document_type": "annual_audited",
                "url": "https://www.crecepymes.com/documents/SUNAVAL/Informe%20de%20Auditoria%20Crecepymes%202025-ultimo.pdf",
            },
            {
                "fiscal_period": "FY2024",
                "as_of": "2024-12-31",
                "audited": True,
                "document_type": "annual_audited",
                "url": "https://www.crecepymes.com/documents/SUNAVAL/Informe%20Auditado%20Inversiones%20CrecePymes%202023-2024.pdf",
            },
            {
                "fiscal_period": "FY2023",
                "as_of": "2023-12-31",
                "audited": True,
                "document_type": "comparative_in_2024_audit",
                "url": "https://www.crecepymes.com/documents/SUNAVAL/Informe%20Auditado%20Inversiones%20CrecePymes%202023-2024.pdf",
            },
            {
                "fiscal_period": "FY2022",
                "as_of": "2022-12-31",
                "audited": True,
                "document_type": "comparative_2022_2021_audit",
                "url": "https://www.crecepymes.com/documents/SUNAVAL/Informe%20de%20Auditoria%20Inversiones%20Crecepymes%2C%20C.A.%202022-2021.pdf",
            },
        ],
    },
}


def manifest_summary() -> dict:
    issuers = len(PILOT_BACKFILL_V5)
    docs = sum(len(v.get("documents", [])) for v in PILOT_BACKFILL_V5.values())
    exact = sum(1 for v in PILOT_BACKFILL_V5.values() for d in v.get("documents", []) if d.get("url"))
    pending_discovery = docs - exact
    return {
        "issuers": issuers,
        "documents": docs,
        "exact_urls": exact,
        "pending_discovery": pending_discovery,
        "symbols": sorted(PILOT_BACKFILL_V5),
    }


# Segunda ola: documentos oficiales cuya entidad, fecha de cierre, moneda y
# unidad fueron verificadas en el propio PDF. Cada período usa la columna actual
# de su informe, no una comparativa reexpresada en poder adquisitivo posterior.
VERIFIED_BACKFILL_V5 = {
    "BVCC": {
        "issuer": "Bolsa de Valores de Caracas, C.A.",
        "industry_type": "non_financial",
        "discovery_url": "https://www.bolsadecaracas.com/wp-json/wp/v2/posts/31909",
        "documents": [
            {"fiscal_period": "FY2025", "as_of": "2025-12-31", "audited": True, "document_type": "annual_audited_bvc_image_bundle", "currency": "VES", "monetary_basis": "nominal_ves", "value_multiplier": 1, "statement_unit_evidence": "Expresados en bolívares", "bvc_post_id": 31909, "url": "https://www.bolsadecaracas.com/bolsa-de-valores-de-caracas-ca-informacion-financiera-auditada-estados-financieros-correspondiente-diciembre-2025-2024/"},
        ],
    },
    "FNV": {
        "issuer": "C.A. Fábrica Nacional de Vidrio",
        "industry_type": "non_financial",
        "discovery_url": "https://www.bolsadecaracas.com/wp-json/wp/v2/posts/21390",
        "documents": [
            {"fiscal_period": "FY2022", "as_of": "2022-10-31", "audited": True, "document_type": "annual_audited_bvc_image_bundle", "currency": "VES", "monetary_basis": "constant_ves_end_period", "value_multiplier": 1, "statement_unit_evidence": "Expresados en bolívares constantes", "bvc_post_id": 21390, "url": "https://www.bolsadecaracas.com/c-a-fabrica-nacional-de-vidrio-y-subsidiaria-informacion-financiera-auditada-a-octubre-2022-2021/"},
        ],
    },
    "PGR": {
        "issuer": "Proagro, C.A.",
        "industry_type": "non_financial",
        "discovery_url": "https://www.bolsadecaracas.com/wp-json/wp/v2/posts/17776",
        "documents": [
            {"fiscal_period": "FY2022", "as_of": "2022-08-31", "audited": True, "document_type": "annual_audited_bvc_image_bundle", "currency": "VES", "monetary_basis": "constant_ves_end_period", "value_multiplier": 1, "statement_unit_evidence": "Expresados en bolívares constantes", "bvc_post_id": 17776, "url": "https://www.bolsadecaracas.com/proagro-c-a-y-filiales-informacion-financiera-auditada-al-31-de-agosto-de-2022-2021/"},
        ],
    },
    "PTN": {
        "issuer": "Protinal, C.A.",
        "industry_type": "non_financial",
        "discovery_url": "https://www.bolsadecaracas.com/wp-json/wp/v2/posts/22123",
        "documents": [
            {"fiscal_period": "FY2023", "as_of": "2023-08-31", "audited": True, "document_type": "annual_audited_bvc_image_bundle", "currency": "VES", "monetary_basis": "constant_ves_end_period", "value_multiplier": 1, "statement_unit_evidence": "Expresados en bolívares constantes", "bvc_post_id": 22123, "url": "https://www.bolsadecaracas.com/protinal-c-a-y-filiales-informacion-financiera-auditada-al-31-de-agosto-de-2022-2021-2/"},
        ],
    },
    "VNA.B": {
        "issuer": "Venealternative, S.A.",
        "industry_type": "investment_vehicle",
        "discovery_url": "https://www.bolsadecaracas.com/wp-json/wp/v2/posts/22259",
        "documents": [
            {"fiscal_period": "FY2023", "as_of": "2023-12-31", "audited": True, "document_type": "annual_audited_bvc_image_bundle", "currency": "VES", "monetary_basis": "constant_ves_end_period", "value_multiplier": 1, "statement_unit_evidence": "Expresados en bolívares constantes", "bvc_post_id": 22259, "url": "https://www.bolsadecaracas.com/venealternative-s-a-estados-financieros-al-31-de-diciembre-de-2023-auditados/"},
        ],
    },
    "CRM.A": {
        "issuer": "Corimon, C.A.",
        "industry_type": "non_financial",
        "discovery_url": "https://www.bolsadecaracas.com/wp-json/wp/v2/posts/31494",
        "documents": [
            {"fiscal_period": "FY2025", "as_of": "2025-03-31", "audited": True, "document_type": "annual_audited_bvc_image_bundle", "currency": "VES", "monetary_basis": "constant_ves_end_period", "value_multiplier": 1, "statement_unit_evidence": "Expresados en bolívares constantes", "bvc_post_id": 31494, "url": "https://www.bolsadecaracas.com/corimon-c-a-y-subsidiarias-informacion-financiera-auditada-al-31-de-marzo-de-2025-2024/"},
        ],
    },
    "RST": {
        "issuer": "C.A. Ron Santa Teresa, S.A.C.A.",
        "industry_type": "non_financial",
        "discovery_url": "https://www.bolsadecaracas.com/wp-json/wp/v2/posts/29952",
        "documents": [
            {"fiscal_period": "FY2025", "as_of": "2025-06-30", "audited": True, "document_type": "annual_audited_bvc_image_bundle", "currency": "VES", "monetary_basis": "nominal_ves", "value_multiplier": 1000, "statement_unit_evidence": "En miles de bolívares", "bvc_post_id": 29952, "url": "https://www.bolsadecaracas.com/c-a-ron-santa-teresa-saca-y-companias-filiales-estados-financieros-al-30-de-junio-de-2025-auditado/"},
        ],
    },
    "TDV.D": {
        "issuer": "C.A. Nacional Teléfonos de Venezuela (CANTV)",
        "industry_type": "non_financial",
        "discovery_url": "https://www.bolsadecaracas.com/wp-json/wp/v2/posts/32881",
        "documents": [
            {"fiscal_period": "FY2025", "as_of": "2025-12-31", "audited": True, "document_type": "annual_audited_bvc_image_bundle", "currency": "VES", "monetary_basis": "nominal_ves", "value_multiplier": 1, "statement_unit_evidence": "Expresados en bolívares", "bvc_post_id": 32881, "url": "https://www.bolsadecaracas.com/c-a-nacional-telefonos-de-venezuela-cantv-informacion-financiera-diciembre-2025-2024-auditado-dictamen-de-los-contadores-publicos-mcr-asociados/"},
        ],
    },
    "BPV": {
        "issuer": "Banco Provincial, S.A. Banco Universal",
        "industry_type": "financial",
        "discovery_url": "https://www.provincial.com/personas/informacion-corporativa/informacion-financiera.html",
        "documents": [
            {"fiscal_period": "FY2025", "as_of": "2025-12-31", "audited": True, "document_type": "annual_audited", "currency": "VES", "monetary_basis": "nominal_ves", "value_multiplier": 1, "audit_opinion": "unmodified", "statement_unit_evidence": "Balance general expresado en bolívares", "url": "https://www.provincial.com/content/dam/public-web/venezuela/documents/informe-financiero-2dosemestre-2025.pdf"},
            {"fiscal_period": "FY2024", "as_of": "2024-12-31", "audited": True, "document_type": "annual_audited", "currency": "VES", "monetary_basis": "nominal_ves", "value_multiplier": 1, "url": "https://www.provincial.com/content/dam/public-web/venezuela/documents/informe-2do-semestre-2024-bbva-provincial.pdf"},
            {"fiscal_period": "FY2023", "as_of": "2023-12-31", "audited": True, "document_type": "annual_audited", "currency": "VES", "monetary_basis": "nominal_ves", "value_multiplier": 1, "url": "https://www.provincial.com/content/dam/public-web/venezuela/documents/informe-2do-semestre-2023.pdf"},
            {"fiscal_period": "FY2022", "as_of": "2022-12-31", "audited": True, "document_type": "annual_audited", "currency": "VES", "monetary_basis": "nominal_ves", "value_multiplier": 1, "url": "https://www.provincial.com/content/dam/public-web/venezuela/documents/informe-2do-semestre-2022.pdf"},
        ],
    },
    "BNC": {
        "issuer": "Banco Nacional de Crédito, C.A., Banco Universal",
        "industry_type": "financial",
        "discovery_url": "https://www.bncenlinea.com/bnc/informes-anuales",
        "documents": [
            {"fiscal_period": "FY2025", "as_of": "2025-12-31", "audited": True, "document_type": "annual_audited", "currency": "VES", "monetary_basis": "nominal_ves", "value_multiplier": 1, "url": "https://d3q4nr72nuserl.cloudfront.net/docs/default-source/documents/finalcial-reports/annual-reports/diciembre-2025.pdf?sfvrsn=dafc9f7c_2"},
            {"fiscal_period": "FY2024", "as_of": "2024-12-31", "audited": True, "document_type": "annual_audited", "currency": "VES", "monetary_basis": "nominal_ves", "value_multiplier": 1, "url": "https://d3q4nr72nuserl.cloudfront.net/docs/default-source/documents/finalcial-reports/annual-reports/diciembre-2024.pdf?sfvrsn=d9c946bd_2"},
            {"fiscal_period": "FY2023", "as_of": "2023-12-31", "audited": True, "document_type": "annual_audited", "currency": "VES", "monetary_basis": "nominal_ves", "value_multiplier": 1, "url": "https://d3q4nr72nuserl.cloudfront.net/docs/default-source/documents/finalcial-reports/annual-reports/diciembre-2023.pdf?sfvrsn=3b451378_2"},
            {"fiscal_period": "FY2022", "as_of": "2022-12-31", "audited": True, "document_type": "annual_audited", "currency": "VES", "monetary_basis": "nominal_ves", "value_multiplier": 1, "url": "https://d3q4nr72nuserl.cloudfront.net/docs/default-source/documents/finalcial-reports/annual-reports/diciembre--2022.pdf?sfvrsn=c97a1f77_2"},
        ],
    },
    "ABC.A": {
        "issuer": "Banco del Caribe, C.A., Banco Universal (Bancaribe)",
        "industry_type": "financial",
        "discovery_url": "https://www.bancaribe.com.ve/cifras-e-informes",
        "documents": [
            {"fiscal_period": "FY2025", "as_of": "2025-12-31", "audited": True, "document_type": "annual_audited", "currency": "VES", "monetary_basis": "nominal_ves", "value_multiplier": 1, "url": "https://d3olc33sy92l9e.cloudfront.net/wp-content/uploads/2026/02/Informe_Individual_Auditado-al-31-12-2025.pdf"},
            {"fiscal_period": "FY2024", "as_of": "2024-12-31", "audited": True, "document_type": "annual_audited", "currency": "VES", "monetary_basis": "nominal_ves", "value_multiplier": 1, "url": "https://d3olc33sy92l9e.cloudfront.net/wp-content/uploads/2025/02/Banco_del-Caribe_C.A._Banco_Universal_Semestral_Dic-Jun2024-003.pdf"},
            {"fiscal_period": "FY2023", "as_of": "2023-12-31", "audited": True, "document_type": "annual_audited", "currency": "VES", "monetary_basis": "nominal_ves", "value_multiplier": 1, "url": "https://d3olc33sy92l9e.cloudfront.net/wp-content/uploads/2024/02/Informe-Semestral-Auditado-Dic.Jun-2023.pdf"},
            {"fiscal_period": "FY2022", "as_of": "2022-12-31", "audited": True, "document_type": "annual_audited", "currency": "VES", "monetary_basis": "nominal_ves", "value_multiplier": 1, "url": "https://d3olc33sy92l9e.cloudfront.net/wp-content/uploads/2023/02/Estados-Financieros-Auditados-31-12-2022-1.pdf"},
        ],
    },
    "IVC.A": {
        "issuer": "INVACA Investment Company, S.A.C.A.",
        "industry_type": "non_financial",
        "discovery_url": "https://invaca.com.ve/es/investor-hub",
        "documents": [
            {"fiscal_period": "FY2025", "as_of": "2025-06-30", "audited": True, "document_type": "annual_audited", "currency": "VES", "monetary_basis": "constant_ves_end_period", "value_multiplier": 1, "url": "https://ambitious-art-5a4bef14f6.media.strapiapp.com/INVACA_EEFF_2025_24_11_Nov25_81ac7495a7.pdf"},
            {"fiscal_period": "FY2024", "as_of": "2024-06-30", "audited": True, "document_type": "annual_audited", "currency": "VES", "monetary_basis": "constant_ves_end_period", "value_multiplier": 1, "url": "https://ambitious-art-5a4bef14f6.media.strapiapp.com/INVACA_EEFF_2024_23_20_Dic24_62001aff82.pdf"},
            {"fiscal_period": "FY2023", "as_of": "2023-06-30", "audited": True, "document_type": "annual_audited", "currency": "VES", "monetary_basis": "constant_ves_end_period", "value_multiplier": 1, "url": "https://ambitious-art-5a4bef14f6.media.strapiapp.com/INVACA_EEFF_2023_22_AEA_f49f7dd645.pdf"},
        ],
    },
    "ENV": {
        "issuer": "Envases Venezolanos, S.A.",
        "industry_type": "non_financial",
        "discovery_url": "https://envasesvenezolanos.com.ve/estados-financieros/",
        "documents": [
            {"fiscal_period": "FY2023", "as_of": "2023-08-31", "audited": True, "document_type": "annual_audited", "currency": "VES", "monetary_basis": "constant_ves_end_period", "value_multiplier": 1, "url": "https://envasesvenezolanos.com.ve/wp-content/uploads/2023/10/informe_auditores_2022_2023.pdf"},
            {"fiscal_period": "FY2022", "as_of": "2022-08-31", "audited": True, "document_type": "annual_audited", "currency": "VES", "monetary_basis": "constant_ves_end_period", "value_multiplier": 1, "url": "https://envasesvenezolanos.com.ve/wp-content/uploads/2023/04/informe_auditores_2021_2022.pdf"},
            {"fiscal_period": "FY2021", "as_of": "2021-08-31", "audited": True, "document_type": "annual_audited", "currency": "VES", "monetary_basis": "constant_ves_end_period", "value_multiplier": 1, "url": "https://envasesvenezolanos.com.ve/wp-content/uploads/2023/04/informe_auditores_2020_2021.pdf"},
            {"fiscal_period": "FY2020", "as_of": "2020-08-31", "audited": True, "document_type": "annual_audited", "currency": "VES", "monetary_basis": "constant_ves_end_period", "value_multiplier": 1, "url": "https://envasesvenezolanos.com.ve/wp-content/uploads/2023/04/informe_auditores_2019_2020.pdf"},
        ],
    },
    "BVL": {
        "issuer": "Banco de Venezuela, S.A. Banco Universal",
        "industry_type": "financial",
        "discovery_url": "https://www.bancodevenezuela.com/reportes-financieros/",
        "documents": [
            {"fiscal_period": "FY2024", "as_of": "2024-12-31", "audited": True, "document_type": "annual_audited", "currency": "VES", "monetary_basis": "nominal_ves", "value_multiplier": 1, "audit_opinion": "qualified", "statement_unit_evidence": "Expresados en bolívares", "url": "https://www.bancodevenezuela.com/files/informesgestion/Informe%20II%20Semestre%202024%20Estados%20financieros%20auditados.pdf"},
        ],
    },
    "TPG": {
        "issuer": "C.A. Telares de Palo Grande",
        "industry_type": "non_financial",
        "discovery_url": "https://telaresdepalogrande.com/tpg/wp/quienes-somos/informacion-financiera/",
        "documents": [
            {"fiscal_period": "FY2025", "as_of": "2025-12-31", "audited": True, "document_type": "annual_audited", "currency": "VES", "monetary_basis": "constant_ves_end_period", "value_multiplier": 1, "audit_opinion": "unmodified_with_emphasis", "statement_unit_evidence": "Expresados en bolívares constantes", "url": "https://telaresdepalogrande.com/tpg/wp/wp-content/uploads/2026/07/Informe-E-F-Auditados-TPG-31-12-2025.pdf"},
            {"fiscal_period": "FY2024", "as_of": "2024-12-31", "audited": True, "document_type": "annual_audited", "currency": "VES", "monetary_basis": "constant_ves_end_period", "value_multiplier": 1, "url": "https://telaresdepalogrande.com/tpg/wp/wp-content/uploads/2026/07/Informe-E-F-Auditados-TPG-al-31-12-2024.pdf"},
        ],
    },
    "CGQ": {
        "issuer": "Corporación Grupo Químico, C.A.",
        "industry_type": "non_financial",
        "discovery_url": "https://www.grupoquimico.com/accionistas-1",
        "documents": [
            {"fiscal_period": "FY2025", "as_of": "2025-12-31", "audited": True, "document_type": "annual_audited", "currency": "VES", "monetary_basis": "constant_ves_end_period", "value_multiplier": 1000, "audit_opinion": "unmodified_with_emphasis", "statement_unit_evidence": "Estados financieros consolidados en miles de bolívares constantes", "url": "https://www.grupoquimico.com/_files/ugd/ad64a7_db932ce5114c4976b19a711232d0fada.pdf"},
            {"fiscal_period": "FY2024", "as_of": "2024-12-31", "audited": True, "document_type": "annual_audited", "currency": "VES", "monetary_basis": "constant_ves_end_period", "value_multiplier": 1000, "statement_unit_evidence": "Miles de bolívares constantes", "url": "https://www.grupoquimico.com/_files/ugd/ad64a7_14518c45430a46d7b5944fd62a7e594d.pdf"},
            {"fiscal_period": "FY2023", "as_of": "2023-12-31", "audited": True, "document_type": "annual_audited", "currency": "VES", "monetary_basis": "constant_ves_end_period", "value_multiplier": 1000, "url": "https://www.grupoquimico.com/_files/ugd/38bdc9_89c1eab827674e96812de5dccba474d2.pdf"},
            {"fiscal_period": "FY2022", "as_of": "2022-12-31", "audited": True, "document_type": "annual_audited", "currency": "VES", "monetary_basis": "constant_ves_end_period", "value_multiplier": 1000, "url": "https://www.grupoquimico.com/_files/ugd/38bdc9_3cb23edcc0564651bb4563837bbdfe8d.pdf"},
        ],
    },
    "ARC.A": {
        "issuer": "ARCA Inmuebles y Valores, C.A.",
        "industry_type": "non_financial",
        "discovery_url": "https://arcainmueblesyvalores.com/",
        "documents": [
            {"fiscal_period": "FY2023", "as_of": "2023-12-31", "audited": True, "document_type": "annual_audited", "currency": "VES", "monetary_basis": "constant_ves_end_period", "value_multiplier": 1, "audit_opinion": "qualified_scope", "validation_notes": "El informe revela que estados de una afiliada que representa 98% del activo consolidado fueron auditados por otros auditores.", "statement_unit_evidence": "Expresado en bolívares constantes", "url": "https://arcainmueblesyvalores.com/wp-content/uploads/2024/08/AUDITORIA-DE-ESTADOS-FINANCIEROS-DE-ARCA-INMUEBLES-Y-VALORES-C.A.-Y-FILIAL-1.pdf"},
        ],
    },
    "GZL": {
        "issuer": "Grupo Zuliano, C.A.",
        "industry_type": "investment_vehicle",
        "discovery_url": "https://www.grupozuliano.com.ve/site/index.php/informacion-al-inversor/estados-financieros-auditados",
        "documents": [
            {"fiscal_period": "FY2026", "as_of": "2026-02-28", "audited": True, "document_type": "annual_audited", "currency": "VES", "monetary_basis": "nominal_ves", "value_multiplier": 1, "audit_opinion": "qualified", "statement_unit_evidence": "En bolívares", "url": "https://www.grupozuliano.com.ve/site/images/GZL_INFORME_NIIF_FEBRERO_2026-2025_VERSION_FINAL.pdf"},
            {"fiscal_period": "FY2025", "as_of": "2025-02-28", "audited": True, "document_type": "comparative_in_2026_audit", "preferred_column": 1, "currency": "VES", "monetary_basis": "nominal_ves", "value_multiplier": 1, "audit_opinion": "qualified", "statement_unit_evidence": "En bolívares", "url": "https://www.grupozuliano.com.ve/site/images/GZL_INFORME_NIIF_FEBRERO_2026-2025_VERSION_FINAL.pdf"},
            {"fiscal_period": "FY2024", "as_of": "2024-02-29", "audited": True, "document_type": "annual_audited", "currency": "VES", "monetary_basis": "nominal_ves", "value_multiplier": 1, "url": "https://www.grupozuliano.com.ve/site/images/materiales/INFORME_AUDITADO_NIIF_GZL_29_FEB_2024_compressed.pdf"},
            {"fiscal_period": "FY2023", "as_of": "2023-02-28", "audited": True, "document_type": "annual_audited", "currency": "VES", "monetary_basis": "nominal_ves", "value_multiplier": 1, "url": "https://www.grupozuliano.com.ve/site/images/materiales/GZL_INFORME_AUDITADO_NIIF_FEBRERO_2023-2022.pdf"},
        ],
    },
    "DOM": {
        "issuer": "Domínguez & Cía., S.A.",
        "industry_type": "non_financial",
        "discovery_url": "https://domcia.com/informacion-financiera/",
        "documents": [
            {"fiscal_period": "FY2022", "as_of": "2022-11-30", "audited": True, "document_type": "annual_audited", "currency": "VES", "monetary_basis": "constant_ves_end_period", "value_multiplier": 1, "url": "https://domcia.com/wp-content/uploads/2023/02/DominguezCia2022-16feb23-def.pdf"},
        ],
    },
}


FUNDAMENTAL_BACKFILL_V5 = {**PILOT_BACKFILL_V5, **VERIFIED_BACKFILL_V5}


def full_manifest_summary() -> dict:
    issuers = len(FUNDAMENTAL_BACKFILL_V5)
    docs = sum(len(v.get("documents", [])) for v in FUNDAMENTAL_BACKFILL_V5.values())
    exact = sum(1 for v in FUNDAMENTAL_BACKFILL_V5.values() for d in v.get("documents", []) if d.get("url"))
    return {
        "issuers": issuers,
        "documents": docs,
        "exact_urls": exact,
        "pending_discovery": docs - exact,
        "symbols": sorted(FUNDAMENTAL_BACKFILL_V5),
    }
