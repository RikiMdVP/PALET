> **PALET 2.0 (noviembre de 2026).** Esta guía describe el pipeline 1.0. El flujo nuevo (protocolo, cribado con dos modelos, decisión humana, asignación, informe) y su dashboard están descritos en `docs/ESTADO.md`, sección 6; se abre con `python -m uvicorn app:app --port 8000` en `/workflow`.

# Guía para escribir buenos seed prompts

PALET funciona mejor cuando tu seed prompt sigue el framework CPC:

## Contexto (X)
- ¿Qué ámbito geográfico? (Europa, España, global)
- ¿Qué periodo temporal? (últimos 5 años, post-2020)
- ¿Qué disciplina? (economía, sociología, informática)

## Precisión (P)
- ¿Qué fenómeno específico? (no "IA" sino "automatización en manufactura")
- ¿Qué aspecto te interesa? (causas, efectos, políticas)

## Concisión (C)
- 2-4 frases claras
- Evita divagaciones

### Ejemplo MALO:
"Quiero saber sobre IA"

### Ejemplo BUENO:
"Quiero revisar el impacto de la automatización mediante IA en
el empleo manufacturero en Europa (2018-2024), enfocándome en
políticas de reconversión laboral."
