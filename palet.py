#!/usr/bin/env python3
# palet.py
# Script de orquestación completa del pipeline PALET

# -------------- Instrucciones --------------
# 1. Activar entorno
 # source palet_env/bin/activate

# 2. Crear/editar tu seed prompt
 # nano prompts/mi_tema.txt

# 3. Ejecutar pipeline
# python palet.py --seed-prompt prompts/mi_tema.txt --output results/

# 4. Revisar resultados
 # ls results/
# cat results/summary_*.json


# python palet.py --seed-prompt prompts/seed_populism.txt --output results/ --max-results 10 --min-year 2015 --max-year 2025 --doc-types article


import os
import sys
import argparse
from datetime import datetime

# Añadir scripts/ al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scripts'))

from arq_module import extract_keywords, save_arq_output
from qsp_module import suggest_query_structure, save_qsp_output
# ── CAMBIO 1: importar execute_se en lugar de las funciones individuales ──
from se_module import execute_se
from map_module_v2 import load_research_questions, process_batch, generate_assignment_summary, save_map_output
from report_generator_v2 import generate_latex_report, compile_pdf, calculate_statistics
from report_generator_v2 import generate_temporal_distribution, generate_citation_distribution, generate_publications_by_rq_year
from report_generator_v2 import generate_rq_distribution
from report_generator_v2 import generate_concept_frequency, generate_concept_cooccurrence
from export_bibtex import export_to_bibtex
from prisma_validator import run_prisma_validation
from synthesis_module import run_synthesis


def print_header(text):
    """Imprime header con formato."""
    print("\n" + "="*70)
    print(f"  {text}")
    print("="*70)


