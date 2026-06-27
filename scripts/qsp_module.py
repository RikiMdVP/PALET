# scripts/qsp_module.py
# Módulo QSP: Query Structuring Process
# Asiste en construcción de queries para bases de datos académicas

import os
import sys
import json
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env'))

api_key = os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    print("ERROR: No se encontró ANTHROPIC_API_KEY en .env")
    sys.exit(1)

client = Anthropic(api_key=api_key)

QSP_SYSTEM_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    'prompts',
    'qsp_system_v2.txt'
)

with open(QSP_SYSTEM_PATH, 'r', encoding='utf-8') as f:
    QSP_SYSTEM_PROMPT = f.read()

def load_arq_output(filepath: str) -> dict:
    """Carga el output de ARQ desde JSON."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"ERROR: No se encontró {filepath}")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"ERROR: {filepath} no es JSON válido")
        sys.exit(1)


def suggest_query_structure(keywords: list, database: str = "openalex") -> str:
    """
    Sugiere estructura de query usando Claude.

    Args:
        keywords: Lista de keywords de ARQ
        database: Base de datos objetivo (openalex, scopus, wos)
    """

    prompt = f"""Given these academic keywords for a systematic literature review:

{json.dumps(keywords, indent=2)}

Suggest a search query structure for {database.upper()}.

REQUIREMENTS:
- Use boolean operators appropriately (AND, OR)
- Group related terms with OR
- Connect main concepts with AND
- Keep it simple and executable
- Do NOT use complex nesting unless necessary

Provide:
1. The suggested query string
2. Brief reasoning for the structure

Format as JSON:
{{
  "query": "your query here",
  "reasoning": "explanation",
  "alternative_queries": ["simpler version", "more specific version"]
}}
"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        system = QSP_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}]
    )

    response_text = response.content[0].text.strip()

    # Limpiar markdown
    if response_text.startswith("```json"):
        response_text = response_text.replace("```json", "").replace("```", "").strip()

    return json.loads(response_text)


def build_openalex_query(keywords: list) -> str:
    """
    Construye query simple para OpenAlex.
    OpenAlex acepta búsquedas de texto libre.
    """
    # Estrategia simple: términos más importantes con AND
    core_terms = keywords[:5]  # Primeros 5 keywords (generalmente los más importantes)
    query = " ".join(core_terms)
    return query


def build_scopus_query(keywords: list) -> str:
    """
    Construye query para Scopus siguiendo su sintaxis.
    Formato: TITLE-ABS-KEY("term1" AND "term2")
    """
    # Agrupar keywords por relevancia
    core = keywords[:3]
    secondary = keywords[3:8] if len(keywords) > 3 else []

    # Core terms con AND
    core_query = " AND ".join([f'"{term}"' for term in core])

    # Secondary con OR
    if secondary:
        secondary_query = " OR ".join([f'"{term}"' for term in secondary])
        full_query = f'TITLE-ABS-KEY(({core_query}) AND ({secondary_query}))'
    else:
        full_query = f'TITLE-ABS-KEY({core_query})'

    return full_query


