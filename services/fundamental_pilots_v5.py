"""Snapshots piloto auditables para validar la tubería V5 end-to-end.

Las cifras provienen de fuentes oficiales identificadas. Las tasas BCV históricas
no se inventan: la ingesta las resuelve y persiste con metadata de procedencia.
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
            "monetary_basis": "nominal_ves",
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
            "monetary_basis": "constant_ves_end_period",
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
            "monetary_basis": "constant_ves_end_period",
            "as_of": "2025-12-31",
        },
    },
}

# Serie oficial de Mercantil Servicios Financieros publicada en su página de
# cifras históricas. La fuente declara las magnitudes en miles de Bs.; aquí se
# convierten a VES multiplicando por 1.000. No se deriva Pasivo por diferencia.
# Se marca audited=False porque la fuente de estas tres filas es la tabla oficial
# de cifras del emisor, aunque los años también disponen de estados auditados.
#
# Para Sivensa cada año histórico usa SU PROPIO informe auditado y únicamente la
# columna del ejercicio corriente de ese PDF. No se reutiliza la columna
# comparativa del informe del año siguiente porque está reexpresada a moneda
# constante de otra fecha de cierre.
HISTORICAL_PILOTS = {
    "MVZ.A": [
        {
            "document_type": "official_historical_figures",
            "fiscal_period": "FY2024",
            "as_of": "2024-12-31",
            "audited": False,
            "source_url": "https://www.msf.com/content/inversionistas/informacion_financiera/cifras_mercantil.html",
            "evidence": "MSF Cifras Mercantil: Diciembre 2024, tabla histórica en miles de Bs.",
            "data": {
                "industry_type": "financial",
                "total_assets": 50269001000.0,
                "equity": 10489897000.0,
                "net_income": 2999594000.0,
                "currency": "VES",
                "monetary_basis": "nominal_ves",
                "as_of": "2024-12-31",
            },
        },
        {
            "document_type": "official_historical_figures",
            "fiscal_period": "FY2023",
            "as_of": "2023-12-31",
            "audited": False,
            "source_url": "https://www.msf.com/content/inversionistas/informacion_financiera/cifras_mercantil.html",
            "evidence": "MSF Cifras Mercantil: 2023, tabla histórica en miles de Bs.",
            "data": {
                "industry_type": "financial",
                "total_assets": 29613943000.0,
                "equity": 5958514000.0,
                "net_income": 1161962000.0,
                "currency": "VES",
                "monetary_basis": "nominal_ves",
                "as_of": "2023-12-31",
            },
        },
        {
            "document_type": "official_historical_figures",
            "fiscal_period": "FY2022",
            "as_of": "2022-12-31",
            "audited": False,
            "source_url": "https://www.msf.com/content/inversionistas/informacion_financiera/cifras_mercantil.html",
            "evidence": "MSF Cifras Mercantil: 2022, tabla histórica en miles de Bs.",
            "data": {
                "industry_type": "financial",
                "total_assets": 11619045000.0,
                "equity": 2670873000.0,
                "net_income": 884935000.0,
                "currency": "VES",
                "monetary_basis": "nominal_ves",
                "as_of": "2022-12-31",
            },
        },
    ],
    "SVS": [
        {
            "document_type": "annual_audited_financial_statements",
            "fiscal_period": "FY2024",
            "as_of": "2024-09-30",
            "audited": True,
            "source_url": "https://sivensa.com.ve/wp-content/uploads/2024/11/2024.11.18-SIVENSA-Informe-Auditores-PwC.pdf",
            "evidence": "PwC Sivensa FY2024: estado consolidado primario; Activo 30.778.195.109, Pasivo 5.818.745.451, Patrimonio 24.959.449.658 y pérdida neta 3.942.518.486 Bs constantes al 30-09-2024.",
            "data": {
                "industry_type": "non_financial",
                "total_assets": 30778195109.0,
                "total_liabilities": 5818745451.0,
                "equity": 24959449658.0,
                "net_income": -3942518486.0,
                "currency": "VES",
                "monetary_basis": "constant_ves_end_period",
                "as_of": "2024-09-30",
            },
        },
        {
            "document_type": "annual_audited_financial_statements",
            "fiscal_period": "FY2023",
            "as_of": "2023-09-30",
            "audited": True,
            "source_url": "https://sivensa.com.ve/wp-content/uploads/2023/11/2023.11.22-SIVENSA-Informe-Auditores-PwC-v2.pdf",
            "evidence": "PwC Sivensa FY2023: estado consolidado primario; Activo 37.392.980.099, Pasivo 5.966.393.028, Patrimonio 31.426.587.071 y pérdida neta 39.268.305 Bs constantes al 30-09-2023.",
            "data": {
                "industry_type": "non_financial",
                "total_assets": 37392980099.0,
                "total_liabilities": 5966393028.0,
                "equity": 31426587071.0,
                "net_income": -39268305.0,
                "currency": "VES",
                "monetary_basis": "constant_ves_end_period",
                "as_of": "2023-09-30",
            },
        },
        {
            "document_type": "annual_audited_financial_statements",
            "fiscal_period": "FY2022",
            "as_of": "2022-09-30",
            "audited": True,
            "source_url": "https://sivensa.com.ve/wp-content/uploads/2022/12/2022.12.29-SIVENSA-Informe-Auditores-PwC.pdf",
            "evidence": "PwC Sivensa FY2022: estado consolidado primario; Activo 35.174.963.773, Pasivo 5.807.262.905, Patrimonio 29.367.700.868 y utilidad neta 1.626.124.749 Bs constantes al 30-09-2022.",
            "data": {
                "industry_type": "non_financial",
                "total_assets": 35174963773.0,
                "total_liabilities": 5807262905.0,
                "equity": 29367700868.0,
                "net_income": 1626124749.0,
                "currency": "VES",
                "monetary_basis": "constant_ves_end_period",
                "as_of": "2022-09-30",
            },
        },
    ],
}


def get_pilot(symbol: str) -> dict | None:
    item = PILOTS.get(str(symbol or "").upper())
    return dict(item) if item else None
