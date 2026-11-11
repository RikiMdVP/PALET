# scripts/map_module.py
# Módulo MAP: Matching and Assignment Process
# Asigna papers a Research Questions mediante análisis semántico

import os
import sys
import json
import pandas as pd
from datetime import datetime
from anthropic import Anthropic
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("ANTHROPIC_API_KEY")
if not api_key:
    print("ERROR: No se encontró ANTHROPIC_API_KEY en .env")
    sys.exit(1)

client = Anthropic(api_key=api_key)

# Cargar system prompt
MAP_SYSTEM_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    'prompts',
    'map_system.txt'
)

try:
    with open(MAP_SYSTEM_PATH, 'r', encoding='utf-8') as f:
        MAP_SYSTEM_PROMPT = f.read()
except FileNotFoundError:
    print(f"ERROR: No se encontró {MAP_SYSTEM_PATH}")
    sys.exit(1)

# ====================================================================
# Función para inyectar RQs en el system prompt
# ====================================================================

def generate_map_prompt(research_questions: list) -> str:
    """
    Inyecta Research Questions en el system prompt de MAP.

    Args:
        research_questions: Lista de RQs desde ARQ output

    Returns:
        System prompt completo con RQs inyectadas
    """
    # Formatear RQs (uno por línea con guion)
    rqs_formatted = "\n".join([f"- {rq}" for rq in research_questions])

    # Reemplazar placeholder en el template
    system_prompt = MAP_SYSTEM_PROMPT.replace(
        "{{RESEARCH_QUESTIONS_WILL_BE_INSERTED_HERE}}",
        rqs_formatted
    )

    return system_prompt


# ====================================================================
# Función de validación
# ====================================================================

def validate_map_output(response: dict, num_rqs: int) -> tuple:
    """
    Valida que el output de MAP sea coherente.

    Args:
        response: JSON parseado de Claude
        num_rqs: Número total de Research Questions

    Returns:
        (is_valid: bool, error_message: str)
    """
    # Check 1: Campos requeridos
    required_fields = ['paper_id', 'title', 'assignments', 'reasoning', 'confidence']
    missing_fields = [f for f in required_fields if f not in response]
    if missing_fields:
        return False, f"Missing fields: {', '.join(missing_fields)}"

    # Check 2: Assignments válidos
    valid_assignments = [f"RQ{i+1}" for i in range(num_rqs)] + ["unmatched_no_abstract"]
    invalid_assignments = [a for a in response.get('assignments', []) if a not in valid_assignments]
    if invalid_assignments:
        return False, f"Invalid assignments: {', '.join(invalid_assignments)}"

    # Check 3: Confidence válido
    valid_confidences = ['high', 'medium', 'low', 'n/a']
    if response.get('confidence') not in valid_confidences:
        return False, f"Invalid confidence: {response.get('confidence')}"

    # Check 4: Reasoning no vacío (excepto casos especiales)
    if response.get('assignments') and response['assignments'] not in [[], ['unmatched_no_abstract']]:
        reasoning = response.get('reasoning', '').strip()
        if not reasoning or len(reasoning) < 50:
            return False, "Reasoning too short or empty"

    return True, ""

def load_papers(csv_path: str) -> pd.DataFrame:
    """Carga CSV de papers desde SE."""
    try:
        df = pd.read_csv(csv_path)
        print(f"\n✅ Papers cargados: {len(df)}")
        print(f"   - Con abstract: {df['abstract'].notna().sum()}")
        print(f"   - Sin abstract: {df['abstract'].isna().sum()}")
        return df
    except FileNotFoundError:
        print(f"ERROR: No se encontró {csv_path}")
        sys.exit(1)


def load_research_questions(arq_path: str) -> list:
    """Carga Research Questions desde ARQ output."""
    try:
        with open(arq_path, 'r', encoding='utf-8') as f:
            arq_data = json.load(f)
        rqs = arq_data['research_questions']
        print(f"\n✅ Research Questions cargadas: {len(rqs)}")
        for i, rq in enumerate(rqs, 1):
            print(f"   {i}. {rq[:80]}...")
        return rqs
    except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
        print(f"ERROR cargando RQs: {e}")
        sys.exit(1)


