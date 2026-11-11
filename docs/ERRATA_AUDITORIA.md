# Erratas del informe de auditoría (docs/PALET_auditoria_plan_mejora.tex)

Correcciones detectadas al verificar el informe contra el código (sesión de verificación del 2026-11-11, ver `docs/sesiones/2026-11-11_wp0_verificacion_fable51.md`). **Prevalecen sobre el informe.**

1. **WP0, paso 1 (mover a `legacy/`)**: NO mover `prompts/synthesis_system.txt`; es el prompt activo de `scripts/synthesis_module.py`. Se renombra a `prompts/synthesis_system_v1.txt` (con `git mv`) y se actualiza la ruta en el módulo. Sí se mueven a `legacy/`: `arq_system.txt`, `map_system.txt`, `qsp_system.txt` y también `arq_system_v2.txt` (no lo usa nadie).
2. **Sección 6 / apéndice A — clave fantasma `'unmatched'`**: hay un cuarto sitio, `scripts/map_module_v2.py:381` (además de `palet.py:293` y `report_generator_v2.py:885, 1082`).
3. **Apéndice A — correo personal**: está en `scripts/se_module.py:19` (no 20) y también en `scripts/se_module_legacy.py:68`.
4. **Sección 6 — IDs de modelo**: están en 6 ficheros, no 5 (falta `scripts/test_llm.py:29`, con `claude-sonnet-4-20250514`). Los precios están en `app.py`, `arq_module.py`, `synthesis_module.py` y `test_llm.py`; `app.py` los etiqueta como "Sonnet 4.5" mientras los módulos llaman a `claude-sonnet-4-6`.
5. **Sección 6 — `user.email` de git**: NO es un valor de relleno; está configurado correctamente.
6. **Sección 6 — entornos virtuales**: en la copia de trabajo (`~/code/palet`) solo existe `.venv`.
7. **WP0 — criterio de aceptación**: la ejecución de prueba del pipeline actual añade ficheros nuevos con timestamp en `data/raw/` y `outputs/json/`. Se permite (son añadidos, no modificaciones; ver CLAUDE.md, regla 2). Debe lanzarse después de añadir `api_key` de OpenAlex y con estimación de coste previa.
8. **Hallazgos adicionales a incorporar en WP0**: `sys.exit` al importar impide que pytest importe arq/qsp/map_v2/synthesis sin `ANTHROPIC_API_KEY`; en la GUI, `sys.exit` dentro del hilo deja la ejecución en "running"; `scripts/` no es un paquete (los tests necesitan `pythonpath`); `pytest` y `ruff` no están instalados; `.env.example` desactualizado; `report_generator_v2.py:886` divide por `total_papers` (ZeroDivisionError con 0 papers).
