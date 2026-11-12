# Sesión 2026-11-12 — flujo 2.0 completo, cribadores y dashboard

Rama `refactor/palet-2`, sin push. Estado al cerrar: `pytest` 404 en verde (5 xfail documentados), ruff limpio.

## Hecho hoy

| Bloque | Qué | Commit |
|---|---|---|
| Búsquedas | Suplementarias solo en inglés; aprobadas `rq4_d` (220) y `rq5` (54) por RMV y FRM; descargadas y deduplicadas: 509 identificados, 505 únicos | 34455b0, 16a799c |
| WP10 | `check-citations`: citas del manuscrito frente a la lista de referencias. Ejecutado: `runs/isabel_chapter_v1/report/citation_check.md` | 65a6662 |
| WP7 | `assign`: asignación de incluidos a las RQ con cita literal verificada | e1e6278 |
| WP9 | `report`: PRISMA (PDF/PNG), lista PRISMA-ScR, apéndice de métodos, excluidos, tablas y figuras. `approve-search` | 3ad7c98 |
| Cribado | Corregido: dos cribadores con el mismo modelo compartían caché (acuerdo falso del 100 %) | e170d3c |
| Cribado | Uno o dos cribadores, modelo elegible (`--screeners`); vuelve a Opus 5.5 + Sonnet 5.5 | 71bc6d5, e55e4d1 |
| Dashboard | Página `/workflow` ("Revisión 2.0") y API `/api/v2/` sobre el flujo nuevo | 59b8864 |

## Decisiones de método registradas (docs/DECISIONES_METODO.md)

- Cribadores del capítulo: Opus 5.5 (A) + Sonnet 5.5 (B). Descartado 2x Sonnet.
- La herramienta admite un solo cribador; el informe lo declara como limitación.
- Validación ciega frente a cribado humano: aplazada (no se hace para el capítulo).

## No verificado

- La página `/workflow` no se ha visto en un navegador: se probaron sus endpoints, que carga y que el JavaScript
  llega, pero no su aspecto ni los clics. Primera comprobación pendiente en el Mac.
- Ninguna ejecución real con modelo desde el dashboard (solo con modelo simulado en los tests).
- El precio de Fable 5.2 en el catálogo sigue sin verificar.

## Pendiente (en orden)

1. Cribado completo de 505 registros (≈ 24,4 $ estimados; solo 10 cribados hasta ahora).
2. Decidir los pendientes en `adjudication.xlsx` y cargarlos.
3. `assign` (pedir antes la estimación) y `report`.
4. Con los números reales: párrafo de métodos, limitaciones y respuestas de Ricardo en la carta.
5. Texto del capítulo: reescribir Sección 2 y Figura 1 (describen un proceso que no ocurrió); corregir las
   citas del informe de cotejo; declarar la asimetría de idiomas (protocolo en/es, suplementarias solo en) o cambiar D3.
6. Aplazado: coste por llamada en el dashboard antiguo; búsquedas y aprobaciones desde el dashboard; WP3, WP8,
   resto de WP11, WP12, WP13; validación frente a cribado humano (para la tesis).
