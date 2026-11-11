# legacy/

Obsolete files kept for reference (project rule: nothing is deleted).
They are not imported by the pipeline, not linted and not tested.

The directory mirrors the original layout (`legacy/scripts/`, `legacy/prompts/`),
so relative paths inside these files keep resolving within `legacy/`.

| File | Superseded by |
|---|---|
| `palet_legacy.py` | `palet.py` |
| `scripts/map_module.py` + `prompts/map_system.txt` | `scripts/map_module_v2.py` + `prompts/map_system_v2.txt` |
| `scripts/report_generator.py` | `scripts/report_generator_v2.py` |
| `scripts/se_module_legacy.py` | `scripts/se_module.py` |
| `prompts/arq_system.txt`, `prompts/arq_system_v2.txt` | `prompts/arq_system_v3.txt` |
| `prompts/qsp_system.txt` | `prompts/qsp_system_v2.txt` |
| `scripts/test_*.py`, `scripts/configure_pybliometrics.py` | Manual smoke scripts that call real APIs; replaced by `tests/` |

Moved in WP0 of the PALET 2.0 refactor (November 2026).