def analyze_paper(paper_id: int, title: str, abstract: str, rqs: list, verbose: bool = False) -> dict:
    """
    Analiza un paper y lo asigna a RQs relevantes.

    Args:
        paper_id: ID del paper en el DataFrame
        title: Título del paper
        abstract: Abstract completo
        rqs: Lista de Research Questions
        verbose: Mostrar progreso

    Returns:
        dict con assignments, reasoning, confidence
    """

    if pd.isna(abstract) or not abstract or abstract == "":
        return {
            "paper_id": paper_id,
            "title": title,
            "assignments": [],
            "reasoning": "No abstract available",
            "confidence": "n/a"
        }

    # Construir prompt
    rqs_formatted = "\n".join([f"{i+1}. {rq}" for i, rq in enumerate(rqs)])

    prompt = f"""Analyze this paper and determine which Research Questions it addresses.

RESEARCH QUESTIONS:
{rqs_formatted}

PAPER:
Title: {title}
Abstract: {abstract}

Determine which RQ(s) this paper addresses. Respond with JSON only.

CRITICAL: In your JSON response, use the paper_id EXACTLY as provided: {paper_id}
Do NOT generate a descriptive ID. Use this number: {paper_id}
Respond with JSON matching this structure:
{{
  "paper_id": {paper_id},
  "title": "{title[:50]}...",
  "assignments": ["RQ1", "RQ2"],
  "reasoning": "explanation",
  "confidence": "high/medium/low"
}}"""

    if verbose:
        print(f"\n   Analizando: {title[:60]}...")

    try:
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            system=MAP_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = response.content[0].text.strip()

        # Limpiar markdown
        if response_text.startswith("```json"):
            response_text = response_text.replace("```json", "").replace("```", "").strip()

        result = json.loads(response_text)

        # Forzar paper_id correcto
        result['paper_id'] = paper_id  # ← Sobrescribir con el correcto

        # Validar estructura
        if 'assignments' not in result:
            result['assignments'] = []

        return result

    except json.JSONDecodeError:
        print(f"\n   ⚠️  Error parseando JSON para paper {paper_id}")
        return {
            "paper_id": paper_id,
            "title": title,
            "assignments": [],
            "reasoning": "JSON parsing error",
            "confidence": "n/a"
        }
    except Exception as e:
        print(f"\n   ⚠️  Error analizando paper {paper_id}: {e}")
        return {
            "paper_id": paper_id,
            "title": title,
            "assignments": [],
            "reasoning": f"Error: {str(e)}",
            "confidence": "n/a"
        }


