# Decisiones de método — revisión del capítulo ISABEL

Registro de decisiones metodológicas. Cada cambio posterior se añade como nueva entrada con fecha; no se borran entradas anteriores.

## 2026-11-11 — Decisiones 1 a 4 (adoptadas por Ricardo; pendientes de confirmar con Fernando)

### D1. Estrategia de corpus: vía intermedia
- **Base**: los registros de la exportación Scopus de mayo de 2025 (`data/raw/isabel_chapter_2025/Final_Fernando_3.1.csv`, 235 registros), importados como `manual_import`. Se re-criban con criterios explícitos.
- **Búsquedas suplementarias documentadas** solo para RQ4 (educación/formación) y RQ5 (inmigración/movilidad laboral), en OpenAlex (`search.title_and_abstract`), con cadena, fecha y recuento total registrados. Se declaran en PRISMA como "records identified through supplementary searches".
- Scopus API: pendiente (VPN no disponible). Si se consigue, se repiten las suplementarias también en Scopus.
- La cadena de búsqueda original de Scopus (2025) no está archivada; intentar recuperarla del historial de la cuenta. Si no aparece, se declara.

### D2. Ámbito geográfico
- Incluye: UE-27, Reino Unido y AELC/EFTA (Islandia, Liechtenstein, Noruega, Suiza).
- Estudios multipaís o globales: solo si reportan resultados específicos para esos países o para la UE.
- Excluye: estudios exclusivamente sobre otros contextos (p. ej., China, India, Perú, Rusia, EE. UU., Balcanes Occidentales sin marco UE explícito).

### D3. Contenido mínimo para la inclusión (cribado por título y resumen)
- Obligatorio: **dimensión laboral** (empleo, puestos de trabajo, creación/destrucción de empleo, competencias, mercado laboral o movilidad laboral).
- Obligatorio: **vínculo con la transición verde o digital** (descarbonización, transición energética, política climática, transición justa; digitalización, automatización, IA, TIC, Industria 4.0).
- **No** se exige que el resumen contenga recomendaciones de política: se comprueba en la fase de extracción.
- Periodo 2013–2025; idiomas inglés y español; artículos y revisiones revisados por pares.

### D4. Preguntas de investigación y asignación
- **RQ3 reformulada** (cambio declarado en el capítulo):
  - Original: "What cohesion or smart-specialisation policies does the evidence suggest?"
  - Nueva: "What cohesion or smart-specialisation policies does the evidence suggest to address job creation and destruction linked to the green and digital transition in EU regions?"
- El resto de RQs se mantienen literalmente.
- **Asignación múltiple**: un artículo puede responder a varias RQs. Se informa del solapamiento.

## Pendientes (D5–D8)
- D5. Base de extracción: resumen vs. texto completo OA (propuesta: cribar con resumen; extraer de texto completo si es OA y declararlo).
- D6. Quién hace la validación humana a ciegas (dos personas, ~150–200 registros).
- D7. Lista de 20–40 DOIs imprescindibles (`known_items`).
- D8. Relación entre los seis bloques de política y las siete RQs; separación entre hallazgos de la revisión y lectura amplia de los autores.
