"""Manifiesto auditable de backfill fundamental V5 para los tres pilotos.

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
