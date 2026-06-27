# PALET - Documentación del Proceso de Desarrollo

**Fecha inicio:** 20 abril 2025
**Estado actual:** MVP 100% completado
**Última actualización:** [8 de octubre de 2025]

---

## Índice

1. [Contexto y Objetivos](#contexto-y-objetivos)
2. [Arquitectura del Sistema](#arquitectura-del-sistema)
3. [Setup Inicial](#setup-inicial)
4. [Módulo ARQ](#módulo-arq)
5. [Módulo QSP](#módulo-qsp)
6. [Módulo SE](#módulo-se)
7. [Módulo MAP](#módulo-map-pendiente)
8. [Problemas Encontrados y Soluciones](#problemas-encontrados-y-soluciones)
9. [Próximos Pasos](#próximos-pasos)
10. [Decisiones de Diseño](#decisiones-de-diseño)

---

## Contexto y Objetivos

### ¿Qué es PALET?

PALET (Prompt-based Automated Literature Extraction Tool) es un sistema de agente autónomo basado en IA para automatizar revisiones sistemáticas de literatura científica siguiendo lineamientos PRISMA-ScR.

### Caso de uso principal

Revisión sistemática sobre políticas y estrategias para enfrentar creación/destrucción de empleo (JCD) vinculada al doble desafío de transición verde y digital en la UE (Proyecto ISABEL).

### Objetivos del MVP

- Automatizar extracción de Research Questions y keywords desde seed prompts
- Generar queries de búsqueda académica
- Recuperar papers de bases de datos académicas
- Asignar papers a Research Questions mediante análisis semántico
- Exportar resultados estructurados (CSV, JSON, PDF)

---

## Arquitectura del Sistema

### Flujo general

Usuario → ARQ → QSP → SE → MAP → Reporte

### Módulos

1. **ARQ (Automated Research Query)**: Extrae RQs y keywords desde seed prompt
2. **QSP (Query Structuring Process)**: Convierte keywords en queries de búsqueda
3. **SE (Search Execution)**: Ejecuta búsquedas y recupera papers
4. **MAP (Matching and Assignment Process)**: Asigna papers a RQs

### Stack tecnológico

- **Lenguaje:** Python 3.12
- **LLM:** Claude Sonnet 4.5 (Anthropic API)
- **Base de datos académica:** OpenAlex (primaria), Scopus (pendiente InstToken)
- **Librerías principales:**
  - `anthropic` - Cliente API Claude
  - `pyalex` - Cliente OpenAlex
  - `pandas` - Procesamiento datos
  - `python-dotenv` - Gestión variables entorno

---

## Setup Inicial

### Estructura de carpetas

palet/
├── .env                      # API keys
├── .gitignore                # Protección datos sensibles
├── palet_env/                # Entorno virtual Python
├── scripts/                  # Módulos ejecutables
│   ├── arq_module.py
│   ├── qsp_module.py
│   ├── se_module.py
│   ├── map_module.py
│   └── map_module_v2.py      # Adiciones menores


├── prompts/                  # System prompts para Claude
│   ├── arq_system.txt
│   ├── qsp_system.txt
│   ├── map_system.txt
│   ├── arq_system_v2.txt     # Mas intensivo en tokens (XML tags, etc. etc.)
│   ├── qsp_system_v2.txt     # Mas intensivo en tokens (XML tags, etc. etc.)
│   └── seed_isabel.txt (ejemplo)
├── data/
│   ├── raw/                  # CSVs de búsquedas
│   └── processed/            # Datos limpios
├── outputs/
│   ├── json/                 # Outputs intermedios
│   └── reports/              # Reportes finales
├── logs/                     # Logs de ejecución
└── docs/                     # Documentación
└── documentacion.md

### Instalación
```bash
cd "/ruta/al/proyecto/palet"
python3 -m venv palet_env
source palet_env/bin/activate
pip install anthropic python-dotenv pyalex pandas requests

### Módulo ARQ
Propósito: Extrae Research Questions y keywords académicas desde un seed prompt del usuario, aplicando framework CPC  (Context-Precision-Concision).

## Archivos

1. scripts/arq_module.py - Script principal
2. prompts/arq_system.txt - System prompt para Claude, contiene las instrucciones/indicaciones clave que seguirá el agente para funcionar.

Las características clave del system prompt son:

1. Adaptativo: Maneja prompts vagos y complejos
2. Con ejemplos (few-shot): 3 ejemplos de calidad variable
3. Educativo: Sugiere mejoras si prompt es vago
4. Estructurado: Output JSON estricto

## Flujo de ejecución

Seed prompt → Claude (ARQ system prompt) → JSON output
Output JSON:
json{
  "research_questions": ["RQ1...", "RQ2..."],
  "keywords": ["keyword1", ...],
  "reasoning": "explicación",
  "timestamp": "ISO8601",
  "tokens_used": {...},
  "cost_usd": 0.012
}

## Opciones de refinamiento

Se pueden añadir/eliminar keywords manualmente, así como regenerar con feedback adicional y aceptar resultado.

##Tiempo de ejecución promedio

Simple: ~30 segundos
Complejo: ~70 segundos
Coste: $0.40-0.50 por ejecución


## Proximos pasos

Crear un network de papers para distinguir principales escuelas de pensamiento sobre un tema, cómo se organizan temporalmente.
  Luego sintetizar en una tabla con principales contribuciones sobre determinado tema (extraido del network anterior).
Buscar/Sugerir huecos en la literatura basado en estas dos revisiones.
Capacidad de hacer buen screening pre-descarga.!!
Loop en función de calidad del prompt, para ello:
  1. ¿Cómo se puede evaluar calidad? Marco CPC + promp boosting techniques
  2. Pensando en usos reales con prompts vagos, lo mejor podría ser correr el proceso automático (si evaluación baja) analizar papers conseguidos y sugerir nuevo prompt (o nuevas ideas para prompt), entonces entrar en loop.
  3.