def process_batch(df: pd.DataFrame, rqs: list, batch_size: int = 5) -> list:
    """
    Procesa papers en batches para manejar rate limits y costos.
    """
    results = []
    total = len(df)

    print(f"\n🔄 Procesando {total} papers en batches de {batch_size}...")

    for i in range(0, total, batch_size):
        batch = df.iloc[i:i+batch_size]
        batch_num = (i // batch_size) + 1
        total_batches = (total + batch_size - 1) // batch_size

        print(f"\n📦 Batch {batch_num}/{total_batches}")

        for idx, row in batch.iterrows():
            result = analyze_paper(
                paper_id=idx,
                title=row['title'],
                abstract=row.get('abstract'),
                rqs=rqs,
                verbose=True
            )
            results.append(result)

        # Pausa entre batches (opcional, para evitar rate limits)
        if i + batch_size < total:
            import time
            time.sleep(1)

    return results


def generate_assignment_summary(results: list, rqs: list) -> dict:
    """Genera resumen de asignaciones."""
    summary = {f"RQ{i+1}": [] for i in range(len(rqs))}
    summary["unmatched"] = []

    for result in results:
        assignments = result.get('assignments', [])

        if not assignments or assignments == []:
            summary["unmatched"].append(result['paper_id'])
        else:
            for assignment in assignments:
                if assignment in summary:
                    summary[assignment].append(result['paper_id'])

    return summary


def save_map_output(results: list, summary: dict, csv_path: str, arq_path: str):
    """Guarda resultados de MAP."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Guardar resultados detallados
    results_filename = f"map_results_{timestamp}.json"
    results_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'outputs', 'json', results_filename
    )

    with open(results_path, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\n💾 Resultados detallados: {results_path}")

    # Guardar resumen
    summary_filename = f"map_summary_{timestamp}.json"
    summary_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'outputs', 'json', summary_filename
    )

    summary_with_meta = {
        "source_csv": csv_path,
        "source_arq": arq_path,
        "timestamp": timestamp,
        "assignments": summary
    }

    with open(summary_path, 'w', encoding='utf-8') as f:
        json.dump(summary_with_meta, f, indent=2, ensure_ascii=False)

    print(f"📋 Resumen de asignaciones: {summary_path}")

    return results_path, summary_path


def print_summary(summary: dict, rqs: list):
    """Imprime resumen de asignaciones."""
    print("\n" + "="*60)
    print("RESUMEN DE ASIGNACIONES")
    print("="*60)

    for i, rq in enumerate(rqs, 1):
        rq_key = f"RQ{i}"
        count = len(summary['assignments'].get(rq_key, []))
        print(f"\n{rq_key}: {count} papers")
        print(f"   {rq[:80]}...")

    unmatched = len(summary['assignments'].get('unmatched', []))
    print(f"\nUnmatched: {unmatched} papers")

    print("="*60)


if __name__ == "__main__":
    print("="*60)
    print("  MÓDULO MAP - Matching and Assignment Process")
    print("="*60)

    # Listar CSVs disponibles
    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'raw')
    csv_files = [f for f in os.listdir(data_dir) if f.startswith('se_results_') and f.endswith('.csv')]

    if not csv_files:
        print("\n❌ No se encontraron CSVs de SE")
        sys.exit(1)

    print(f"\nCSVs disponibles ({len(csv_files)}):")
    for i, f in enumerate(sorted(csv_files, reverse=True)[:5], 1):
        print(f"  {i}. {f}")

    csv_choice = input("\nSelecciona CSV (número): ").strip()

    if csv_choice.isdigit() and 1 <= int(csv_choice) <= len(csv_files):
        csv_file = sorted(csv_files, reverse=True)[int(csv_choice) - 1]
        csv_path = os.path.join(data_dir, csv_file)
    else:
        print("Selección inválida")
        sys.exit(1)

    # Cargar papers
    df = load_papers(csv_path)

    # Listar ARQ outputs
    outputs_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'outputs', 'json')
    arq_files = [f for f in os.listdir(outputs_dir) if f.startswith('arq_output_')]

    if not arq_files:
        print("\n❌ No se encontraron outputs de ARQ")
        sys.exit(1)

    print(f"\nARQ outputs disponibles ({len(arq_files)}):")
    for i, f in enumerate(sorted(arq_files, reverse=True)[:5], 1):
        print(f"  {i}. {f}")

    arq_choice = input("\nSelecciona ARQ (número): ").strip()

    if arq_choice.isdigit() and 1 <= int(arq_choice) <= len(arq_files):
        arq_file = sorted(arq_files, reverse=True)[int(arq_choice) - 1]
        arq_path = os.path.join(outputs_dir, arq_file)
    else:
        print("Selección inválida")
        sys.exit(1)

    # Cargar RQs
    rqs = load_research_questions(arq_path)

    # Configurar procesamiento
    batch_size = input("\nTamaño de batch (default 5): ").strip()
    batch_size = int(batch_size) if batch_size.isdigit() else 5

    # Procesar papers
    results = process_batch(df, rqs, batch_size)

    # Generar resumen
    summary_data = generate_assignment_summary(results, rqs)

    # Guardar
    results_path, summary_path = save_map_output(results, {'assignments': summary_data}, csv_path, arq_path)

    # Resumen final
    print_summary({'assignments': summary_data}, rqs)

    print("\n✅ Módulo MAP completado")
    print("\n🎉 PALET MVP COMPLETO - Todos los módulos funcionando")
