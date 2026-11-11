Voy a leer los documentos en el orden indicado y luego verificar cada error del apéndice A contra el código actual, sin modificar nada.

Terminando la verificación: me faltan los imports de `app.py`, la llamada a PRISMA en `palet.py` y el contenido de `data/raw/isabel_chapter_2025`.

He leído los documentos y verificado todo contra el código actual sin tocar nada. Resultado: **los ocho errores de WP0 se confirman**, con tres puntos donde el informe no coincide con esta copia.

## Verificación del apéndice A y sección 6

| Error | Veredicto | Dónde |
|---|---|---|
| `escape_latex` orden de la barra | **Confirmado** (probado: `a&b` → `a\textbackslash{}&b`) | [report_generator_v2.py:53-67](scripts/report_generator_v2.py:53) |
| `included` suma por RQ en PRISMA | **Confirmado** | [prisma_validator.py:32](prisma_validator.py:32) |
| Clave fantasma `'unmatched'` | **Confirmado**, y hay un cuarto sitio que el informe no lista | [palet.py:293](palet.py:293), [report_generator_v2.py:885](scripts/report_generator_v2.py:885), [:1082](scripts/report_generator_v2.py:1082), [map_module_v2.py:381](scripts/map_module_v2.py:381) |
| Errores contados como exclusiones en MAP | **Confirmado**: las tres ramas de error devuelven `assignments: []` y el resumen las mete en `unmatched_not_relevant` | [map_module_v2.py:214-262](scripts/map_module_v2.py:214), [:319](scripts/map_module_v2.py:319) |
| Correo personal en `se_module.py` | **Confirmado** (línea 19, no 20). También literal en `se_module_legacy.py:68` | [se_module.py:19](scripts/se_module.py:19) |
| Path traversal en `/api/download` | **Confirmado**: acepta rutas absolutas y `..` sin comprobar contención | [app.py:574-582](app.py:574) |
| `sys.exit`/`input()` en librería | **Confirmado**. `sys.exit` al importar en arq, qsp, map_v2 y synthesis; dentro de funciones del pipeline en `execute_se`, `load_research_questions`, `compile_pdf`. Los `input()` están solo en bloques `__main__` y en la CLI (tras `--auto-accept`) | ver abajo |
| IDs de modelo hardcodeados | **Confirmado** en 6 ficheros, no 5: el informe omite `scripts/test_llm.py:29`, que también lleva `claude-sonnet-4-20250514`. Precios en `app.py`, `arq_module.py`, `synthesis_module.py` y `test_llm.py`; `app.py` etiqueta los precios como "Sonnet 4.5" mientras los módulos llaman a `claude-sonnet-4-6` | |

**Donde el informe no coincide con esta copia:**
- Dice que hay que mover a `legacy/` los `prompts/*_system.txt` sin versión. Pero `synthesis_system.txt` no lleva versión y **es el prompt activo** de [synthesis_module.py:27](scripts/synthesis_module.py:27). Moverlo rompería la síntesis.
- Dice que el `user.email` de git es un relleno. No: está configurado con tu dirección de Uniovi.
- Dice que hay tres entornos virtuales. Aquí solo existe `.venv` (ya lo recoge CLAUDE.md).

**Otros hallazgos relevantes para WP0:**
- El `sys.exit` al importar hace que **pytest no pueda ni importar** arq, qsp, map_v2 o synthesis sin `ANTHROPIC_API_KEY`. Es lo primero que condiciona el orden del plan.
- En la GUI, `sys.exit` dentro del hilo de trabajo mata solo el hilo: la ejecución queda en "running" para siempre.
- `scripts/` no es un paquete; `palet.py` y `app.py` lo meten en `sys.path` a mano. Los tests necesitarán lo mismo en `conftest.py` hasta WP1.
- `pytest` y `ruff` no están instalados en `.venv`.
- `.env.example` está desactualizado: lista `NCBI_API_KEY` y le faltan `OPENALEX_API_KEY`, `ELSEVIER_API_KEY` y `CONTACT_EMAIL`.
- El criterio de aceptación de WP0 (pipeline completo con `--max-results 10`) choca con dos cosas: OpenAlex sin `api_key` puede rechazar la búsqueda, y el pipeline actual escribe en `data/raw/` y `outputs/json/`, que la regla 2 protege. Lo trato en las decisiones de abajo.
- `report_generator_v2.py:886` divide por `total_papers`; con cero papers lanza `ZeroDivisionError`. Desaparece al quitar la línea de `unmatched`.

## Plan de WP0: un commit por paso

