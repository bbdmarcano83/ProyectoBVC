# Auditoría de fuentes fundamentales V5

Objetivo: usar únicamente información fundamental trazable para la filosofía Caracas Bull V5.

## Regla de fuente
1. Portal oficial del emisor / Relaciones con Inversionistas.
2. BVC, SUNAVAL, SUDEBAN u otro regulador oficial.
3. Espejos/terceros sólo para descubrir documentos; nunca para confirmar una señal V5 sin validar el original.

## Fuentes primarias verificadas
| Ticker | Emisor | Modelo | Fuente primaria | Cobertura observada |
|---|---|---|---|---|
| MVZ.A / MVZ.B | Mercantil Servicios Financieros | Financiera | msf.com | Auditados anuales/semestrales, trimestrales 2026, balances |
| BNC | Banco Nacional de Crédito | Financiera | bncenlinea.com | Informes anuales; 2025 disponible |
| BPV | Banco Provincial | Financiera | provincial.com | Informes semestrales y auditados; 2S-2025 verificado |
| BVL | Banco de Venezuela | Financiera | bancodevenezuela.com | Balances, auditados, gestión, dividendos |
| ABC.A | Bancaribe | Financiera | bancaribe.com.ve/cifras-e-informes | Balances mensuales, memoria semestral, auditor externo |
| SVS | Sivensa | No financiera | sivensa.com.ve/inversionistas | Auditados anuales y trimestrales |
| ENV | Envases Venezolanos | No financiera | envasesvenezolanos.com.ve/estados-financieros | Estados e informes históricos |
| CRM.A | Corimon | No financiera | corimon.com | Estados consolidados y comisarios |
| DOM | Domínguez & Cía. | No financiera | domcia.com/informacion-financiera | Información financiera y asambleas |
| PIV.A / PIV.B | PIVCA | No financiera | pivca.com/prospectos | EEFF auditados y prospectos |

## Ruta oficial/manual verificada, pendiente URL documental estable
- BVCC: documentos financieros y materiales de asamblea publicados por la propia BVC.
- MPA (MANPA): EEFF auditados disponibles vía divulgaciones del mercado/BVC; falta ruta estable del emisor.
- RST / RST.B: existen EEFF auditados recientes, pero falta URL oficial estable del emisor para automatizar.
- TDV.D (CANTV): estados y materiales de asamblea existen en divulgaciones de mercado; falta ruta oficial estable para collector.

## Diseño fail-closed
- Si un ticker no está en `services/fundamental_sources_v5.py`, queda `unmapped`.
- Si la fuente existe pero los campos fundamentales no están extraídos y validados, V5 muestra `TÉCNICO V3 · SIN FUNDAMENTALES`.
- La cobertura de fuentes se calcula contra toda la pizarra BVC que llegue en vivo; no contra una lista fija de acciones.
- Bancos usan ruta financiera (ROE/ROA/P-B/P-E), no EBIT/EV.
- No financieras pueden usar Greenblatt (ROC + earnings yield), Graham y Buffett cuando los estados soporten los campos necesarios.

## Próxima fase del collector
1. Descubrir documentos nuevos por emisor.
2. Guardar URL, período, fecha de publicación, auditor/regulador y hash del documento.
3. Extraer datos a un snapshot normalizado.
4. Validar balance (`activo = pasivo + patrimonio` dentro de tolerancia) y coherencia temporal.
5. Sólo entonces publicar el snapshot a `FUNDAMENTALS_V5_JSON/PATH` o, posteriormente, Neon.
