# scripts/se_module.py
# Módulo SE: Search Execution
# Ejecuta búsquedas y recupera metadatos bibliográficos

import requests
import time
import os
import sys
import json
import pandas as pd
from datetime import datetime
from pyalex import Works
from dotenv import load_dotenv

load_dotenv()


def load_qsp_output(filepath: str) -> dict:
    """Carga query estructurada de QSP."""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"ERROR: No se encontró {filepath}")
        sys.exit(1)


def search_openalex(query: str, max_results: int = 100, verbose: bool = True,
                   min_year: int = None, max_year: int = None,
                   doc_types: list = None) -> list:
    """
    Busca papers en OpenAlex con filtros opcionales.

    Args:
        query: Query de búsqueda
        max_results: Máximo de resultados
        verbose: Imprimir progreso
        min_year: Año mínimo de publicación
        max_year: Año máximo de publicación
        open_access_only: Solo papers Open Access
        doc_types: Lista de tipos ['article', 'review', 'book-chapter']

    Returns:
        Lista de works de OpenAlex
    """

    base_url = "https://api.openalex.org/works"

    # Construir filtros
    filters = []

    if min_year:
        filters.append(f"from_publication_date:{min_year}-01-01")

    if max_year:
        filters.append(f"to_publication_date:{max_year}-12-31")

    if doc_types:
        # OpenAlex usa type en lugar de doc_type
        # Tipos válidos: article, book-chapter, dissertation, etc.
        type_filter = "|".join(doc_types)
        filters.append(f"type:{type_filter}")

    # Construir URL con filtros
    params = {
        "search": query,
        "per_page": 200,
        "mailto": "ricardo.martinez.rm774@gmail.com"  # Buenas prácticas OpenAlex
    }

    if filters:
        params["filter"] = ",".join(filters)

    if verbose:
        print(f"\nBuscando en OpenAlex...")
        print(f"Query: {query}")
        if filters:
            print(f"Filtros: {', '.join(filters)}")

    all_results = []
    page = 1

    while len(all_results) < max_results:
        params["page"] = page

        try:
            response = requests.get(base_url, params=params, timeout=30)
            response.raise_for_status()

            data = response.json()
            results = data.get('results', [])

            if not results:
                break

            all_results.extend(results)

            if verbose:
                print(f"  Página {page}: {len(results)} resultados")

            if len(results) < 200:
                break

            page += 1
            time.sleep(0.1)

        except requests.exceptions.RequestException as e:
            print(f"Error en búsqueda OpenAlex: {e}")
            break

    return all_results[:max_results]


def parse_openalex_results(results: list) -> pd.DataFrame:
    """
    Convierte resultados de OpenAlex a DataFrame estructurado.
    Maneja casos donde faltan datos.
    """
    data = []

    for work in results:
        # Extraer autores
        authors = []
        if work.get('authorships'):
            authors = [
                a.get('author', {}).get('display_name', 'Unknown')
                for a in work['authorships']
                if a.get('author')
            ]
        authors_str = '; '.join(authors) if authors else 'Unknown'

        # Extraer abstract
        abstract = work.get('abstract')
        if not abstract and work.get('abstract_inverted_index'):
            # Reconstruir abstract desde índice invertido
            try:
                inverted = work['abstract_inverted_index']
                # Crear lista de palabras en posiciones correctas
                max_pos = max(max(positions) for positions in inverted.values())
                words = [''] * (max_pos + 1)

                for word, positions in inverted.items():  # ← Cambio: 'word' no 'words'
                    for pos in positions:
                        words[pos] = word  # ← Cambio: indentación correcta

                abstract = ' '.join(words).strip()
            except (KeyError, ValueError, TypeError):
                abstract = None

        # DOI
        doi = work.get('doi', '').replace('https://doi.org/', '') if work.get('doi') else None

        # Source (con verificación de None)
        source = None
        primary_location = work.get('primary_location')
        if primary_location and isinstance(primary_location, dict):
            source_data = primary_location.get('source')
            if source_data and isinstance(source_data, dict):
                source = source_data.get('display_name')

        # Conceptos/keywords
        concepts = []
        if work.get('concepts'):
            concepts = [
                c.get('display_name')
                for c in work['concepts'][:5]
                if c.get('display_name')
            ]
        concepts_str = '; '.join(concepts) if concepts else ''

        # Open access info
        open_access_data = work.get('open_access', {})
        is_oa = open_access_data.get('is_oa', False) if isinstance(open_access_data, dict) else False

        entry = {
            'title': work.get('title', 'Untitled'),
            'authors': authors_str,
            'year': work.get('publication_year'),
            'doi': doi,
            'source': source,
            'cited_by_count': work.get('cited_by_count', 0),
            'abstract': abstract,
            'concepts': concepts_str,
            'open_access': is_oa,
            'openalex_id': work.get('id'),
            'url': work.get('doi') or work.get('id')
        }

        data.append(entry)

    df = pd.DataFrame(data)
    return df


