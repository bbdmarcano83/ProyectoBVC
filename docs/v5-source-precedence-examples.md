# Ejemplos de precedencia de fundamentales V5

- Emisor/BVC/SUNAVAL disponible: se usa nivel A; cualquier cifra secundaria discordante no reemplaza el valor certificado.
- Solo fuente secundaria trazable disponible: puede alimentar el fundamental como nivel B con menor confianza.
- Dos fuentes secundarias con cifras incompatibles: ese dato fundamental queda pendiente; el activo sigue siendo evaluable sin ese componente.
- Documento oficial con OCR, unidad, contabilidad o FX pendiente: el fundamental correspondiente no se usa hasta resolver el problema; el activo permanece evaluable.
- Empresa nueva sin estados publicados: `fundamental_score_v5` puede ser `None`, pero `philosophy_score_v5` se calcula renormalizando los demás pilares.
