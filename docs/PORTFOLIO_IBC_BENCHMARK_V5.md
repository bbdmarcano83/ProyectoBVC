# Portafolio vs IBC · Benchmark V5

## Objetivo

Comparar el rendimiento económico del portafolio abierto contra el Índice Bursátil Caracas (IBC) usando las mismas fechas de entrada y los mismos flujos, sin atribuir aportes/retiros a rentabilidad y sin inventar tasas BCV históricas.

## Feature flag

El benchmark es opt-in y permanece apagado por defecto:

```text
PORTFOLIO_IBC_BENCHMARK_V5_ENABLED=false
```

Con el flag apagado `/api/v5/portfolio-benchmark` no se registra. El handler y el router de compatibilidad también vuelven a validar el flag para impedir accesos laterales y evitar generación silenciosa de snapshots.

## Benchmark de posiciones abiertas

El motor `services/portfolio_benchmark_v5.py` reconstruye lotes FIFO desde la bitácora del usuario. Cada lote remanente crea una inversión IBC sintética con el mismo capital y la fecha de adquisición del lote.

Para un lote:

```text
IBC_terminal_Bs = costo_lote_Bs × IBC_actual / IBC_entrada
```

La comparación agregada en bolívares utiliza exclusivamente capital con fecha de entrada e IBC reconciliables. Una posición no reconciliable no entra en el numerador ni en el denominador del alpha; sí entra en el denominador de cobertura para que la UI muestre cuánto capital realmente está siendo comparado.

## USD / BCV histórico

La comparación USD es fail-closed. Para cada lote se exige una tasa histórica válida proveniente de `fx_rates_v5`; no se usa como fallback automático la `tasa_bcv` legacy guardada en transacciones antiguas porque esa columna pudo haberse registrado con la tasa vigente al momento de cargar manualmente una operación histórica.

La cobertura USD se calcula por lote. Por tanto, una cartera puede tener benchmark Bs al 100% y USD sólo sobre una fracción del capital. La parte sin FX histórico se informa como cobertura faltante y no se aproxima.

## Ventanas 1M / 3M / 6M / YTD / 1Y

`services/portfolio_performance_v5.py` usa Modified Dietz para corregir compras y ventas dentro de cada ventana. El benchmark IBC recibe los mismos flujos en las mismas fechas.

Una ventana sólo se habilita si existe un snapshot en o antes de la fecha de inicio requerida. No se permite etiquetar como `YTD` o `1Y` una serie que comenzó después del inicio real de la ventana.

## Snapshots diarios

Los snapshots no se guardan simplemente al abrir la página. `snapshot_capture_policy()` exige:

1. mercado cerrado;
2. cierre IBC auditado disponible;
3. fecha del IBC igual a la fecha de valoración de la cartera.

Sólo entonces se persiste un snapshot con `source=market_close_aligned`. Si el mercado está abierto o el IBC todavía corresponde a una fecha anterior, el endpoint devuelve el benchmark abierto pero no persiste el snapshot temporal.

## Estado provisional en UI

El endpoint expone:

```text
valuation_as_of
ibc_as_of
terminal_dates_aligned
```

Si `terminal_dates_aligned=true`, la UI muestra `Cierre comparable`.

Si es `false`, los valores abiertos pueden seguir mostrándose como referencia, pero la UI marca claramente:

```text
PROVISIONAL · cartera <fecha> / IBC <fecha>
```

y añade la advertencia de que el alpha no corresponde a un cierre terminal perfectamente comparable.

## Fuente IBC

`services/ibc_history_v5.py` prioriza la historia IBC persistida y auditada en Neon. JSON/path sólo se usan como mecanismo de fallback/importación cuando el store persistente está vacío. Los puntos sin confianza suficiente quedan fuera del benchmark.

## Flujo oficial

```text
portafolio.html
    ↓
/api/v5/portfolio-benchmark
    ↓
v5_routes.py
    ↓
portfolio_benchmark_v5.py     (posiciones abiertas / FIFO)
portfolio_performance_v5.py   (ventanas / Modified Dietz)
portfolio_snapshot_v5.py      (cierres diarios alineados)
    ↓
IBC persistido + FX histórico
```

No existe un segundo adaptador runtime paralelo. El objetivo es mantener una sola implementación del benchmark visible para evitar divergencias futuras.

## Criterio para activación

Antes de cambiar el flag a `true` en producción deben verificarse conjuntamente:

- CI de la rama completamente verde;
- historial IBC persistido con cobertura suficiente para las fechas reales de las posiciones;
- FX histórico suficiente para el nivel de cobertura USD esperado;
- ninguna ventana temporal presentada sin snapshot anterior o igual a su fecha inicial;
- UI mostrando `PROVISIONAL` cuando cartera e IBC estén desalineados;
- V5 scoring sigue siendo independiente de este flag y permanece sujeto a su propio gate.
