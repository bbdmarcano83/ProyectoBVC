# Política FX histórica — Caracas Bull V5

## Objetivo
En Venezuela no se comparan estados financieros de períodos distintos usando únicamente bolívares nominales. Caracas Bull conserva la cifra reportada y construye una vista USD trazable para análisis intertemporal.

## Jerarquía de fuente
1. BCV oficial, cuando exista una ruta histórica estable y automatizable.
2. Proveedor derivado que identifique explícitamente BCV como fuente de la tasa oficial.
3. Tasa BCV incluida explícitamente en un estado/informe oficial del emisor, sólo para el período que el documento soporte.

La implementación inicial usa el histórico de dólar oficial de DolarAPI (`https://ve.dolarapi.com/v1/historicos/dolares/oficial`). Su documentación declara BCV como fuente. Se registra como `bcv_derived_api`, no como portal oficial del BCV.

## Regla por tipo de cifra
### Estado de situación / balance
Activos, pasivos, patrimonio, caja, deuda, capitalización, NAV y valores por acción a fecha de corte usan la **tasa BCV de cierre** correspondiente al `as_of`.

Si la fecha cae en fin de semana o feriado, se usa la última tasa publicada anterior o igual a la fecha. Nunca una tasa posterior.

### Resultados y flujos — estados nominales
Ingresos, EBIT, utilidad, flujo operativo, FCF, CAPEX y distribuciones del período usan la **tasa BCV promedio del período**.

El promedio es calendario con forward-fill de la última tasa publicada. Esto evita sesgar el promedio al excluir fines de semana y feriados.

### Estados en moneda constante de cierre
Cuando el documento declara que las cifras están reexpresadas en bolívares constantes de la fecha de cierre (`constant_ves_end_period`), se usa la tasa de cierre para las partidas monetarias reexpresadas.

### Estados reportados en USD
No se reconvierten. Se marcan como `usd_reported`.

## Fail-closed
- Nunca se usa la tasa actual para convertir un estado histórico.
- Si falta tasa de cierre, no se construye la vista USD.
- Si el estado nominal requiere tasa promedio y ésta no puede calcularse, el snapshot no pasa el gate FX de producción.
- Un V5 con `fx_valid_v5=False` no puede emitir `OPORTUNIDAD HÍBRIDA CONFIRMADA`.
- Los datos originales en VES nunca se sobrescriben.

## Persistencia
`services/fx_history_v5.py` mantiene `fx_rates_v5` en la misma base SQLAlchemy/Neon de producción. Cada fila conserva:
- fecha de tasa;
- par `USD/VES`;
- tasa;
- nombre del proveedor;
- URL de origen;
- tipo de fuente;
- confianza;
- fecha de recolección.

La actualización es idempotente por fecha/par.

## Integración con fundamentales
El collector aplica por defecto:

`documento -> normalización de campos -> resolución FX histórica -> vista USD -> validación contable -> persistencia`

Los fixtures de CI pueden desactivar explícitamente la resolución de red para pruebas offline, pero producción usa los defaults `hydrate_fx=True` y `require_fx=True`.

## Series históricas
La siguiente capa debe almacenar series por período ya normalizadas (`earnings_history_usd`, `revenue_history_usd`, `fcf_history_usd`, `nav_history_usd`). Los CAGR y tendencias de Buffett/Graham deben preferir esas series USD sobre series VES nominales.
