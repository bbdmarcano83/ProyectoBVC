# ProyectoBVC — Evolución V3/V4 sin romper producción

## Objetivo
Separar cálculo, política y presentación para evolucionar el scoring y el portafolio sin alterar contratos existentes ni obligar migraciones de datos.

## Restricción de infraestructura actual
La aplicación NO dispone hoy de una base de datos persistente conectada en producción. El almacenamiento local usado por Render es efímero: puede perderse en reinicios, redeploys o recreaciones de instancia.

Consecuencias:
- No usar SQLite local como fuente persistente de verdad para historial V3/V4.
- No guardar snapshots históricos de score en `caracasbull.db` esperando conservarlos entre deploys.
- No usar `portafolio.json`, `config.json` ni otros archivos locales como almacenamiento persistente nuevo.
- V3/V4 deben funcionar de forma stateless mientras no exista un storage externo persistente.
- Cualquier futura persistencia histórica debe quedar detrás de una interfaz desacoplada y activarse sólo cuando exista un backend persistente real.

## Principios de rollout
1. `main` permanece estable hasta que cada motor pase pruebas de contrato.
2. Los motores nuevos son opt-in mediante variables de entorno.
3. Ningún cambio V3/V4 elimina o renombra campos legacy en su primera etapa.
4. No introducir dependencias de persistencia local efímera.
5. Los cambios se integran por PR pequeño y reversible.

## Fase 0 — Seguridad y baseline
- Centralizar feature flags.
- Ampliar `.gitignore` para secretos, DB locales, JSON de runtime y caches.
- No borrar todavía archivos ya versionados hasta definir respaldo/migración.
- Eliminar fallbacks de secretos únicamente cuando las variables de producción estén confirmadas.

Riesgos detectados en baseline:
- `caracasbull.db` está versionada en el repositorio, pero NO representa una DB persistente conectada en producción.
- `portafolio.json` y `config.json` están versionados y tampoco deben considerarse almacenamiento persistente.
- `services/auth.py` contiene un `SECRET_KEY` de desarrollo como fallback.
- `/api/alertas-cierre` contiene una clave fallback en `main.py`.
- La migración ad-hoc de `main.py` silencia cualquier excepción y no distingue "columna ya existe" de errores reales.

## Fase 1 — V3 Scoring Engine
Archivo: `services/scoring_v3.py`

Primera entrega compatible/stateless:
- Conserva todos los campos legacy del V2.
- Separa `Confidence`, `Strength`, `Opportunity` y `Risk`.
- Añade percentiles cross-sectional sobre el snapshot actual.
- Añade quality gates y flags explícitos.
- Añade estados `OBSERVAR`, `PREPARAR COMPRA` y `OPORTUNIDAD CONFIRMADA`.
- Añade comparador V2 vs V3 para shadow mode.
- Consume exactamente el mismo snapshot ya calculado por V2; no hace I/O adicional ni requiere DB.

Activación futura:
- `SCORING_ENGINE_V3_SHADOW=true` para comparación interna.
- `SCORING_ENGINE_V3_ENABLED=true` para salida visible V3.

## Fase 2 — V4 Portfolio Engine
Archivo: `services/portfolio_v4.py`

Primera entrega compatible/stateless:
- No escribe ni modifica posiciones.
- Analiza filas ya calculadas por `services.portafolio`.
- Añade concentración máxima, top-3, HHI y salud de cartera.
- Añade score/confidence/risk ponderados cuando recibe scoring V3.
- Añade capital en posiciones débiles y capital en alerta.
- Añade candidatos de toma de ganancia y revisión.
- Modela fricción de rotación con corretaje, IVA, registro e ISLR.
- No requiere persistencia adicional.

Activación futura:
- `PORTFOLIO_ENGINE_V4_SHADOW=true`.
- `PORTFOLIO_ENGINE_V4_ENABLED=true`.

## Fase 3 — Integración controlada
- Usar `services/engine_router.py` para seleccionar legacy/shadow/enabled fuera de FastAPI.
- Integrar V3/V4 en `main.py` sólo después de tests de contrato.
- En shadow mode, mantener V2 visible y calcular V3/V4 sólo para observabilidad.
- Exponer versión de engine en metadata/API.
- Añadir fixtures anonimizadas para pruebas reproducibles.

## Fase 4 — Métricas históricas sin DB persistente
Mientras no exista storage persistente:
- Calcular momentum multi-horizonte, drawdown y volatilidad directamente desde el histórico de mercado disponible en cada corrida.
- Mantener estas métricas como cálculo stateless.
- No prometer persistencia de score histórico entre deploys.
- El backtest debe reconstruirse desde históricos de mercado disponibles, no desde SQLite efímero.

## Fase 5 — Persistencia opcional futura
Sólo cuando exista un backend persistente real (PostgreSQL gestionado u otro storage externo):
- Introducir una interfaz `SnapshotStore` desacoplada del motor.
- Implementar persistencia de snapshots de score, señales y métricas.
- Añadir migraciones versionadas.
- Habilitar score history, alertas por pendiente y análisis longitudinal.

La aplicación debe seguir funcionando si `SnapshotStore` no está configurado.

## Seguridad/arquitectura posterior
Después de confirmar variables de entorno en producción:
- Hacer obligatorio `SECRET_KEY` seguro en producción.
- Hacer obligatorio `ALERTA_SECRET` y comparar con `secrets.compare_digest`.
- Marcar cookie `Secure` en HTTPS y conservar `HttpOnly`/`SameSite`.
- Añadir headers de seguridad.
- Sustituir migraciones ad-hoc por migraciones versionadas cuando exista una DB persistente real.
- Retirar DB/JSON runtime del historial activo del repo tras respaldo seguro.

## Rollback
Cada fase es reversible desactivando el flag correspondiente. V3/V4 no deben depender de almacenamiento persistente para operar en su modo actual.
