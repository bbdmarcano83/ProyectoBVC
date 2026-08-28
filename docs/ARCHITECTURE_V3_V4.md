# ProyectoBVC — Evolución V3/V4 sin romper producción

## Objetivo
Separar cálculo, política y presentación para evolucionar el scoring y el portafolio sin alterar contratos existentes ni obligar migraciones de datos.

## Principios de rollout
1. `main` permanece estable hasta que cada motor pase pruebas de contrato.
2. Los motores nuevos son opt-in mediante variables de entorno.
3. Ningún cambio V3/V4 elimina o renombra campos legacy en su primera etapa.
4. Las migraciones de datos se hacen después de validar lectura compatible.
5. Los cambios se integran por PR pequeño y reversible.

## Fase 0 — Seguridad y baseline
- Centralizar feature flags.
- Ampliar `.gitignore` para secretos, DB locales, JSON de runtime y caches.
- No borrar todavía archivos ya versionados hasta definir respaldo/migración.
- Eliminar fallbacks de secretos únicamente cuando las variables de producción estén confirmadas.

Riesgos detectados en baseline:
- `caracasbull.db` está versionada en el repositorio.
- `portafolio.json` y `config.json` están versionados aunque la app actual ya usa SQLAlchemy para portafolios por usuario.
- `services/auth.py` contiene un `SECRET_KEY` de desarrollo como fallback.
- `/api/alertas-cierre` contiene una clave fallback en `main.py`.
- La migración ad-hoc de `main.py` silencia cualquier excepción y no distingue "columna ya existe" de errores reales.

## Fase 1 — V3 Scoring Engine
Archivo: `services/scoring_v3.py`

Primera entrega compatible:
- Conserva `(resultados, devaluacion, metadata)`.
- Conserva todos los campos legacy.
- Añade `score_v3`, `score_class_v3`, `quality_flags_v3`, `data_quality_ok_v3` y `engine_version`.
- Añade quality gates para impedir señales cuando faltan precio, fecha, histórico mínimo o liquidez.
- Mantiene inicialmente los umbrales operativos existentes: score mínimo 65, liquidez 15 y caída -15%.

Activación futura:
`SCORING_ENGINE_V3_ENABLED=true`

Antes de activar en producción se debe comparar V2 vs V3 con un snapshot real y exigir igualdad en campos legacy.

## Fase 2 — V4 Portfolio Engine
Archivo: `services/portfolio_v4.py`

Primera entrega compatible:
- No escribe ni modifica posiciones.
- Analiza filas ya calculadas por `services.portafolio`.
- Añade concentración máxima, HHI, ganadores/perdedores, candidatos de toma de ganancia y candidatos de revisión.
- Mantiene toma de ganancia en +50% como regla inicial compatible.

Activación futura:
`PORTFOLIO_ENGINE_V4_ENABLED=true`

## Fase 3 — Integración controlada
- Introducir adaptador en `main.py` para seleccionar V2/V3 por feature flag.
- Enriquecer el resumen de `/portafolio` con V4 sin cambiar la plantilla inicialmente.
- Exponer versión de engine en metadata/API para observabilidad.
- Añadir pruebas de snapshot/contrato con fixtures reales anonimizadas.

## Fase 4 — Seguridad/arquitectura
Después de confirmar variables de entorno en producción:
- Hacer obligatorio `SECRET_KEY` seguro en producción.
- Hacer obligatorio `ALERTA_SECRET` y comparar con `secrets.compare_digest`.
- Marcar cookie `Secure` en HTTPS y conservar `HttpOnly`/`SameSite`.
- Añadir headers de seguridad.
- Sustituir migraciones ad-hoc por migraciones versionadas.
- Retirar DB/JSON de runtime del historial activo del repo tras respaldo seguro.
- Añadir restricciones/índices únicos por usuario y símbolo para portafolio/watchlist.

## Rollback
Cada fase es reversible desactivando el flag correspondiente. Hasta completar Fase 3, V3/V4 no alteran el flujo activo de `main`.
