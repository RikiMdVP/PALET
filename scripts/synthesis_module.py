# scripts/synthesis_module.py
# Módulo SYNTHESIS: Síntesis narrativa y detección de gaps de literatura
# Se ejecuta entre MAP y REPORT en el pipeline PALET

import os
import sys
import json
import time
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
SYNTHESIS_SYSTEM_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    'prompts',
    'synthesis_system.txt'
)

try:
    with open(SYNTHESIS_SYSTEM_PATH, 'r', encoding='utf-8') as f:
        SYNTHESIS_SYSTEM_PROMPT = f.read()
except FileNotFoundError:
    print(f"ERROR: No se encontró {SYNTHESIS_SYSTEM_PATH}")
    sys.exit(1)

# ─── Constantes ─────────────────────────────────────────────────────────────
MAX_PAPERS_PER_RQ   = 25   # Límite de papers enviados por RQ a Claude
MAX_ABSTRACT_CHARS  = 1200  # Truncar abstracts largos para controlar tokens
MODEL               = "claude-sonnet-4-6"
MAX_TOKENS_SYNTH    = 4000  # Por síntesis (una por RQ)
MAX_TOKENS_GAPS     = 4000  # Para el análisis de gaps global


# ════════════════════════════════════════════════════════════════════════════
#  UTILIDADES
# ════════════════════════════════════════════════════════════════════════════

def _truncate_abstract(abstract: str, max_chars: int = MAX_ABSTRACT_CHARS) -> str:
    """Trunca abstracts largos para controlar el tamaño del contexto."""
    if not abstract or pd.isna(abstract):
        return "Abstract not available."
    abstract = str(abstract).strip()
    if len(abstract) <= max_chars:
        return abstract
    return abstract[:max_chars] + "... [truncated]"


def _select_representative_papers(paper_ids: list, papers_df: pd.DataFrame,
                                   max_papers: int = MAX_PAPERS_PER_RQ,
                                   reasoning_map: dict = None) -> list:
    """
    Selecciona los papers más representativos para una RQ cuando hay más
    de MAX_PAPERS_PER_RQ asignados.

    Estrategia: prioriza papers con abstract disponible, luego ordena por
    citaciones descendentes (OpenAlex) y toma los más recientes como complemento.

    Args:
        paper_ids   : IDs de papers asignados a esta RQ
        papers_df   : DataFrame completo de papers
        max_papers  : Límite máximo a seleccionar
        reasoning_map: Reasoning de MAP por paper_id (opcional)

    Returns:
        Lista de dicts con metadatos listos para enviar a Claude
    """
    selected = []

    for pid in paper_ids:
        try:
            row = papers_df.iloc[int(pid)]
            abstract = row.get('abstract')
            if pd.isna(abstract) or not str(abstract).strip():
                continue  # Excluir sin abstract en primera pasada

            entry = {
                'paper_id': int(pid),
                'title': str(row.get('title', 'Untitled')),
                'authors': str(row.get('authors', 'Unknown')),
                'year': int(row['year']) if pd.notna(row.get('year')) else None,
                'source': str(row.get('source', '')) if pd.notna(row.get('source')) else '',
                'cited_by_count': int(row['cited_by_count']) if pd.notna(row.get('cited_by_count')) else 0,
                'abstract': _truncate_abstract(abstract),
                'concepts': str(row.get('concepts', '')) if pd.notna(row.get('concepts')) else '',
                'database': str(row.get('database', '')),
                'map_reasoning': reasoning_map.get(int(pid), {}).get('reasoning', '') if reasoning_map else ''
            }
            selected.append(entry)
        except (IndexError, ValueError, TypeError):
            continue

    if not selected:
        return []

    # Ordenar: primero por citaciones desc, luego por año desc
    selected.sort(key=lambda x: (x['cited_by_count'], x['year'] or 0), reverse=True)

    # Tomar top MAX_PAPERS_PER_RQ
    return selected[:max_papers]


