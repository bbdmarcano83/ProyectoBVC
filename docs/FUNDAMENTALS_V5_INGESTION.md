# Caracas Bull V5 — Ingesta fundamental auditable

## Objetivo

Separar estrictamente cuatro fases: descubrimiento de fuente, descarga/documento, normalización y scoring. Ninguna cifra entra al V5 sólo por aparecer en una web secundaria.

## Jerarquía de fuentes

1. Portal oficial del emisor / relaciones con inversionistas.
2. BVC, SUNAVAL, SUDEBAN u otro regulador oficial.
3. Fuente secundaria sólo para descubrir el documento original.

El registro está en `services/fundamental_sources_v5.py`. Símbolos no registrados quedan `unmapped` y no pueden producir una confirmación V5.

## Tipos de emisor

- `non_financial`: Greenblatt + Graham + Buffett.
- `financial`: métricas bancarias/financieras; no EBIT/EV.
- `investment_vehicle`: NAV/patrimonio, descuento/prima, rentabilidad, distribuciones y consistencia; no Greenblatt operativo.

## Persistencia

Neon/SQLAlchemy usa dos tablas nuevas:

- `fundamental_documents`: trazabilidad documental, período, auditoría, URL, confianza y hash.
- `fundamental_snapshots`: JSON normalizado, tipo de emisor, score de validación y estado validado.

`Base.metadata.create_all()` crea las tablas nuevas en una base existente sin borrar datos.

## Validación mínima

`services/fundamental_store_v5.py` aplica un flujo fail-closed:

- símbolo debe estar en el registro oficial;
- confianza de fuente >= 80;
- URL HTTPS;
- período `as_of` obligatorio;
- no se imputan faltantes;
- campos numéricos presentes deben ser numéricos;
- si existen Activos, Pasivos y Patrimonio, se comprueba `Activos ≈ Pasivos + Patrimonio`;
- diferencia > 5% rechaza el snapshot; 2–5% penaliza la confianza;
- score de validación mínimo: 70/100.

## Ingesta

Entrada única: `ingest_normalized_report(...)` en `services/fundamental_collector_v5.py`.

El collector normaliza aliases de nombres (`assets -> total_assets`, `profit -> net_income`, etc.) sin crear valores inexistentes. Luego produce reporte de cobertura, valida y persiste de manera idempotente.

## Campos base

Campos admitidos incluyen:

`market_cap`, `total_debt`, `cash`, `ebit`, `net_income`, `equity`, `total_assets`, `total_liabilities`, `revenue`, `free_cash_flow`, `current_assets`, `current_liabilities`, `net_ppe`, `operating_cash_flow`, `capex`, `shares_outstanding`, `nav`, `nav_per_share`, `market_price`, `distribution_yield_pct`, `earnings_history`, `revenue_history`, `fcf_history`, `nav_history`.

Ausencia de un campo = ausencia real. V5 no lo reemplaza por cero ni lo estima.

## Runtime

`services/fundamentals_v5.py` consulta primero `fundamental_snapshots` validados. El JSON/archivo manual queda sólo como fallback controlado para tests o staging.

`SCORING_ENGINE_V5_ENABLED=false` sigue siendo el default hasta que tengamos cobertura y validación suficientes.

## Próxima fase

Crear adaptadores por fuente oficial. Cada adaptador debe producir el mismo contrato normalizado y nunca escribir directamente en las tablas: todo pasa por `ingest_normalized_report()`.
