# CLAUDE.md — reglas permanentes para trabajar en PALET

## Contexto
PALET (Prompt-based Automated Literature Extraction Tool) es una herramienta de revisión de alcance asistida por IA (proyecto ISABEL, GA 101177687). Se está refactorizando a "PALET 2.0" siguiendo `docs/PALET_auditoria_plan_mejora.tex` (auditoría de 11-nov-2026). Las decisiones de método vigentes están en `docs/DECISIONES_METODO.md` y el protocolo del capítulo en `config/protocol_isabel_chapter_v1.yaml`.

## Cómo trabajar con Ricardo
- Habla con Ricardo en **español**. Código, identificadores, docstrings y mensajes de commit en **inglés**.
- Ritmo **secuencial y quirúrgico**: un paquete de trabajo (WP) cada vez; dentro de él, un cambio coherente cada vez. Tras cada paso: resumen breve (qué cambió, por qué, cómo probarlo, comando exacto) y **espera confirmación** ("continuar") antes de seguir.
- Prefiere crítica directa a elogios. Si algo del informe de auditoría no coincide con el código, dilo; no supongas.
- **Decisiones de método** (criterios, umbrales, estrategia de corpus, RQs) son de Ricardo y Fernando: propón, no decidas.

## Entorno
- macOS Apple Silicon, Python 3.12 (Homebrew, arm64), VS Code, TeX Live 2026.
- Entorno virtual único: `.venv` (`source .venv/bin/activate`). No uses ni toques `venv/` ni `palet_env/` (no existen en esta copia; si aparecen, ignóralos).
- Repositorio: `~/code/palet` (fuera de iCloud). Remotos: `origin` (GitHub, RikiMdVP/PALET) y `gitlab` (ISABEL, solo accesible desde red Uniovi).
- Punto de partida etiquetado: `v1.0-pre-audit`.

## Reglas duras
1. **No borres nada.** Lo obsoleto se mueve a `legacy/`.
2. No modifiques datos históricos: `results/`, `outputs/`, `data/raw/` (incluido `data/raw/isabel_chapter_2025/`). Lo nuevo va a `runs/`.
3. **Secretos**: nunca escribas claves ni correos en el código ni en commits. Se leen de `.env` (claves disponibles: `ANTHROPIC_API_KEY`, `OPENALEX_API_KEY`, `ELSEVIER_API_KEY`, `CONTACT_EMAIL`). Actualiza `.env.example` con nombres, nunca valores.
4. **Coste**: antes de cualquier ejecución real con LLM o API de pago estimada en más de 1 €, muestra la estimación y pide permiso. En desarrollo usa muestras pequeñas (≤ 20 registros) y caché.
5. **Tests primero** en las correcciones: test que falla → arreglo → test en verde. `pytest` debe quedar en verde al final de cada paso.
6. Trabaja en la rama `refactor/palet-2`. Un commit por paso coherente (Conventional Commits). **No hagas push** sin que Ricardo lo pida.
7. Mantén `python palet.py --seed-prompt ...` funcionando como alias hasta terminar WP11.
8. Scopus API aún no disponible (VPN Uniovi pendiente). OpenAlex requiere `api_key` (obligatoria desde feb-2026); `mailto` ya no sirve.

## Orden de trabajo
Ruta mínima para el capítulo: WP0 → WP1 → WP2 → WP4 → WP5 → WP6 → WP9 → WP10. Después: WP3, WP7, WP8, WP11, WP12, WP13. Especificación y criterios de aceptación de cada WP en la sección 8 del informe de auditoría.
