# Mensaje de arranque para Fable (sesión 1: WP0)

Copiar y pegar como primer mensaje en una sesión abierta en `~/code/palet`:

---

Hola. Vamos a empezar la refactorización de PALET a la versión 2.0.

Antes de tocar nada, lee en este orden:
1. `CLAUDE.md` (reglas de trabajo; obligatorias).
2. `docs/PALET_auditoria_plan_mejora.tex`: secciones 1 (resumen), 6 (debilidades por módulo), 8 (paquetes de trabajo; sobre todo WP0 y WP1), 11 (instrucciones para ti) y apéndice A (lista de errores).
3. `docs/DECISIONES_METODO.md` y `config/protocol_isabel_chapter_v1.yaml` (solo para contexto; no se usan hasta WP2).

Tarea de esta sesión: **WP0 — Higiene y red de seguridad**.

Primer paso, sin modificar ningún fichero:
- Verifica contra el código actual cada error del apéndice A y de la sección 6 que afecte a WP0 (escape_latex, recuento `included` en PRISMA, clave fantasma `unmatched`, errores contados como exclusiones en MAP, correo en `se_module.py`, path traversal en `/api/download`, `sys.exit`/`input()` en librería, IDs de modelo hardcodeados). Dime cuáles confirmas, cuáles no y si encuentras otros.
- Propón el plan de WP0 dividido en pasos pequeños (uno por commit), con el test que escribirás en cada uno.

Después espera mi "continuar" antes de crear la rama `refactor/palet-2` y empezar el primer paso.