def _build_papers_text(papers: list) -> str:
    """Formatea la lista de papers como texto estructurado para Claude."""
    lines = []
    for i, p in enumerate(papers, 1):
        year_str = str(p['year']) if p['year'] else 'N/A'
        cited_str = str(p['cited_by_count']) if p['cited_by_count'] else 'N/A'
        lines.append(
            f"[Paper {i}]\n"
            f"Title: {p['title']}\n"
            f"Authors: {p['authors']}\n"
            f"Year: {year_str} | Source: {p['source']} | Citations: {cited_str} | DB: {p['database']}\n"
            f"Concepts: {p['concepts']}\n"
            f"Abstract: {p['abstract']}\n"
        )
    return "\n---\n".join(lines)


def _parse_json_response(response_text: str, mode: str) -> dict:
    """
    Parsea y valida la respuesta JSON de Claude.
    Maneja posibles markdown code blocks residuales.
    """
    text = response_text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()

    # Guard: detectar JSON truncado antes de intentar parsear
    # Un JSON completo debe terminar en }
    if not text.rstrip().endswith("}"):
        raise ValueError(
            f"Respuesta truncada (no termina en '}}') — "
            f"aumenta MAX_TOKENS_SYNTH o MAX_TOKENS_GAPS. "
            f"Últimos 50 chars: ...{text[-50:]}"
        )

    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"JSON inválido en respuesta de modo {mode}: {e}\n"
            f"Respuesta (primeros 300 chars): {text[:300]}"
        )


# ════════════════════════════════════════════════════════════════════════════
#  MODO A: SÍNTESIS NARRATIVA POR RQ
# ════════════════════════════════════════════════════════════════════════════