def interactive_query_builder(arq_data: dict, database: str = "openalex"):
    """
    Proceso interactivo para construir query.
    """
    print("\n" + "="*60)
    print("  CONSTRUCCIÓN INTERACTIVA DE QUERY")
    print("="*60)

    keywords = arq_data['keywords']

    print(f"\nKeywords disponibles ({len(keywords)}):")
    for i, kw in enumerate(keywords, 1):
        print(f"  {i}. {kw}")

    print(f"\nBase de datos objetivo: {database.upper()}")

    # Opción 1: Sugerencia automática de Claude
    print("\nObteniendo sugerencia de Claude...")
    suggestion = suggest_query_structure(keywords, database)

    print("\n" + "-"*60)
    print("QUERY SUGERIDA:")
    print(suggestion['query'])
    print("\nRAZONAMIENTO:")
    print(suggestion['reasoning'])

    if 'alternative_queries' in suggestion:
        print("\nALTERNATIVAS:")
        for i, alt in enumerate(suggestion['alternative_queries'], 1):
            print(f"  {i}. {alt}")
    print("-"*60)

    # Opción del usuario
    print("\nOpciones:")
    print("  1. Usar query sugerida")
    print("  2. Usar alternativa")
    print("  3. Construir manualmente")
    print("  4. Query automática simple")

    choice = input("\nSelecciona (1-4): ").strip()

    if choice == "1":
        return suggestion['query']

    elif choice == "2":
        if 'alternative_queries' in suggestion and suggestion['alternative_queries']:
            alt_num = input(f"Selecciona alternativa (1-{len(suggestion['alternative_queries'])}): ").strip()
            try:
                idx = int(alt_num) - 1
                return suggestion['alternative_queries'][idx]
            except (ValueError, IndexError):
                print("Selección inválida, usando sugerencia principal")
                return suggestion['query']
        else:
            print("No hay alternativas, usando sugerencia principal")
            return suggestion['query']

    elif choice == "3":
        print("\nConstruye tu query (usa keywords arriba):")
        custom_query = input("Query: ").strip()
        return custom_query

    elif choice == "4":
        if database == "openalex":
            auto_query = build_openalex_query(keywords)
        elif database == "scopus":
            auto_query = build_scopus_query(keywords)
        else:
            auto_query = " AND ".join(keywords[:5])

        print(f"\nQuery automática generada:\n{auto_query}")
        return auto_query

    else:
        print("Opción inválida, usando sugerencia")
        return suggestion['query']


def save_qsp_output(query: str, arq_data: dict, arq_filepath: str,
                    database: str, timestamp: str = None) -> tuple:
    """Guarda query estructurada con keywords y filters."""
    from datetime import datetime
    if timestamp is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    output = {
        "timestamp": timestamp,
        "boolean_query": query,
        "keywords": arq_data.get('keywords', []),
        "research_questions": arq_data.get('research_questions', []),  # AÑADIDO
        "database": database,
        "source_arq": arq_filepath
    }

    filename = f"qsp_output_{timestamp}.json"
    output_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'outputs', 'json')
    output_path = os.path.join(output_dir, filename)

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"✓ Query guardada: {output_path}")
    return output_path, timestamp


if __name__ == "__main__":
    print("="*60)
    print("  MÓDULO QSP - Query Structuring Process")
    print("="*60)

    # Listar ARQ outputs disponibles
    outputs_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'outputs', 'json')
    arq_files = [f for f in os.listdir(outputs_dir) if f.startswith('arq_output_')]

    if not arq_files:
        print("\nNo se encontraron outputs de ARQ")
        print("Ejecuta primero: python scripts/arq_module.py")
        sys.exit(1)

    print(f"\nOutputs de ARQ disponibles ({len(arq_files)}):")
    for i, f in enumerate(sorted(arq_files, reverse=True)[:5], 1):
        print(f"  {i}. {f}")

    choice = input("\nSelecciona archivo (número o ruta completa): ").strip()

    if choice.isdigit() and 1 <= int(choice) <= len(arq_files):
        arq_file = sorted(arq_files, reverse=True)[int(choice) - 1]
        arq_path = os.path.join(outputs_dir, arq_file)
    else:
        arq_path = choice

    # Cargar ARQ output
    arq_data = load_arq_output(arq_path)

    print(f"\nARQ cargado: {len(arq_data['keywords'])} keywords, {len(arq_data['research_questions'])} RQs")

    # Seleccionar base de datos
    print("\nBase de datos objetivo:")
    print("  1. OpenAlex (recomendado por ahora)")
    print("  2. Scopus (cuando tengas InstToken)")

    db_choice = input("\nSelecciona (1-2): ").strip()
    database = "openalex" if db_choice == "1" else "scopus"

    # Construir query
    query = interactive_query_builder(arq_data, database)

    print("\n" + "="*60)
    print("QUERY FINAL:")
    print("="*60)
    print(query)
    print("="*60)

    # Guardar
    output_path, timestamp = save_qsp_output(query, arq_data, arq_path, database)

    print("\nPróximo paso: Ejecutar búsqueda con módulo SE")
    print("Comando: python scripts/se_module.py")
