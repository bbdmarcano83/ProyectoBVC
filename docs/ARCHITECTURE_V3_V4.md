# ProyectoBVC — V3 Scoring + V4 Portfolio + hardening

## Estado de esta rama
La aplicación está pausada para la migración. `audit/v3-v4-engine` contiene la implementación integrada de V3/V4, manteniendo rollback a V2/V3 legacy mediante flags. `main` no se modifica hasta merge.

## Restricción real de infraestructura
ProyectoBVC no tiene hoy una base de datos persistente conectada. En ausencia de `DATABASE_URL`, el runtime crea deliberadamente SQLite en `/tmp/caracasbull.db`, que es EFÍMERA.

Por tanto:
- la DB local no es fuente persistente de verdad;
- `caracasbull.db`, `portafolio.json` y `config.json` fueron retirados del branch;
- V3/V4 funcionan stateless;
- los históricos analíticos se reconstruyen desde datos BVC en cada corrida;
- score history persistente sólo podrá existir cuando haya storage externo real.

## V3 Scoring Engine — implementado
Runtime: `services/scoring.py` → `services/scoring_engine_v3.py` → `services/scoring_postprocess.py`.
Legacy preservado en `services/scoring_v2.py`.

Incluye:
1. Data Quality y `Confidence Score` separado.
2. Percentiles cross-sectional de retorno, liquidez y momentum.
3. Momentum 5/20/60 ruedas y aceleración.
4. Volatilidad anualizada, downside volatility y max drawdown 60d.
5. Frecuencia de negociación 60d y concentración de volumen.
6. Confirmación precio/actividad y expansión reciente de volumen.
7. `Strength Score` separado.
8. `Opportunity Score` separado.
9. `Risk Score` separado (100 = mayor riesgo).
10. Zona de pullback controlado -8% a -20%.
11. Estados `OBSERVAR`, `PREPARAR COMPRA`, `OPORTUNIDAD CONFIRMADA`.
12. Market Breadth y régimen `RISK-ON / NEUTRAL / DEFENSIVO / ESTRES`.
13. Pesos del score final adaptados al régimen.
14. Fuerza/ranking sectorial sobre la clasificación disponible de BVC.
15. Eventos corporativos opcionales mediante `CORPORATE_EVENTS_JSON`; un evento con `blocking=true` bloquea señales.
16. Explicabilidad (`explain_v3`) y quality flags.
17. Compatibilidad con campos legacy que todavía consume `main.py`.
18. UI V3 en `templates/scoring.html`.

Rollback inmediato:
`SCORING_ENGINE_V3_ENABLED=false`

## Backtesting / walk-forward — implementado stateless
Archivo: `services/backtest_v3.py`.

- reconstruye métricas desde históricos BVC disponibles;
- calcula forward returns 5/20/60 ruedas;
- hit rate y retorno medio por horizonte;
- proxy reproducible para calibración histórica sin depender de snapshots locales;
- walk-forward cronológico 60/20/20 (train/validation/test);
- no escribe DB.

Limitación intencional: sin snapshots históricos cross-sectional persistidos, el backtest no puede reconstruir con exactitud matemática todos los percentiles de mercado V3 de una fecha antigua. El proxy histórico se identifica explícitamente como tal; no se presenta como backtest exacto del score cross-sectional.

## V4 Portfolio Engine — implementado
Runtime: `services/portafolio.py` → `services/portfolio_v4.py`.
Legacy preservado en `services/portafolio_legacy.py`.

Incluye:
- salud de cartera 0–100;
- concentración máxima y top-3;
- HHI;
- score/confidence/risk ponderados si existe scoring V3 de la corrida;
- capital en score débil;
- capital en alerta;
- ganadores/perdedores;
- candidatos de toma de ganancia (+50% inicial compatible);
- candidatos de revisión;
- modelo de fees de rotación: corretaje + IVA + registro + ISLR;
- `evaluar_rotacion_v4()` exige una ventaja bruta proveniente de modelo/backtest y descuenta la fricción; NO convierte delta de score en retorno esperado;
- UI V4 en `templates/portafolio.html`.

Rollback inmediato:
`PORTFOLIO_ENGINE_V4_ENABLED=false`

