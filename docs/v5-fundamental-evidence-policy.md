# Política V5 de evidencia fundamental

## Principio operativo

Un activo válido del universo BVC no deja de ser evaluable porque falten estados financieros, exista un error de OCR/parser/FX o no haya historia suficiente. El fallo cerrado aplica al dato fundamental, no al activo.

## Jerarquía de evidencia

- **A_CERTIFIED**: documento publicado o certificado por el emisor registrado, la Bolsa de Valores de Caracas (BVC) o SUNAVAL. Confianza de evidencia: 100.
- **B_SECONDARY**: fuente secundaria HTTPS trazable para un emisor registrado. Puede alimentar el fundamental con menor confianza y menor peso en el score.
- **NONE**: no existe fundamental utilizable. El activo sigue siendo evaluable con los pilares de mercado, oportunidad, confianza y riesgo.

## Precedencia

1. Si existe evidencia A, prevalece sobre B.
2. Si dos autoridades A discrepan materialmente, el fundamental falla cerrado hasta reconciliación.
3. Si solo existe evidencia B y las fuentes secundarias discrepan, el fundamental falla cerrado hasta reconciliación.
4. Un fallo del fundamental nunca convierte por sí solo al activo en no evaluable.

## Scoring

El `philosophy_score_v5` se renormaliza sobre los pilares disponibles. Un fundamental ausente no recibe cero. La evidencia B reduce el peso efectivo del fundamental mediante su nivel de confianza; la evidencia A conserva el peso completo.

## Trazabilidad

Cada snapshot persistido conserva tier, confianza, ruta de procedencia y si la fuente fue certificada. La normalización histórica VES/USD continúa requiriendo FX BCV histórico cuando corresponda; nunca se usa la tasa actual para estados históricos.
