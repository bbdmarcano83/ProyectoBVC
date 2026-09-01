# Auditoría de fuentes fundamentales V5

Objetivo: usar únicamente información fundamental trazable para la filosofía Caracas Bull V5.

## Regla de fuente
1. Portal oficial del emisor / Relaciones con Inversionistas.
2. BVC, SUNAVAL, SUDEBAN u otro regulador oficial.
3. Espejos/terceros sólo para descubrir documentos; nunca para confirmar una señal V5 sin validar el original.

## Universo
El scoring consume toda la pizarra BVC que llega en vivo. La auditoría de fuentes, por tanto, no se limita al IBC. Una captura pública reciente de la pizarra incluye, entre otros: BPV, TPG, BVCC, TDV.D, RST.B, BNC, PGR, PIV.B, MPA, PCP.B, EFE, RST, FNV, ENV, IVC.B, CCP.B, GZL, ICP.B, SVS, BVL, MVZ.B, PTN, CRM.A, FNC, DOM, CGQ, MTC.B, ABC.A, IVC.A, MVZ.A, CCR, GMC.B y ARC.B.

## Fuentes primarias verificadas
| Ticker | Emisor | Modelo | Fuente primaria | Cobertura observada |
|---|---|---|---|---|
| MVZ.A / MVZ.B | Mercantil Servicios Financieros | Financiera | msf.com | Auditados anuales/semestrales, trimestrales, balances |
| BNC | Banco Nacional de Crédito | Financiera | bncenlinea.com | Informes anuales |
| BPV | Banco Provincial | Financiera | provincial.com | Informes semestrales y auditados |
| BVL | Banco de Venezuela | Financiera | bancodevenezuela.com | Balances, auditados, gestión, dividendos |
| ABC.A | Bancaribe | Financiera | bancaribe.com.ve | Balances mensuales, memoria semestral, auditor externo |
| GZL | Grupo Zuliano | No financiera | grupozuliano.com.ve | Auditados históricos, incluyendo 2026 |
| IVC.A / IVC.B | INVACA | No financiera | invaca.com.ve | Investor Hub, consolidados y reportes |
| TPG | Telares de Palo Grande | No financiera | telaresdepalogrande.com | Auditados históricos e informes a accionistas |
| CGQ | Corporación Grupo Químico | No financiera | grupoquimico.com | Informes de gestión financiera y asambleas |
| ARC.A / ARC.B | ARCA Inmuebles y Valores | No financiera | arcainmueblesyvalores.com | EEFF auditados |
| SVS | Sivensa | No financiera | sivensa.com.ve | Auditados anuales y trimestrales |
| ENV | Envases Venezolanos | No financiera | envasesvenezolanos.com.ve | Estados financieros |
| CRM.A | Corimon | No financiera | corimon.com | Estados consolidados y comisarios |
| DOM | Domínguez & Cía. | No financiera | domcia.com | Información financiera y asambleas |
| PIV.A / PIV.B | PIVCA | No financiera | pivca.com | EEFF auditados y prospectos |
| EFE | Productos EFE | No financiera | empresaspolar.com + divulgaciones oficiales | Asambleas refieren EEFF consolidados auditados; ruta documental estable pendiente |
| ICP.B | Inversiones CrecePymes | Vehículo | crecepymes.com | Informes, auditorías, comisarios y prospecto |
| PER | PC-IBC | Vehículo | per-capital.com | NAV/VUI, rendimiento, posiciones, riesgo y documentos |
| MTC.B | Montesco Fondo Agroindustrial | Vehículo | montescoagro.com | Información del fondo, auditados/divulgaciones |
| CCP.B | Clabe Capital | Vehículo | clabecapital.com | Fondo autorizado SUNAVAL y listado BVC |
| PCP.B | Fondo Petrolia | Vehículo | fondopetrolia.com | Fondo/vehículo del sector hidrocarburos listado como PCP.B |

## Fuente BVC oficial como fallback, pendiente ruta estable del emisor
- BVCC: documentos financieros y materiales de asamblea publicados por la BVC.
- MPA (MANPA): EEFF auditados vía divulgaciones del mercado/BVC.
- RST / RST.B: EEFF auditados recientes; falta ruta oficial estable del emisor.
- TDV.D (CANTV): estados/materiales de asamblea en divulgaciones de mercado.
- PGR (Proagro) y PTN (Protinal): información financiera/asambleas en divulgaciones de mercado.
- FNV (C.A. Fábrica Nacional de Vidrio) y FNC (C.A. Fábrica Nacional de Cementos): cotizan actualmente; collector debe usar BVC/regulador hasta encontrar ruta documental estable del emisor.
- GMC.B (Grupo Mantra Corp): prospecto y hechos de interés disponibles; falta portal estable de estados financieros.
- CCR (Cerámica Carabobo): portal oficial identificado y prospectos históricos; la ruta estable de EEFF debe validarse antes de ingestión automática.

## Diseño fail-closed
- Si un ticker no está en `services/fundamental_sources_v5.py`, queda `unmapped`.
- Si la fuente existe pero no hay snapshot validado, V5 muestra `TÉCNICO V3 · SIN FUNDAMENTALES`.
- La cobertura de fuentes se calcula contra toda la pizarra BVC en vivo.
- Bancos usan ruta financiera; no EBIT/EV.
- Empresas operativas usan Greenblatt/Graham/Buffett sólo cuando los campos están soportados por estados reales.
- Vehículos/fondos usan NAV/patrimonio, descuento/prima, rentabilidad, distribuciones y consistencia; no se les fuerza Greenblatt operativo.

## Persistencia en Neon
`fundamental_documents` conserva trazabilidad documental (URL, tipo, período, auditado, confianza, hash). `fundamental_snapshots` conserva el snapshot normalizado y su score de validación. Sólo `validated=true` puede alimentar V5.

El pipeline es:
1. descubrir documento en una fuente registrada;
2. extraer únicamente campos explícitos;
3. validar tipos y coherencia mínima;
4. comprobar, cuando sea posible, `activo ≈ pasivo + patrimonio`;
5. guardar documento y snapshot de forma idempotente;
6. cargar en V5 únicamente el último snapshot validado por símbolo.

## Pendiente antes de producción V5
- Automatizar descubrimiento/descarga por emisor sin depender de scraping frágil.
- Construir extractores por formato (HTML/PDF) y revisar manualmente las primeras cargas.
- Completar series históricas para que Buffett/Graham midan consistencia, no sólo último período.
- Backtestear los nuevos scores antes de activar `SCORING_ENGINE_V5_ENABLED=true`.