## Alertas inteligentes — implementadas
`services/alertas_cierre.py` consume el motor runtime activo.

Incluye:
- régimen/breadth;
- top/bottom score;
- confidence/risk;
- `PREPARAR COMPRA` y oportunidades confirmadas;
- revisión de cartera por toma de ganancia, liquidez deteriorada, score bajo, risk alto o confidence bajo.

## Seguridad — implementada
### JWT/Auth
- no existe secret público hardcodeado compartido;
- en Render se detecta automáticamente producción;
- `SECRET_KEY` en producción es obligatorio y debe tener >=32 caracteres;
- JWT incluye issuer, iat y exp;
- usuarios inactivos no autentican;
- contraseña nueva mínima 8 caracteres.

### HTTP/runtime
`services/security_runtime.py`:
- rate limit local/efímero por IP;
- same-origin protection para operaciones con sesión;
- `HttpOnly`/`SameSite` existentes + `Secure` añadido en producción;
- HSTS en producción;
- X-Content-Type-Options, X-Frame-Options, Referrer-Policy y Permissions-Policy;
- audit log mínimo de APIs/login sin cuerpo ni secretos.

### Endpoint de alertas
`services/secret_guard.py` hace fail-closed `/api/alertas-cierre`:
- requiere `ALERTA_SECRET` >=24 caracteres;
- usa comparación constante;
- sin secret: 503;
- secret incorrecto: 401.

### Pagos
`services/pagos.py`:
- `NOWPAYMENTS_IPN_SECRET` obligatorio para validar IPN;
- sin secret/firma: rechazo;
- HMAC-SHA512 + compare_digest;
- validación estricta de `order_id`/plan;
- idempotencia básica de reintentos;
- sólo `finished/confirmed` activa suscripción;
- no se imprimen API keys ni payloads sensibles.

## DB efímera — esquema limpio
`database.py`:
- usa `DATABASE_URL` externa si algún día se configura;
- si no, `/tmp/caracasbull.db` y `DB_PERSISTENCE_MODE=ephemeral`;
- foreign keys activadas en SQLite;
- unicidad usuario+símbolo en portafolio/watchlist;
- constraints básicos de cantidades, precios, planes, transacciones y alertas;
- índices operativos.

No se implementa Alembic todavía porque no existe una DB persistente que migrar. Cuando exista PostgreSQL/otro storage externo, Alembic debe ser requisito antes de cambios de esquema.

## CI / validación
`.github/workflows/engine-contract-tests.yml` valida:
- instalación de dependencias;
- `py_compile` del stack V3/V4/seguridad/pagos/DB;
- parseo de templates Jinja V3/V4;
- creación limpia del esquema SQLite efímero;
- tests unitarios/contrato;
- pagos fail-closed.

## Variables requeridas antes de arrancar en Render
Obligatorias para producción:
- `SECRET_KEY` (>=32 caracteres)
- `ALERTA_SECRET` (>=24 caracteres) si se usa alertas-cierre
- `NOWPAYMENTS_API_KEY` si se habilitan pagos
- `NOWPAYMENTS_IPN_SECRET` (>=24 caracteres) si se habilitan pagos
- `APP_URL` para callbacks de pago

Opcionales:
- `SCORING_ENGINE_V3_ENABLED=true|false` (default en esta rama: true)
- `PORTFOLIO_ENGINE_V4_ENABLED=true|false` (default en esta rama: true)
- `CORPORATE_EVENTS_JSON` para bloquear/etiquetar eventos corporativos
- `DATABASE_URL` sólo si en el futuro se conecta storage persistente real

## Lo que deliberadamente NO se finge
- No hay score history persistente mientras la DB sea efímera.
- No hay backtest cross-sectional exacto de fechas antiguas sin snapshots históricos de todo el universo.
- No se inventan fundamentales BVC donde no existe una fuente fiable integrada.
- No se infiere retorno esperado a partir de una diferencia de score.

## Rollback
V3: `SCORING_ENGINE_V3_ENABLED=false`.
V4: `PORTFOLIO_ENGINE_V4_ENABLED=false`.
Los motores legacy permanecen versionados en la misma rama para rollback rápido.