def run_palet_pipeline(seed_prompt_file: str, output_dir: str, database: str = "openalex",
                       max_results: int = 100, batch_size: int = 5, auto_accept: bool = False,
                       min_year: int = None, max_year: int = None,
                       doc_types: list = None):
    """
    Ejecuta pipeline completo PALET.

    Args:
        seed_prompt_file: Path al archivo con seed prompt
        output_dir: Directorio para guardar outputs finales
        database: Base de datos (openalex / pubmed / both)
        max_results: Máximo papers a recuperar
        batch_size: Tamaño de batch para MAP
        auto_accept: Si True, usa sugerencias sin confirmación
    """

    # Crear directorio output
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    print_header("PALET - Prompt-based Automated Literature Extraction Tool")
    print(f"Timestamp: {timestamp}")
    print(f"Output directory: {output_dir}")

    # ====================================================================
    # FASE 1: ARQ - Automated Research Query
    # ====================================================================

    print_header("FASE 1: ARQ - Extracción de Research Questions y Keywords")

    # Leer seed prompt
    try:
        with open(seed_prompt_file, 'r', encoding='utf-8') as f:
            seed_prompt = f.read()
    except FileNotFoundError:
        print(f"ERROR: No se encontró {seed_prompt_file}")
        sys.exit(1)

    print(f"\nSeed prompt cargado ({len(seed_prompt)} caracteres)")
    print("Extrayendo RQs y keywords con Claude...")

    arq_result = extract_keywords(seed_prompt, verbose=False)

    print(f"\n✓ Research Questions generadas: {len(arq_result['research_questions'])}")
    for i, rq in enumerate(arq_result['research_questions'], 1):
        print(f"  RQ{i}: {rq[:70]}...")

    print(f"\n✓ Keywords generadas: {len(arq_result['keywords'])}")
    print(f"  {', '.join(arq_result['keywords'][:10])}...")

    # Guardar ARQ
    arq_filename = f"arq_output_{timestamp}.json"
    arq_path = save_arq_output(arq_result, filename=arq_filename)

    print(f"\n✓ ARQ guardado: {arq_path}")

    # ====================================================================
    # FASE 2: QSP - Query Structuring Process
    # ====================================================================

    print_header("FASE 2: QSP - Estructuración de Query de Búsqueda")

    print(f"Generando query para {database.upper()}...")

    suggestion = suggest_query_structure(arq_result['keywords'], database)
    query = suggestion['query']

    print(f"\n✓ Query generada:")
    print(f"  {query[:150]}...")

    if not auto_accept:
        confirm = input("\n¿Usar esta query? (s/n): ").strip().lower()
        if confirm != 's':
            print("Query rechazada. Saliendo...")
            sys.exit(0)

    # Guardar QSP
    qsp_path, _ = save_qsp_output(query, arq_result, arq_path, database, timestamp=timestamp)

    print(f"\n✓ QSP guardado: {qsp_path}")

    # ====================================================================
    # FASE 3: SE - Search Execution
    # ====================================================================

    print_header("FASE 3: SE - Ejecución de Búsqueda y Recuperación de Papers")

    db_label = database.upper()
    print(f"Buscando en {db_label} (max {max_results} resultados por BD)...")

    # ── CAMBIO 2: llamada unificada a execute_se() ────────────────────────
    # execute_se gestiona openalex, pubmed y both internamente,
    # devuelve la ruta al CSV de resultados ya deduplicado.
    se_path, dedup_stats = execute_se(
        query=query,
        max_results=max_results,
        min_year=min_year,
        max_year=max_year,
        doc_types=doc_types,
        database=database,
        qsp_filepath=qsp_path,
        verbose=True
    )

    # Cargar el CSV generado por execute_se para el resto del pipeline
    import pandas as pd
    df = pd.read_csv(se_path, encoding='utf-8')

    print(f"\n✓ Papers únicos después de deduplicación: {len(df)}")
    print(f"  - Con abstract: {df['abstract'].notna().sum()}")
    print(f"  - Con DOI: {df['doi'].notna().sum()}")

    # ====================================================================
    # FASE 4: MAP - Matching and Assignment Process
    # ====================================================================

    print_header("FASE 4: MAP - Análisis y Asignación a Research Questions")

    rqs = arq_result['research_questions']

    print(f"Analizando {len(df)} papers contra {len(rqs)} RQs...")
    print(f"Batch size: {batch_size}")

    map_results = process_batch(df, rqs, batch_size=batch_size)

    print(f"\n✓ Papers analizados: {len(map_results)}")

    # Generar resumen
    summary = generate_assignment_summary(map_results, rqs)

    # Guardar MAP
    map_results_path, map_summary_path = save_map_output(
        map_results,
        summary,
        se_path,
        arq_path
    )

    # ── PRISMA Validation ─────────────────────────────────────────────────
    print_header("FASE 4b: PRISMA - Validación y diagrama de flujo")

    prisma_diagram_path, prisma_checklist = run_prisma_validation(
        arq_data=arq_result,
        dedup_stats=dedup_stats,
        papers_df=df,
        summary=summary,
        output_dir=output_dir
    )

    # ====================================================================
    # FASE 4b: SYNTHESIS - Síntesis narrativa y detección de gaps
    # ====================================================================

    print_header("FASE 4b: SYNTHESIS - Síntesis narrativa y detección de gaps")

    syntheses, gaps, synthesis_path, gaps_path = run_synthesis(
        rqs=rqs,
        assignments=summary,
        papers_df=df,
        map_results=map_results,
        output_dir=os.path.join(os.path.dirname(__file__), 'outputs', 'json'),
        verbose=True
    )

    # ====================================================================
    # FASE 5: REPORT - Generación de Reporte PDF
    # ====================================================================

    print_header("FASE 5: REPORT - Generación de Reporte PDF")

    print("Generando reporte LaTeX con estadísticas y gráficos...")

    # Preparar paths para report generator
    report_timestamp = timestamp
    tex_filename = f"report_{report_timestamp}.tex"
    tex_path = os.path.join(output_dir, tex_filename)

    # Cargar map_results detallados
    try:
        with open(map_results_path, 'r', encoding='utf-8') as f:
            import json
            map_results_detailed = json.load(f)
        print(f"✓ MAP results cargados: {len(map_results_detailed)} papers")
    except Exception as e:
        print(f"⚠️  No se pudieron cargar MAP results detallados: {e}")
        map_results_detailed = []

    # Generar LaTeX
    try:
        generate_latex_report(
            summary_data={'timestamp': timestamp, 'assignments': summary,
                         'source_arq': arq_path, 'source_csv': se_path,
                         'source_qsp': qsp_path},
            arq_data=arq_result,
            papers_df=df,
            map_results=map_results_detailed,
            output_path=tex_path,
            seed_prompt=seed_prompt,  # Pasar el seed prompt original
            prisma_checklist=prisma_checklist,
            prisma_diagram=True,
            syntheses=syntheses,
            gaps=gaps
        )

        print(f"✓ LaTeX generado: {tex_path}")

        # Compilar a PDF
        pdf_path = compile_pdf(tex_path)
        print(f"✓ PDF generado: {pdf_path}")

        # Abrir PDF automáticamente (solo macOS)
        import subprocess
        subprocess.run(['open', pdf_path], check=False)

    except Exception as e:
        print(f"\n⚠️  Error generando reporte PDF: {e}")
        print(f"   Puedes generarlo manualmente: python scripts/report_generator.py")


    # ====================================================================
    # FASE 6: Generación de BibTeX
    # ====================================================================

    # Exportar a BibTeX
    print("\nExportando a BibTeX...")

    bibtex_path = os.path.join(output_dir, f"references_{timestamp}.bib")
    export_to_bibtex(se_path, bibtex_path)

    # ====================================================================
    # RESUMEN FINAL
    # ====================================================================

    print_header("RESUMEN FINAL")

    print(f"\nResearch Questions ({len(rqs)}):")
    for i, rq in enumerate(rqs, 1):
        count = len(summary.get(f"RQ{i}", []))
        print(f"  RQ{i}: {count} papers - {rq[:60]}...")

    unmatched = len(summary.get('unmatched', []))
    print(f"\n  Unmatched: {unmatched} papers")

    print(f"\nOutputs generados:")
    print(f"  - ARQ: {arq_path}")
    print(f"  - QSP: {qsp_path}")
    print(f"  - SE:  {se_path}")
    print(f"  - MAP: {map_summary_path}")

    # Copiar outputs finales a output_dir
    import shutil

    final_summary = os.path.join(output_dir, f"summary_{timestamp}.json")
    shutil.copy(map_summary_path, final_summary)

    final_papers = os.path.join(output_dir, f"papers_{timestamp}.csv")
    shutil.copy(se_path, final_papers)

    print(f"\nArchivos copiados a {output_dir}:")
    print(f"  - {final_summary}")
    print(f"  - {final_papers}")

    print_header("PIPELINE COMPLETADO EXITOSAMENTE")

    return {
        'arq_path': arq_path,
        'qsp_path': qsp_path,
        'se_path': se_path,
        'map_results_path': map_results_path,
        'map_summary_path': map_summary_path,
        'report_pdf': tex_path.replace('.tex', '.pdf') if 'pdf_path' in locals() else None,
        'timestamp': timestamp
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="PALET - Automated systematic literature review pipeline"
    )

    parser.add_argument(
        '--seed-prompt',
        required=True,
        help='Path to seed prompt file'
    )

    parser.add_argument(
        '--output',
        default='./results',
        help='Output directory (default: ./results)'
    )

    # ── CAMBIO 1 (argparse): un único --database con los tres valores válidos ──
    parser.add_argument(
        '--database',
        default='openalex',
        choices=['openalex', 'pubmed', 'both'],
        help='Academic database to search (default: openalex)'
    )

    parser.add_argument(
        '--max-results',
        type=int,
        default=100,
        help='Maximum papers to retrieve per database (default: 100)'
    )

    parser.add_argument(
        '--batch-size',
        type=int,
        default=5,
        help='Batch size for MAP processing (default: 5)'
    )

    parser.add_argument(
        '--auto-accept',
        action='store_true',
        help='Auto-accept query suggestions without confirmation'
    )

    parser.add_argument(
        '--min-year',
        type=int,
        default=None,
        help='Minimum publication year (e.g., 2015)'
    )

    parser.add_argument(
        '--max-year',
        type=int,
        default=None,
        help='Maximum publication year (e.g., 2025)'
    )

    parser.add_argument(
        '--doc-types',
        nargs='+',
        default=['article', 'review'],
        help='Document types (default: article review)'
    )

    args = parser.parse_args()

    try:
        results = run_palet_pipeline(
            seed_prompt_file=args.seed_prompt,
            output_dir=args.output,
            database=args.database,
            max_results=args.max_results,
            batch_size=args.batch_size,
            auto_accept=args.auto_accept,
            min_year=args.min_year,
            max_year=args.max_year,
            doc_types=args.doc_types
        )

        sys.exit(0)

    except KeyboardInterrupt:
        print("\n\nProceso interrumpido por usuario")
        sys.exit(1)
    except Exception as e:
        print(f"\n\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
