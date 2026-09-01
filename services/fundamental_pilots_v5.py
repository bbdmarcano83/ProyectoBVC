"""Tres snapshots piloto auditables para validar la tubería V5 end-to-end.

NO se cargan automáticamente en producción. Son fixtures controlados con cifras
extraídas de documentos oficiales y sirven para probar validación/persistencia.
"""

PILOTS = {
    "MVZ.A": {
        "document_type": "quarterly_report",
        "fiscal_period": "2026-Q2",
        "as_of": "2026-06-30",
        "audited": False,
        "source_url": "https://www.msf.com/content/pdfs/historicos/mercantil_servicios_financieros/reportes_trimestrales/esp/2026/PR_MSF_2T_2026.pdf",
        "evidence": "MSF Reporte Segundo Trimestre 2026; cifras expresadas en millones de bolívares",
        "data": {
            "industry_type": "financial",
            "total_assets": 1092169000000.0,
            "equity": 243825000000.0,
            "net_income": 106804000000.0,
            "currency": "VES",
            "as_of": "2026-06-30",
        },
    },
    "SVS": {
        "document_type": "annual_audited_financial_statements",
        "fiscal_period": "FY2025",
        "as_of": "2025-09-30",
        "audited": True,
        "source_url": "https://sivensa.com.ve/wp-content/uploads/2025/12/2025.12.08-SIVENSA-Informe-Auditores-PwC.pdf",
        "evidence": "PwC: estados financieros consolidados de Sivensa al 30-09-2025",
        "data": {
            "industry_type": "non_financial",
            "total_assets": 197414378186.0,
            "total_liabilities": 33849379030.0,
            "equity": 163564999156.0,
            "net_income": -758060382.0,
            "shares_outstanding": 52524376.0,
            "currency": "VES",
            "as_of": "2025-09-30",
        },
    },
    "ICP.B": {
        "document_type": "annual_audited_financial_statements",
        "fiscal_period": "FY2025",
        "as_of": "2025-12-31",
        "audited": True,
        "source_url": "https://www.crecepymes.com/documents/SUNAVAL/Informe%20de%20Auditoria%20Crecepymes%202025-ultimo.pdf",
        "evidence": "Informe de Auditoría Inversiones CrecePymes 2025; cifras constantes",
        "data": {
            "industry_type": "investment_vehicle",
            "total_assets": 273877404.0,
            "total_liabilities": 123014635.0,
            "equity": 150862769.0,
            "net_income": -92353830.0,
            "currency": "VES",
            "as_of": "2025-12-31",
        },
    },
}


def get_pilot(symbol: str) -> dict | None:
    item = PILOTS.get(str(symbol or "").upper())
    return dict(item) if item else None