def remove_duplicates(df: pd.DataFrame, verbose: bool = True) -> pd.DataFrame:
    """
    Elimina duplicados basado en DOI y título.
    """
    initial_count = len(df)

    # Duplicados por DOI
    df_with_doi = df[df['doi'].notna()]
    df_without_doi = df[df['doi'].isna()]

    df_with_doi = df_with_doi.drop_duplicates(subset=['doi'], keep='first')

    # Duplicados por título (para papers sin DOI)
    df_without_doi = df_without_doi.drop_duplicates(subset=['title'], keep='first')

    # Combinar
    df_clean = pd.concat([df_with_doi, df_without_doi], ignore_index=True)

    removed = initial_count - len(df_clean)

    if verbose and removed > 0:
        print(f"🧹 Duplicados eliminados: {removed}")
        print(f"📊 Papers únicos: {len(df_clean)}\n")

    return df_clean


def save_results(df: pd.DataFrame, qsp_filepath: str) -> str:
    """Guarda resultados en CSV."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"se_results_{timestamp}.csv"

    output_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        'data', 'raw'
    )
    os.makedirs(output_dir, exist_ok=True)

    output_path = os.path.join(output_dir, filename)

    df.to_csv(output_path, index=False, encoding='utf-8')

    print(f"💾 Resultados guardados: {output_path}")

    # Metadata con conversión de tipos numpy a tipos Python nativos
    metadata = {
        'source_qsp': qsp_filepath,
        'timestamp': timestamp,
        'total_papers': int(len(df)),
        'papers_with_doi': int(df['doi'].notna().sum()),
        'papers_with_abstract': int(df['abstract'].notna().sum()),
        'year_range': [int(df['year'].min()), int(df['year'].max())] if not df['year'].isna().all() else None
    }

    metadata_path = output_path.replace('.csv', '_metadata.json')
    with open(metadata_path, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2)

    print(f"📋 Metadata guardada: {metadata_path}")

    return output_path


def print_summary(df: pd.DataFrame):
    """Imprime resumen de resultados."""
    print("\n" + "="*60)
    print("RESUMEN DE BÚSQUEDA")
    print("="*60)
    print(f"Total papers: {len(df)}")
    print(f"Papers con DOI: {df['doi'].notna().sum()}")
    print(f"Papers con abstract: {df['abstract'].notna().sum()}")
    print(f"Rango años: {int(df['year'].min())} - {int(df['year'].max())}" if not df['year'].isna().all() else "N/A")
    print(f"Open Access: {df['open_access'].sum()}")
    print(f"Citaciones promedio: {df['cited_by_count'].mean():.1f}")

    print("\nTop 5 sources:")
    top_sources = df['source'].value_counts().head(5)
    for source, count in top_sources.items():
        print(f"  - {source}: {count}")

    print("\nPrimeros 3 papers:")
    for i, row in df.head(3).iterrows():
        print(f"\n{i+1}. {row['title']}")
        print(f"   {row['authors'][:100]}...")
        print(f"   {row['source']} ({row['year']})")
        print(f"   DOI: {row['doi'] if row['doi'] else 'N/A'}")

    print("="*60)


if __name__ == "__main__":
    print("="*60)
    print("  MÓDULO SE - Search Execution")
    print("="*60)

    # Listar QSP outputs
    outputs_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'outputs', 'json')
    qsp_files = [f for f in os.listdir(outputs_dir) if f.startswith('qsp_output_')]

    if not qsp_files:
        print("\n❌ No se encontraron outputs de QSP")
        print("Ejecuta primero: python scripts/qsp_module.py")
        sys.exit(1)

    print(f"\nOutputs de QSP disponibles ({len(qsp_files)}):")
    for i, f in enumerate(sorted(qsp_files, reverse=True), 1):
        print(f"  {i}. {f}")

    choice = input("\nSelecciona archivo (número): ").strip()

    if choice.isdigit() and 1 <= int(choice) <= len(qsp_files):
        qsp_file = sorted(qsp_files, reverse=True)[int(choice) - 1]
        qsp_path = os.path.join(outputs_dir, qsp_file)
    else:
        print("Selección inválida")
        sys.exit(1)

    # Cargar QSP
    qsp_data = load_qsp_output(qsp_path)
    query = qsp_data['boolean_query']

    print(f"\nQuery cargada: {query[:80]}...")

    # Configurar búsqueda
    max_results = input("\nMáximo de resultados (default 100): ").strip()
    max_results = int(max_results) if max_results.isdigit() else 100

    # Ejecutar búsqueda
    results = search_openalex(query, max_results=max_results)

    if not results:
        print("❌ No se encontraron resultados")
        sys.exit(1)

    # Parsear resultados
    print("📊 Procesando resultados...")
    df = parse_openalex_results(results)

    # Eliminar duplicados
    df = remove_duplicates(df)

    # Guardar
    output_path = save_results(df, qsp_path)

    # Resumen
    print_summary(df)

    print("\n✅ Módulo SE completado")
    print(f"\nPróximo paso: Analizar abstracts con módulo MAP")