1. **Red de seguridad**: `pyproject.toml` (metadatos, deps actuales, `dev = [pytest, ruff]`, config de pytest con `pythonpath = [".", "scripts"]`, ruff con reglas mínimas y `legacy/` excluido), `tests/conftest.py`. Test: `test_imports.py`, cada módulo activo importa con una clave ficticia en el entorno.
2. **Mover a `legacy/`** con `git mv`: `palet_legacy.py`, `scripts/map_module.py`, `scripts/report_generator.py`, `scripts/se_module_legacy.py`, `prompts/arq_system.txt`, `map_system.txt`, `qsp_system.txt`. Test: `test_layout.py`, los cuatro prompts que cargan los módulos existen (protege `synthesis_system.txt`).
3. **`escape_latex`**: `re.sub` con diccionario en una sola pasada. Test: cada carácter de `\ & % _ { } ~ ^ $ #`, una cadena con todos juntos, y cirílico intacto.
4. **`included` en PRISMA**: unión de conjuntos. Test: dos papers, uno en RQ1 y RQ2, `included == 2`.
5. **Clave `'unmatched'`**: sustituir en los cuatro sitios por `unmatched_not_relevant` y `unmatched_no_abstract`. Test: `generate_latex_report` con un DataFrame de 3 papers muestra los dos recuentos correctos.
6. **Errores ≠ exclusiones en MAP**: cada resultado lleva `status` (`ok` / `error` / `no_abstract`); el resumen gana la clave `errors`, que nunca entra en `unmatched_not_relevant`; PRISMA, `palet.py` y `app.py` la muestran aparte. La unidad en MAP v2 es el paper, no la pareja (paper, RQ), así que "se marca para revisión", y el reintento selectivo queda para WP5. Test: `client.messages.create` parcheado para lanzar excepción y para devolver JSON inválido; el paper acaba en `errors`.
7. **Correo y OpenAlex**: `CONTACT_EMAIL` sin valor por defecto (si falta, no se envía `mailto`); añadir `api_key` desde `OPENALEX_API_KEY` si está definido; actualizar `.env.example`. Test: `test_hygiene.py`, ningún `.py` activo contiene un literal con forma de correo; y los parámetros de la petición con y sin variables de entorno.
8. **`/api/download`**: resolver la ruta y exigir que esté dentro de `results/` o `runs/`; 404 en caso contrario. Test con `TestClient` de FastAPI y `RESULTS_DIR` parcheado a un directorio temporal: `../.env` y ruta absoluta devuelven 404, un fichero dentro devuelve 200.
9. **`sys.exit` → excepciones**: cliente Anthropic y prompts cargados de forma perezosa (`get_client()`), `PaletConfigError` si falta la clave; `execute_se` sin resultados, `load_*` y `compile_pdf` lanzan excepciones; `palet.py` las captura y sale. Test: importar sin `ANTHROPIC_API_KEY` no lanza `SystemExit`; llamar a `extract_keywords` sin clave lanza `PaletConfigError`; `execute_se` con búsquedas parcheadas a vacío lanza `NoResultsError`.
10. **`palet.toml` + cargador** con `tomllib`: IDs de modelo por fase, precios por MTok, `per_page`, `max_results`, `batch_size`, límites de síntesis. Mantengo `claude-sonnet-4-6` para que las salidas no cambien; en este paso cargaré la referencia `claude-api` para verificar IDs y precios vigentes en vez de fiarme de memoria. Test: `test_config.py` carga el fichero y `test_hygiene.py` comprueba que no queda ningún literal `claude-` ni precio fuera de la config.
11. **CI**: `.github/workflows/ci.yml` con `ruff check` y `pytest` en Python 3.12. Verificación local con el mismo comando; no se verá en GitHub hasta que tú hagas push.
12. **Tests de parseo y esquemas**: fixture JSON de OpenAlex grabada (una llamada real, tres works recortados), tests de `parse_openalex_results` (abstract desde índice invertido, DOI, año), de `remove_duplicates` (DOI con mayúsculas, título repetido sin DOI, y el caso Coaquira/Velásquez como `xfail` hasta WP4) y de `validate_map_output` / `validate_arq_output`.

Cierre: ejecución de aceptación con `--max-results 10 --auto-accept` (estimo bastante menos de 1 €; te daré la cifra antes de lanzarla), comparación con una salida anterior, y entrada en `CHANGELOG.md`.

**Fuera de WP0 a propósito**: `search.title_and_abstract` y `meta.count` (WP3), `iloc` posicional (WP1), checklist PRISMA-ScR (WP9), `YOUR_USERNAME` y la afirmación sobre `temperature=0` en el README (WP13).

**Decisiones que necesito de ti antes de empezar** (mi recomendación primero):
- `synthesis_system.txt`: renombrar a `synthesis_system_v1.txt` y actualizar el módulo, o dejarlo como está.
- `prompts/arq_system_v2.txt` no lo usa nadie: moverlo también a `legacy/`, o dejarlo.
- El correo literal en `legacy/se_module_legacy.py`: sustituirlo por la lectura del entorno aunque sea legacy (repositorio público), o dejarlo intacto.
- Cargador de `palet.toml`: crear ya `palet/config.py` como primer fichero del paquete de WP1, o ponerlo en `scripts/`.
- Ejecución de aceptación: el pipeline actual añade ficheros nuevos con timestamp a `data/raw/` y `outputs/json/`. Acepto que son añadidos, no modificaciones, y la lanzo en WP0, o la pospongo a WP1 cuando todo vaya a `runs/`.

Si dices "continuar" sin más, aplico mis recomendaciones, creo la rama `refactor/palet-2` desde `main` y empiezo por el paso 1.