def generate_narrative_synthesis(rq_index: int, rq_text: str,
                                  paper_ids: list, papers_df: pd.DataFrame,
                                  reasoning_map: dict,
                                  verbose: bool = True) -> dict:
    """
    Genera síntesis narrativa para una Research Question.

    Args:
        rq_index    : Índice de la RQ (1-based)
        rq_text     : Texto completo de la RQ
        paper_ids   : IDs de papers asignados a esta RQ
        papers_df   : DataFrame completo de papers
        reasoning_map: Reasoning de MAP por paper_id
        verbose     : Mostrar progreso

    Returns:
        Dict con síntesis estructurada o dict de error
    """
    if verbose:
        print(f"\n  Sintetizando RQ{rq_index}: {rq_text[:70]}...")
        print(f"  Papers asignados: {len(paper_ids)}")

    # Seleccionar papers representativos
    papers = _select_representative_papers(
        paper_ids, papers_df,
        max_papers=MAX_PAPERS_PER_RQ,
        reasoning_map=reasoning_map
    )

    if not papers:
        if verbose:
            print(f"  ⚠️  Sin papers con abstract para RQ{rq_index}")
        return {
            "rq": rq_text,
            "synthesis": {
                "overview": "No papers with available abstracts were assigned to this research question.",
                "main_findings": "N/A",
                "tensions": "N/A",
                "methodological_patterns": "N/A",
                "emerging_themes": "N/A",
                "synthesis_statement": "Insufficient evidence to generate synthesis."
            },
            "paper_count_used": 0,
            "confidence": "low",
            "confidence_note": "No abstracts available for synthesis."
        }

    papers_text = _build_papers_text(papers)
    total_assigned = len(paper_ids)
    total_used = len(papers)
    truncation_note = (
        f"Note: {total_assigned} papers were assigned to this RQ. "
        f"Due to context limits, synthesis is based on the {total_used} most-cited papers with available abstracts."
        if total_assigned > total_used else
        f"All {total_used} assigned papers with abstracts are included."
    )

    user_message = f"""MODE A — NARRATIVE SYNTHESIS

Research Question {rq_index}: {rq_text}

{truncation_note}

PAPERS TO SYNTHESIZE ({total_used} papers):

{papers_text}

Generate the narrative synthesis for this Research Question following the structure defined in the system prompt.
"""

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS_SYNTH,
                temperature=0,
                system=SYNTHESIS_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}]
            )

            result = _parse_json_response(response.content[0].text, mode="A")

            # Asegurar campos mínimos
            result['rq_index'] = rq_index
            result['paper_count_assigned'] = total_assigned
            result['paper_count_used'] = total_used
            result['tokens_used'] = {
                'input': response.usage.input_tokens,
                'output': response.usage.output_tokens
            }

            if verbose:
                conf = result.get('confidence', 'n/a')
                print(f"  ✓ RQ{rq_index} sintetizada — confianza: {conf} | "
                      f"tokens: {response.usage.input_tokens}in / {response.usage.output_tokens}out")

            return result

        except (ValueError, Exception) as e:
            if verbose:
                print(f"  ⚠️  Intento {attempt+1}/{max_retries} fallido: {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            else:
                return {
                    "rq": rq_text,
                    "rq_index": rq_index,
                    "synthesis": {
                        "overview": f"Synthesis generation failed after {max_retries} attempts.",
                        "main_findings": "N/A",
                        "tensions": "N/A",
                        "methodological_patterns": "N/A",
                        "emerging_themes": "N/A",
                        "synthesis_statement": f"Error: {str(e)}"
                    },
                    "paper_count_used": total_used,
                    "confidence": "low",
                    "confidence_note": f"Generation failed: {str(e)}"
                }


# ════════════════════════════════════════════════════════════════════════════
#  MODO B: DETECCIÓN DE GAPS
# ════════════════════════════════════════════════════════════════════════════

def detect_literature_gaps(rqs: list, assignments: dict,
                            papers_df: pd.DataFrame,
                            syntheses: list,
                            verbose: bool = True) -> dict:
    """
    Detecta gaps en la literatura cruzando todas las RQs.

    Args:
        rqs         : Lista de textos de Research Questions
        assignments : Dict {RQ1: [ids], RQ2: [ids], ...} del summary MAP
        papers_df   : DataFrame completo de papers
        syntheses   : Resultados de síntesis por RQ (para contexto adicional)
        verbose     : Mostrar progreso

    Returns:
        Dict con análisis de gaps estructurado
    """
    if verbose:
        print(f"\n  Detectando gaps en {len(rqs)} Research Questions...")

    # Construir resumen compacto por RQ para el contexto de gaps
    rq_summaries = []
    for i, rq in enumerate(rqs, 1):
        rq_key = f"RQ{i}"
        paper_ids = assignments.get(rq_key, [])

        # Muestra representativa para gaps (más pequeña que para síntesis)
        sample_papers = _select_representative_papers(
            paper_ids, papers_df, max_papers=10
        )

        # Extraer años, geografías inferidas de conceptos, y métodos
        years = [p['year'] for p in sample_papers if p['year']]
        concepts_all = "; ".join([p['concepts'] for p in sample_papers if p['concepts']])

        # Síntesis overview si está disponible
        synth_overview = ""
        if syntheses and i <= len(syntheses):
            synth_data = syntheses[i-1]
            synth_overview = synth_data.get('synthesis', {}).get('overview', '')[:300]

        rq_summaries.append({
            'index': i,
            'rq': rq,
            'paper_count': len(paper_ids),
            'year_range': f"{min(years)}-{max(years)}" if years else "N/A",
            'key_concepts': concepts_all[:400],
            'synthesis_overview': synth_overview
        })

    # Formatear para el prompt
    rq_sections = []
    for s in rq_summaries:
        rq_sections.append(
            f"RQ{s['index']}: {s['rq']}\n"
            f"  Papers assigned: {s['paper_count']}\n"
            f"  Year range: {s['year_range']}\n"
            f"  Key concepts: {s['key_concepts']}\n"
            f"  Literature overview: {s['synthesis_overview']}\n"
        )

    rq_text = "\n".join(rq_sections)

    # Estadísticas globales del corpus
    total_papers = len(papers_df)
    papers_with_abstract = int(papers_df['abstract'].notna().sum())
    db_dist = papers_df['database'].value_counts().to_dict() if 'database' in papers_df.columns else {}
    year_range = ""
    if papers_df['year'].notna().any():
        year_range = f"{int(papers_df['year'].min())}-{int(papers_df['year'].max())}"

    unmatched_count = (
        len(assignments.get('unmatched_not_relevant', [])) +
        len(assignments.get('unmatched_no_abstract', []))
    )

    corpus_stats = (
        f"Total papers in corpus: {total_papers}\n"
        f"Papers with abstract: {papers_with_abstract}\n"
        f"Database distribution: {db_dist}\n"
        f"Year range of corpus: {year_range}\n"
        f"Unmatched papers (not assigned to any RQ): {unmatched_count}\n"
    )

    user_message = f"""MODE B — LITERATURE GAP DETECTION

CORPUS STATISTICS:
{corpus_stats}

RESEARCH QUESTIONS AND COVERAGE:
{rq_text}

Analyze the above information to identify literature gaps across all Research Questions. Follow the structure defined in the system prompt for MODE B.
"""

    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS_GAPS,
                temperature=0,
                system=SYNTHESIS_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_message}]
            )

            result = _parse_json_response(response.content[0].text, mode="B")
            result['tokens_used'] = {
                'input': response.usage.input_tokens,
                'output': response.usage.output_tokens
            }

            if verbose:
                n_opportunities = len(
                    result.get('gap_analysis', {}).get('priority_opportunities', [])
                )
                print(f"  ✓ Gap analysis completado — "
                      f"{n_opportunities} oportunidades identificadas | "
                      f"tokens: {response.usage.input_tokens}in / {response.usage.output_tokens}out")

            return result

        except (ValueError, Exception) as e:
            if verbose:
                print(f"  ⚠️  Intento {attempt+1}/{max_retries} fallido: {e}")
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            else:
                return {
                    "gap_analysis": {
                        "coverage_overview": f"Gap detection failed: {str(e)}",
                        "geographic_gaps": "N/A",
                        "temporal_gaps": "N/A",
                        "methodological_gaps": "N/A",
                        "thematic_gaps": "N/A",
                        "cross_rq_gaps": "N/A",
                        "priority_opportunities": [],
                        "caveats": f"Generation failed after {max_retries} attempts."
                    }
                }


