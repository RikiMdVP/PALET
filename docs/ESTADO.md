# Estado de PALET 2.0 y del capítulo ISABEL

Actualizado: 15-nov-2026. Documento vivo: es lo primero que debe leer quien continúe el trabajo, junto con
`CLAUDE.md` (reglas) y `docs/DECISIONES_METODO.md` (decisiones de método; prevalece). El historial está en
`docs/sesiones/` y en `CHANGELOG.md`.

## 1. Objetivo y plazo

Entregar a los revisores, **antes del 12-dic-2026**, el capítulo de libro del proyecto ISABEL (políticas de creación y
destrucción de empleo ligadas a la doble transición en la UE) revisado, con su carta de respuesta. Autores: Ricardo
Martínez de Vega y Fernando Rubiera-Morollón.

El corpus de 2025 (142 estudios) no cumplía los criterios: solo 2 sobreviven al proceso nuevo. **El capítulo se
reescribe sobre el corpus nuevo** y se declara así. Se conservan introducción, marco, las siete preguntas y la
estructura; se reescriben las secciones de resultados. Ninguna afirmación antigua se sostiene con una referencia
nueva: cada afirmación debe estar respaldada por el estudio que se cita.

## 2. Corpus (ejecución `runs/isabel_chapter_v1`, protocolo `config/protocol_isabel_chapter_v2.yaml`)

| | Registros |
|---|---|
| Identificados (Scopus 2025 + siete búsquedas en OpenAlex) | 2.419 |
| Únicos tras deduplicar | 2.119 |
| Excluidos | 1.747 |
| · revista fuera de SCIE, SSCI y ESCI | 1.064 |
| · criterios, con acuerdo de los dos cribadores | 402 |
| · sin acuerdo entre cribadores | 179 |
| · sin resumen | 88 |
| · otros motivos (decisión de los autores) | 14 |
| Elegibles | 372 (358 por acuerdo, 14 por decisión de los autores sobre 53 pendientes) |
| **Sintetizados: principales para alguna pregunta** | **170** |

Principales por pregunta: RQ1 40 · RQ2 38 · RQ3 5 · RQ4 31 · RQ5 4 · RQ6 57 · RQ7 7 (12 lo son en dos).
Acuerdo entre cribadores: 842/967 (87,1 %), kappa = 0,794. Coste de modelo acumulado ≈ 60 $.

## 3. Método vigente

- Criterios IC1-IC3 / EC1-EC3: los juzga el modelo con cita literal que el código verifica. Tipo de documento,
  idioma, periodo e IC5 (revista en SCIE, SSCI o ESCI, por ISSN) se comprueban con metadatos antes de llamar al modelo.
- Cribadores: `claude-opus-5-5` (A) y `claude-sonnet-5-5` (B). Regla `agreement_or_exclude`: se incluye si ambos
  incluyen; "uno incluye, otro duda" lo deciden los autores; el resto se excluye.
- Asignación a preguntas (principal / parcial / ninguna) con un solo modelo y cita verificada; se sintetizan solo los
  principales (`synthesis_selection: core_only`).
- Descartado para el capítulo: validación frente a cribado humano; criterio a posteriori de "recomendaciones de política".

## 4. Material disponible

- `runs/isabel_chapter_v1/report/`: `prisma_flow.pdf`, `methods_appendix.md`, `prisma_scr_checklist.md`,
  `evidence_by_rq.md` (cada estudio principal con su contribución y citas), `selected_studies.csv`,
  `excluded_records.csv`, figuras, `citation_check.md` (cotejo del manuscrito antiguo).
- `docs/chapter/`: borradores de síntesis por pregunta (`synthesis_RQ1.md` … `RQ7.md`), lectura transversal
  (`cross_reading.md`) y todo ello en Word (`ISABEL_evidence_synthesis.docx`). Escritos a partir de resúmenes:
  **hay que contrastar cada estudio con su texto completo antes de citarlo**.
- Manuscrito anterior y carta de los revisores: `data/raw/isabel_chapter_2025/manuscript/ISABELCHAPTER REV.docx`.

## 5. Lo que queda para el capítulo

1. Decisiones de los autores marcadas **[authors]** en `docs/chapter/cross_reading.md`, y estas tres:
   RQ3, RQ5 y RQ7 con pocos estudios (¿se presenta como laguna o se amplía la búsqueda?); los 88 excluidos sin
   resumen (¿se declara o se recuperan?); confirmación expresa de Fernando del protocolo v2 (añadir su nombre en
   `approved_by`).
2. Reescribir las siete secciones de resultados a partir de las síntesis; ajustar introducción, discusión y
   conclusiones a lo que el corpus sostiene.
3. Sección de método, PRISMA, limitaciones y lista PRISMA-ScR en inglés, desde `methods_appendix.md`. Rehacer la
   Sección 2, la Figura 1 y la tabla de referencias por pregunta.
4. Cotejo de citas sobre el texto nuevo: `python -m palet check-citations --manuscript <docx> --run isabel_chapter_v1`.
5. Carta de respuesta punto por punto. Límite de palabras, formato y envío.

A declarar en el texto (ya decidido): cadena de Scopus 2025 no archivada; búsquedas nuevas solo en OpenAlex y en
inglés; filtro de revistas según indexación de 2025-2026, no de la fecha de publicación; cribado con dos modelos sin
validación humana y regla conservadora; acuerdo entre cribadores (87,1 %, kappa 0,794); clasificación
principal/parcial de un solo modelo; revisión no exhaustiva; todo sobre título, palabras clave y resumen.

## 6. La herramienta

Flujo: preguntas → protocolo → búsqueda → duplicados → revistas → cribado → decisión humana → asignación → informe.

- Terminal: `python -m palet draft-protocol | approve-protocol | init | search | approve-search | dedup | reparse |
  journals | set-protocol | screen | adjudicate | assign | report | check-citations | status`.
- Dashboard: `python -m uvicorn app:app --port 8000` y abrir `/workflow`. Diagrama de pasos animado, salida de cada
  comando, asistente de protocolo en "+ nueva revisión", elección de modelo en asistente, cribado y asignación, y el
  robot PALET. El dashboard antiguo (pipeline 1.0) sigue en `/`.

**Sin probar todavía con ejecuciones reales**: el asistente de protocolo (solo con modelo simulado; falta juzgar la
calidad de sus sugerencias) y los botones del dashboard contra el modelo real.

Pendiente técnico, sin fecha: generalizar el prompt de asignación (hoy menciona empleo y transición) y los motivos de
exclusión del Excel para protocolos de otros temas; documento único del informe y síntesis dentro de la herramienta
(WP8); coste por llamada en el dashboard antiguo; WP3, WP12, WP13; verificar el precio de Fable 5.2 en el catálogo.

## 7. Reglas prácticas

- Repositorio `~/code/palet`, rama `refactor/palet-2`, en GitHub (`origin`). `pytest`: 455 en verde, 5 xfail documentados.
- Toda ejecución real con modelo u OpenAlex la lanza Ricardo en su Mac (`source .venv/bin/activate`); el entorno del
  asistente no alcanza esas APIs, pero sí puede leer `runs/` y repetir pasos con `--replay` sin coste.
- Antes de gastar más de 1 €: estimación y permiso. Tests primero; un commit por paso; código en inglés,
  conversación en español. No dos sesiones haciendo commits a la vez en esta carpeta.
