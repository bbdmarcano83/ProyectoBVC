from services.fundamental_autoreview_v5 import propose_fail_closed_selections


def _opt(index, value, page, col, alias, evidence, years=(2025, 2024), quality="accounting_row"):
    return {
        "index": index,
        "value": value,
        "page": page,
        "column_index": col,
        "alias": alias,
        "evidence": evidence,
        "page_years": list(years),
        "context_quality": quality,
    }


def test_component_rows_cannot_impersonate_statement_totals():
    review = {
        "valid": True,
        "industry_type": "non_financial",
        "preferred_column": 0,
        "fields": {
            "total_assets": [
                _opt(0, 650.0, 7, 0, "total activo", "Total activo corriente 650 700"),
                _opt(1, 350.0, 7, 0, "total activo", "Total activo no corriente 350 300"),
                _opt(2, 1000.0, 7, 0, "derived_total_assets", "corriente + no corriente", quality="derived_accounting_total"),
            ],
            "total_liabilities": [
                _opt(0, 200.0, 7, 0, "total pasivo", "Total pasivo corriente 200 250"),
                _opt(1, 100.0, 7, 0, "total pasivo", "Total pasivo no corriente 100 100"),
                _opt(2, 300.0, 7, 0, "derived_total_liabilities", "corriente + no corriente", quality="derived_accounting_total"),
            ],
            "equity": [
                _opt(0, 700.0, 7, 0, "total patrimonio", "Total patrimonio 700 650"),
                _opt(1, 15.0, 7, 0, "patrimonio", "Nota 15 patrimonio"),
            ],
            "net_income": [
                _opt(0, -461.0, 8, 0, "resultado neto", "Resultado neto operativo (461)"),
                _opt(1, -391.0, 8, 0, "resultado neto del año", "Resultado neto del año (391)"),
            ],
        },
    }
    result = propose_fail_closed_selections(review)
    assert result["valid"] is True
    assert result["selections"]["total_assets"] == 2
    assert result["selections"]["total_liabilities"] == 2
    assert result["selections"]["equity"] == 0
    assert result["selections"]["net_income"] == 1


def test_equal_duplicate_aliases_do_not_create_false_ambiguity():
    review = {
        "valid": True,
        "industry_type": "investment_vehicle",
        "preferred_column": 0,
        "fields": {
            "total_assets": [
                _opt(0, 1000.0, 5, 0, "total activo", "Total activo 1000"),
                _opt(1, 1000.0, 5, 0, "total activos", "Total activos 1000"),
            ],
            "total_liabilities": [_opt(0, 300.0, 5, 0, "total pasivo", "Total pasivo 300")],
            "equity": [
                _opt(0, 700.0, 5, 0, "total patrimonio", "Total patrimonio 700"),
                _opt(1, 700.0, 5, 0, "patrimonio total", "Patrimonio total 700"),
            ],
        },
    }
    result = propose_fail_closed_selections(review)
    assert result["valid"] is True
    assert result["missing_required"] == []
