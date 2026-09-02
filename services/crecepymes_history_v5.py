"""Historia anual verificada de Inversiones CrecePymes para V5.

Regla de integridad:
- cada ejercicio usa la columna primaria de SU PROPIO informe auditado;
- no se usa FY2023 desde el comparativo FY2024 porque ese comparativo está
  reexpresado en bolívares constantes al 31-12-2024;
- se preserva la base monetaria reportada y la normalización USD se hace luego
  con FX histórico del cierre correspondiente.
"""

CRECEPYMES_HISTORICAL_PILOTS = [
    {
        "document_type": "annual_audited_financial_statements",
        "fiscal_period": "FY2024",
        "as_of": "2024-12-31",
        "audited": True,
        "source_url": "https://www.crecepymes.com/documents/SUNAVAL/Informe%20Auditado%20Inversiones%20CrecePymes%202023-2024.pdf",
        "evidence": (
            "CrecePymes FY2024, estado primario auditado: Total activo 46.312.462; "
            "Total pasivo 11.589.067; Total patrimonio 34.723.395; ganancia neta "
            "4.452.134 Bs. Cifras constantes al 31-12-2024. Ecuación contable validada."
        ),
        "data": {
            "industry_type": "investment_vehicle",
            "total_assets": 46312462.0,
            "total_liabilities": 11589067.0,
            "equity": 34723395.0,
            "net_income": 4452134.0,
            "currency": "VES",
            "monetary_basis": "constant_ves_end_period",
            "as_of": "2024-12-31",
        },
    },
    {
        "document_type": "annual_audited_financial_statements",
        "fiscal_period": "FY2022",
        "as_of": "2022-12-31",
        "audited": True,
        "source_url": "https://www.crecepymes.com/documents/SUNAVAL/Informe%20de%20Auditoria%20Inversiones%20Crecepymes%2C%20C.A.%202022-2021.pdf",
        "evidence": (
            "CrecePymes FY2022, estado primario auditado: Total activo 16.505.427; "
            "Total pasivo 6.075.601; Total patrimonio 10.429.826; ganancia neta "
            "2.862.084 Bs. Cifras constantes al 31-12-2022. Ecuación contable validada."
        ),
        "data": {
            "industry_type": "investment_vehicle",
            "total_assets": 16505427.0,
            "total_liabilities": 6075601.0,
            "equity": 10429826.0,
            "net_income": 2862084.0,
            "currency": "VES",
            "monetary_basis": "constant_ves_end_period",
            "as_of": "2022-12-31",
        },
    },
]
