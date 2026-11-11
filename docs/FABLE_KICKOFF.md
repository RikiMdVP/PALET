# Mensaje de arranque para Fable 5.2 (sesión 1: WP0)

Copiar y pegar como primer mensaje en una sesión abierta en `~/code/palet`:

---

Hola. Vamos a empezar la refactorización de PALET a la versión 2.0.

Antes de tocar nada, lee en este orden:
1. `CLAUDE.md` (reglas de trabajo; obligatorias).
2. `docs/ERRATA_AUDITORIA.md` (correcciones al informe; prevalecen sobre él).
3. `docs/PALET_auditoria_plan_mejora.tex`: secciones 1, 6, 8 (sobre todo WP0 y WP1), 11 y apéndice A.
4. `docs/DECISIONES_METODO.md` y `config/protocol_isabel_chapter_v1.yaml` (solo contexto; no se usan hasta WP2).

Tarea de esta sesión: **WP0 — Higiene y red de seguridad**.

Ya hubo una sesión previa de verificación con otro modelo: `docs/sesiones/2026-11-11_wp0_verificacion_fable51.md`. **Haz primero tu propia verificación** de los errores de WP0 contra el código, sin leer esa nota; después contrástala con ella y dime en qué coincidís y en qué no.

Decisiones ya tomadas para WP0 (no hace falta preguntarlas):
- `prompts/synthesis_system.txt` → renombrar a `synthesis_system_v1.txt` con `git mv` y actualizar `synthesis_module.py`.
- `prompts/arq_system_v2.txt` → mover a `legacy/` junto con `arq_system.txt`, `map_system.txt` y `qsp_system.txt`.
- Correo literal en `se_module_legacy.py` → sustituirlo también por lectura del entorno. No reescribir el historial de git.
- El cargador de `palet.toml` va en `palet/config.py`, primer fichero del paquete. Ten en cuenta la regla de nombres de CLAUDE.md (`palet.py` frente a `palet/`).
- La ejecución de aceptación de WP0 sí se hace en WP0, al final, después de añadir la `api_key` de OpenAlex, con `--max-results 10 --auto-accept` y dándome antes la estimación de coste.
- IDs de modelo: en WP0 se mantiene `claude-sonnet-4-6` para no cambiar las salidas; solo se mueve a la configuración.

Entrega de este primer mensaje, **sin modificar ningún fichero**:
- Tu verificación y el contraste con la nota previa.
- El plan de WP0 en pasos pequeños (uno por commit), con el test de cada paso.

Después espera mi "continuar" para crear la rama `refactor/palet-2` y empezar el paso 1.