# ════════════════════════════════════════════════════════════════════════════
#  PUNTO DE ENTRADA PRINCIPAL
# ════════════════════════════════════════════════════════════════════════════

def run_synthesis(rqs: list, assignments: dict, papers_df: pd.DataFrame,
                  map_results: list, output_dir: str,
                  verbose: bool = True) -> tuple:
    """
    Ejecuta el pipeline completo de síntesis: narrativa por RQ + gaps global.

    Args:
        rqs         : Lista de Research Questions (strings)
        assignments : Dict de asignaciones de MAP {RQ1: [ids], ...}
        papers_df   : DataFrame de papers
        map_results : Lista de resultados detallados de MAP
        output_dir  : Directorio donde guardar los outputs JSON
        verbose     : Mostrar progreso

    Returns:
        (syntheses_list, gaps_dict, synthesis_path, gaps_path)
    """
    print("\n" + "="*60)
    print("  SÍNTESIS NARRATIVA Y DETECCIÓN DE GAPS")
    print("="*60)

    # Construir reasoning_map desde map_results
    reasoning_map = {}
    for result in map_results:
        pid = result.get('paper_id')
        if pid is not None:
            reasoning_map[int(pid)] = {
                'reasoning': result.get('reasoning', ''),
                'confidence': result.get('confidence', 'n/a')
            }

    # ── Fase A: Síntesis por RQ ──────────────────────────────────────────
    print(f"\n📝 Generando síntesis narrativa para {len(rqs)} RQs...")
    syntheses = []
    total_tokens_synth = {'input': 0, 'output': 0}

    for i, rq in enumerate(rqs, 1):
        rq_key = f"RQ{i}"
        paper_ids = assignments.get(rq_key, [])

        synth = generate_narrative_synthesis(
            rq_index=i,
            rq_text=rq,
            paper_ids=paper_ids,
            papers_df=papers_df,
            reasoning_map=reasoning_map,
            verbose=verbose
        )
        syntheses.append(synth)

        # Acumular tokens
        tokens = synth.get('tokens_used', {})
        total_tokens_synth['input']  += tokens.get('input', 0)
        total_tokens_synth['output'] += tokens.get('output', 0)

        # Pausa entre llamadas para evitar rate limits
        if i < len(rqs):
            time.sleep(1)

    # ── Fase B: Detección de gaps ────────────────────────────────────────
    print(f"\n🔍 Detectando gaps de literatura...")
    gaps = detect_literature_gaps(
        rqs=rqs,
        assignments=assignments,
        papers_df=papers_df,
        syntheses=syntheses,
        verbose=verbose
    )

    # ── Calcular coste total ─────────────────────────────────────────────
    gaps_tokens = gaps.get('tokens_used', {})
    total_input  = total_tokens_synth['input']  + gaps_tokens.get('input', 0)
    total_output = total_tokens_synth['output'] + gaps_tokens.get('output', 0)
    cost_usd = round(total_input * 0.000003 + total_output * 0.000015, 4)

    print(f"\n💰 Tokens totales síntesis: {total_input}in / {total_output}out | "
          f"Coste estimado: ${cost_usd}")

    # ── Guardar outputs ──────────────────────────────────────────────────
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    os.makedirs(output_dir, exist_ok=True)

    synthesis_filename = f"synthesis_{timestamp}.json"
    synthesis_path = os.path.join(output_dir, synthesis_filename)
    with open(synthesis_path, 'w', encoding='utf-8') as f:
        json.dump({
            'timestamp': timestamp,
            'rq_count': len(rqs),
            'syntheses': syntheses,
            'total_tokens': {'input': total_input, 'output': total_output},
            'cost_usd': cost_usd
        }, f, indent=2, ensure_ascii=False)

    gaps_filename = f"gaps_{timestamp}.json"
    gaps_path = os.path.join(output_dir, gaps_filename)
    with open(gaps_path, 'w', encoding='utf-8') as f:
        json.dump(gaps, f, indent=2, ensure_ascii=False)

    print(f"\n💾 Síntesis guardada: {synthesis_path}")
    print(f"💾 Gaps guardados: {gaps_path}")
    print("="*60)

    return syntheses, gaps, synthesis_path, gaps_path


