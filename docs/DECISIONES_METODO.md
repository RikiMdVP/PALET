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
- D6. Quién hace la validación humana a ciegas (dos personas, \~150–200 registros).
- D7. Lista de 20–40 DOIs imprescindibles (`known_items`).
- D8. Relación entre los seis bloques de política y las siete RQs; separación entre hallazgos de la revisión y lectura amplia de los autores.

## 2026-11-11 (tarde) — Confirmación de D1–D4 y alcance de la entrega

- **D1–D4 confirmadas por Fernando** (comunicado por Ricardo). El protocolo `config/protocol_isabel_chapter_v1.yaml` pasa a `status: approved` en lo que respecta a preguntas de investigación y criterios. Las cadenas de las búsquedas suplementarias (RQ4 y RQ5) siguen pendientes de definir y aprobar; cada una lleva su propio `status` en el protocolo.
- **Búsquedas suplementarias de RQ4 y RQ5**: se incluyen en esta entrega (OpenAlex, título y resumen), según D1.
- **D6 (validación humana a ciegas): aplazada.** Motivo (Ricardo): el capítulo es una revisión de la literatura, no una presentación de la herramienta; la validación formal (sensibilidad, especificidad, κ) se hará cuando PALET se prepare como herramienta de la tesis. Consecuencia para el capítulo: no se pueden afirmar métricas de fiabilidad; el texto debe describir el procedimiento como asistido por IA con supervisión humana (adjudicación de discrepancias y casos dudosos) y declarar como limitación que no se ha validado formalmente.

## 2026-11-11 (tarde) — Cribado y búsquedas suplementarias

- **Cribadores**: dos modelos distintos, `claude-opus-5-5` (A) y `claude-sonnet-5-5` (B), con el mismo prompt (`prompts/screen_system_v1.txt`). Solo es firme lo que ambos deciden igual; discrepancias, dudas y errores van a adjudicación humana. Configurado en `palet.toml`, sección `[screening]`.
- **Regla de decisión** (en código, `palet/screening.py`): se excluye si falla un criterio de inclusión o se cumple uno de exclusión con cita verificada; se incluye si se cumplen todos los de inclusión con cita verificada y ninguno de exclusión; en cualquier otro caso, dudoso. Los criterios de tipo de documento, idioma y periodo se comprueban con los metadatos, no con el modelo. Los registros sin resumen van a decisión humana.
- **Búsquedas suplementarias RQ4 y RQ5**: bloques de términos en el protocolo, con el bloque geográfico ampliado a los 32 países (UE-27, Reino Unido y AELC). Estado `proposed` hasta que los autores vean los recuentos y las aprueben.
- Se añadió a cada criterio del protocolo su `reason_code` (anotación técnica; no cambia el texto de ningún criterio).

## 2026-11-12 — Búsquedas suplementarias: solo inglés; variantes de RQ4

- **Idioma de las búsquedas suplementarias: solo inglés** (Ricardo). Se aplica a las fuentes OpenAlex del protocolo (`languages: [en]`). Los criterios de elegibilidad del protocolo siguen siendo inglés y español, de modo que los 6 registros en español de la exportación de Scopus siguen siendo elegibles. Esta asimetría debe declararse en el capítulo (o resolverse cambiando D3).
- **Recuentos con filtros (2013–2025, artículo/revisión, inglés o español, título y resumen), consultados el 2026-11-12**: RQ4 = 1.287; RQ4_b (sin "higher education") = 773; RQ4_c (además sin "automation" ni "artificial intelligence") = 668; RQ4_d (formación × competencias × geografía, sin bloque de empleo) = 225; RQ5 = 55. Pendiente repetirlos solo en inglés y elegir una variante de RQ4.