# ════════════════════════════════════════════════════════════════════════════
#  EJECUCIÓN STANDALONE
# ════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("="*60)
    print("  MÓDULO SYNTHESIS - Síntesis narrativa y gaps")
    print("="*60)

    outputs_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'outputs', 'json')
    data_dir    = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'data', 'raw')
    results_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'results')

    # Seleccionar MAP summary
    summary_files = [f for f in os.listdir(outputs_dir) if f.startswith('map_summary_')]
    if not summary_files:
        print("❌ No se encontraron map_summary. Ejecuta primero MAP.")
        sys.exit(1)

    print(f"\nMAP summaries disponibles:")
    for i, f in enumerate(sorted(summary_files, reverse=True)[:5], 1):
        print(f"  {i}. {f}")

    choice = input("\nSelecciona (número): ").strip()
    summary_file = sorted(summary_files, reverse=True)[int(choice)-1]
    summary_path = os.path.join(outputs_dir, summary_file)

    with open(summary_path, 'r', encoding='utf-8') as f:
        summary_data = json.load(f)

    # Cargar MAP results detallados
    timestamp = summary_data.get('timestamp')
    map_results_path = os.path.join(outputs_dir, f"map_results_{timestamp}.json")
    map_results = []
    if os.path.exists(map_results_path):
        with open(map_results_path, 'r', encoding='utf-8') as f:
            map_results = json.load(f)
    else:
        print("⚠️  map_results no encontrado, synthesis sin reasoning de MAP")

    # Cargar ARQ
    arq_path = summary_data.get('source_arq')
    with open(arq_path, 'r', encoding='utf-8') as f:
        arq_data = json.load(f)
    rqs = arq_data['research_questions']

    # Cargar CSV de papers
    csv_path = summary_data.get('source_csv')
    papers_df = pd.read_csv(csv_path)

    assignments = summary_data.get('assignments', {})

    # Ejecutar
    syntheses, gaps, synth_path, gaps_path = run_synthesis(
        rqs=rqs,
        assignments=assignments,
        papers_df=papers_df,
        map_results=map_results,
        output_dir=outputs_dir,
        verbose=True
    )

    print("\n✅ Módulo SYNTHESIS completado")
