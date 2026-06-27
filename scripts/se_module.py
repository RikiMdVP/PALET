# scripts/se_module.py
# Módulo SE: Search Execution
# Ejecuta búsquedas y recupera metadatos bibliográficos
# Soporta: OpenAlex, PubMed

import requests
import time
import os
import sys
import json
import xml.etree.ElementTree as ET
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# ─── Email para buenas prácticas con APIs ───────────────────────────────────
CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "ricardo.martinez.rm774@gmail.com")


# ════════════════════════════════════════════════════════════════════════════
#  OPENALEX
# ════════════════════════════════════════════════════════════════════════════

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
    Retorna lista de works (dicts crudos de la API).
    """
    base_url = "https://api.openalex.org/works"

    filters = []
    if min_year:
        filters.append(f"from_publication_date:{min_year}-01-01")
    if max_year:
        filters.append(f"to_publication_date:{max_year}-12-31")
    if doc_types:
        type_filter = "|".join(doc_types)
        filters.append(f"type:{type_filter}")

    params = {
        "search": query,
        "per_page": 200,
        "mailto": CONTACT_EMAIL
    }
    if filters:
        params["filter"] = ",".join(filters)

    if verbose:
        print(f"\n🔍 Buscando en OpenAlex...")
        print(f"   Query: {query[:80]}...")
        if filters:
            print(f"   Filtros: {', '.join(filters)}")

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
                print(f"   Página {page}: {len(results)} resultados | Total: {len(all_results)}")
            if len(results) < 200:
                break
            page += 1
            time.sleep(0.1)
        except requests.exceptions.RequestException as e:
            print(f"   ⚠️  Error en OpenAlex: {e}")
            break

    return all_results[:max_results]


def parse_openalex_results(results: list) -> pd.DataFrame:
    """Convierte resultados de OpenAlex a DataFrame normalizado."""
    data = []

    for work in results:
        # Autores
        authors = []
        if work.get('authorships'):
            authors = [
                a.get('author', {}).get('display_name', 'Unknown')
                for a in work['authorships']
                if a.get('author')
            ]
        authors_str = '; '.join(authors) if authors else 'Unknown'

        # Abstract
        abstract = work.get('abstract')
        if not abstract and work.get('abstract_inverted_index'):
            try:
                inverted = work['abstract_inverted_index']
                max_pos = max(max(positions) for positions in inverted.values())
                words = [''] * (max_pos + 1)
                for word, positions in inverted.items():
                    for pos in positions:
                        words[pos] = word
                abstract = ' '.join(words).strip()
            except (KeyError, ValueError, TypeError):
                abstract = None

        # DOI
        doi = work.get('doi', '').replace('https://doi.org/', '') if work.get('doi') else None

        # Source / Journal
        source = None
        primary_location = work.get('primary_location')
        if primary_location and isinstance(primary_location, dict):
            source_data = primary_location.get('source')
            if source_data and isinstance(source_data, dict):
                source = source_data.get('display_name')

        # Conceptos
        concepts = []
        if work.get('concepts'):
            concepts = [c.get('display_name') for c in work['concepts'][:5] if c.get('display_name')]

        open_access_data = work.get('open_access', {})
        is_oa = open_access_data.get('is_oa', False) if isinstance(open_access_data, dict) else False

        data.append({
            'title': work.get('title', 'Untitled'),
            'authors': authors_str,
            'year': work.get('publication_year'),
            'doi': doi,
            'source': source,
            'cited_by_count': work.get('cited_by_count', 0),
            'abstract': abstract,
            'concepts': '; '.join(concepts),
            'open_access': is_oa,
            'openalex_id': work.get('id'),
            'url': work.get('doi') or work.get('id'),
            'database': 'OpenAlex'
        })

    return pd.DataFrame(data)


# ════════════════════════════════════════════════════════════════════════════
#  PUBMED  (E-utilities API — gratuita, sin registro obligatorio)
# ════════════════════════════════════════════════════════════════════════════

PUBMED_ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
PUBMED_EFETCH  = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"


def search_pubmed(query: str, max_results: int = 100, verbose: bool = True,
                  min_year: int = None, max_year: int = None,
                  doc_types: list = None) -> list:
    """
    Busca papers en PubMed mediante E-utilities (NCBI).
    Retorna lista de dicts con metadatos normalizados.

    Args:
        query       : Texto de búsqueda (acepta sintaxis booleana estándar)
        max_results : Número máximo de resultados
        verbose     : Imprimir progreso
        min_year    : Año mínimo (filtro PDAT)
        max_year    : Año máximo (filtro PDAT)
        doc_types   : Lista de tipos — PubMed usa ['Journal Article', 'Review', etc.]
                      Si se pasan 'article'/'review' (estilo OpenAlex) los traduce.

    Returns:
        Lista de dicts con campos normalizados
    """

    # ── Traducción de tipos de documento (compatibilidad con OpenAlex) ──────
    type_map = {
        'article': 'Journal Article',
        'review':  'Review',
        'book-chapter': 'Book Chapter',
        'preprint': 'Preprint',
    }
    pubmed_types = []
    if doc_types:
        for dt in doc_types:
            pubmed_types.append(type_map.get(dt.lower(), dt))

    # ── Añadir filtros de fecha y tipo a la query ────────────────────────────
    full_query = query
    if min_year and max_year:
        full_query += f' AND ("{min_year}/01/01"[PDAT] : "{max_year}/12/31"[PDAT])'
    elif min_year:
        full_query += f' AND ("{min_year}/01/01"[PDAT] : "3000"[PDAT])'
    elif max_year:
        full_query += f' AND ("1000"[PDAT] : "{max_year}/12/31"[PDAT])'

    if pubmed_types:
        type_filter = ' OR '.join(f'"{t}"[PT]' for t in pubmed_types)
        full_query += f' AND ({type_filter})'

    if verbose:
        print(f"\n🔍 Buscando en PubMed...")
        print(f"   Query: {full_query[:100]}...")

    # ── Paso 1: esearch — obtener PMIDs ──────────────────────────────────────
    esearch_params = {
        "db": "pubmed",
        "term": full_query,
        "retmax": min(max_results, 10000),
        "retmode": "json",
        "tool": "PALET",
        "email": CONTACT_EMAIL
    }

    try:
        r = requests.get(PUBMED_ESEARCH, params=esearch_params, timeout=30)
        r.raise_for_status()
        search_data = r.json()
    except requests.exceptions.RequestException as e:
        print(f"   ⚠️  Error en PubMed esearch: {e}")
        return []

    pmids = search_data.get('esearchresult', {}).get('idlist', [])
    total_found = int(search_data.get('esearchresult', {}).get('count', 0))

    if verbose:
        print(f"   Total encontrados: {total_found} | Recuperando: {len(pmids)}")

    if not pmids:
        return []

    # ── Paso 2: efetch — descargar metadatos en XML ──────────────────────────
    # PubMed recomienda lotes de máximo 200 PMIDs por petición
    all_articles = []
    batch_size = 200

    for i in range(0, len(pmids), batch_size):
        batch = pmids[i:i + batch_size]
        efetch_params = {
            "db": "pubmed",
            "id": ",".join(batch),
            "rettype": "xml",
            "retmode": "xml",
            "tool": "PALET",
            "email": CONTACT_EMAIL
        }

        try:
            r = requests.get(PUBMED_EFETCH, params=efetch_params, timeout=60)
            r.raise_for_status()
            articles = _parse_pubmed_xml(r.text)
            all_articles.extend(articles)

            if verbose:
                print(f"   Lote {i // batch_size + 1}: {len(articles)} artículos procesados")

            time.sleep(0.34)  # NCBI permite max 3 req/seg sin API key

        except requests.exceptions.RequestException as e:
            print(f"   ⚠️  Error en PubMed efetch (lote {i // batch_size + 1}): {e}")
            continue

    return all_articles[:max_results]


def _parse_pubmed_xml(xml_text: str) -> list:
    """
    Parsea el XML de respuesta de PubMed efetch.
    Retorna lista de dicts normalizados al mismo esquema que OpenAlex.
    """
    articles = []

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as e:
        print(f"   ⚠️  Error parseando XML de PubMed: {e}")
        return []

    for article in root.findall('.//PubmedArticle'):
        try:
            medline = article.find('MedlineCitation')
            if medline is None:
                continue

            art = medline.find('Article')
            if art is None:
                continue

            # ── Título ──────────────────────────────────────────────────────
            title_el = art.find('ArticleTitle')
            title = ''.join(title_el.itertext()).strip() if title_el is not None else 'Untitled'

            # ── Abstract ────────────────────────────────────────────────────
            abstract_parts = []
            abstract_el = art.find('Abstract')
            if abstract_el is not None:
                for text_el in abstract_el.findall('AbstractText'):
                    label = text_el.get('Label', '')
                    text = ''.join(text_el.itertext()).strip()
                    if label:
                        abstract_parts.append(f"{label}: {text}")
                    else:
                        abstract_parts.append(text)
            abstract = ' '.join(abstract_parts) if abstract_parts else None

            # ── Autores ──────────────────────────────────────────────────────
            authors = []
            author_list = art.find('AuthorList')
            if author_list is not None:
                for author in author_list.findall('Author'):
                    last = author.findtext('LastName', '')
                    fore = author.findtext('ForeName', '')
                    name = f"{last}, {fore}".strip(', ')
                    if name:
                        authors.append(name)
            authors_str = '; '.join(authors) if authors else 'Unknown'

            # ── Año ──────────────────────────────────────────────────────────
            year = None
            pub_date = art.find('.//PubDate')
            if pub_date is not None:
                year_el = pub_date.find('Year')
                if year_el is not None:
                    try:
                        year = int(year_el.text)
                    except (ValueError, TypeError):
                        year = None

            # ── DOI ──────────────────────────────────────────────────────────
            doi = None
            for id_el in article.findall('.//ArticleId'):
                if id_el.get('IdType') == 'doi':
                    doi = id_el.text
                    break

            # ── PMID ─────────────────────────────────────────────────────────
            pmid = None
            for id_el in article.findall('.//ArticleId'):
                if id_el.get('IdType') == 'pubmed':
                    pmid = id_el.text
                    break

            # ── Journal / Source ─────────────────────────────────────────────
            journal_el = art.find('Journal')
            source = None
            if journal_el is not None:
                source = journal_el.findtext('Title') or journal_el.findtext('ISOAbbreviation')

            # ── MeSH keywords ────────────────────────────────────────────────
            mesh_terms = []
            mesh_list = medline.find('MeshHeadingList')
            if mesh_list is not None:
                for mesh in mesh_list.findall('MeshHeading'):
                    desc = mesh.find('DescriptorName')
                    if desc is not None:
                        mesh_terms.append(desc.text)

            articles.append({
                'title': title,
                'authors': authors_str,
                'year': year,
                'doi': doi,
                'source': source,
                'cited_by_count': None,          # PubMed no proporciona citas
                'abstract': abstract,
                'concepts': '; '.join(mesh_terms[:5]),
                'open_access': False,          # PubMed no lo informa directamente
                'openalex_id': None,
                'url': f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else None,
                'database': 'PubMed',
                'pmid': pmid
            })

        except Exception as e:
            # No interrumpir el loop por un artículo problemático
            continue

    return articles


def parse_pubmed_results(results: list) -> pd.DataFrame:
    """Convierte lista de dicts de PubMed a DataFrame (ya normalizado)."""
    if not results:
        return pd.DataFrame()
    df = pd.DataFrame(results)
    # Asegurar que todas las columnas del esquema existan
    for col in ['title', 'authors', 'year', 'doi', 'source', 'cited_by_count',
                'abstract', 'concepts', 'open_access', 'openalex_id', 'url', 'database']:
        if col not in df.columns:
            df[col] = None
    return df


# ════════════════════════════════════════════════════════════════════════════
#  DEDUPLICACIÓN Y UTILIDADES COMUNES
# ════════════════════════════════════════════════════════════════════════════

def remove_duplicates(df: pd.DataFrame, verbose: bool = True) -> tuple[pd.DataFrame, dict]:
    """
    Elimina duplicados. Devuelve DataFrame limpio Y estadísticas de deduplicación.
    """
    if df.empty:
        return df, {}

    initial_count = len(df)

    # Distribución por base de datos ANTES de deduplicar
    db_counts_raw = {}
    if 'database' in df.columns:
        db_counts_raw = df['database'].value_counts().to_dict()

    df = df.copy()
    df['doi_normalized'] = df['doi'].str.lower().str.strip()

    df_with_doi    = df[df['doi_normalized'].notna() & (df['doi_normalized'] != '')]
    df_without_doi = df[df['doi_normalized'].isna()  | (df['doi_normalized'] == '')]

    df_with_doi    = df_with_doi.drop_duplicates(subset=['doi_normalized'], keep='first')
    df_without_doi = df_without_doi.drop_duplicates(subset=['title'], keep='first')

    df_clean = pd.concat([df_with_doi, df_without_doi], ignore_index=True)
    df_clean = df_clean.drop(columns=['doi_normalized'])

    removed = initial_count - len(df_clean)

    dedup_stats = {
        'identified_by_database': db_counts_raw,
        'total_identified': initial_count,
        'duplicates_removed': removed,
        'total_after_dedup': len(df_clean)
    }

    if verbose and removed > 0:
        print(f"🧹 Duplicados eliminados: {removed}")
        print(f"📊 Papers únicos: {len(df_clean)}")

    return df_clean, dedup_stats


def save_results(df: pd.DataFrame, qsp_filepath: str) -> str:
    """Guarda resultados en CSV con metadata JSON asociada."""
    timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename   = f"se_results_{timestamp}.csv"
    output_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), 'data', 'raw'
    )
    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, filename)

    df.to_csv(output_path, index=False, encoding='utf-8')
    print(f"💾 Resultados guardados: {output_path}")

    metadata = {
        'source_qsp': qsp_filepath,
        'timestamp': timestamp,
        'total_papers': int(len(df)),
        'papers_with_doi': int(df['doi'].notna().sum()),
        'papers_with_abstract': int(df['abstract'].notna().sum()),
        'year_range': (
            [int(df['year'].min()), int(df['year'].max())]
            if not df['year'].isna().all() else None
        ),
        'databases': df['database'].value_counts().to_dict() if 'database' in df.columns else {}
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
    print(f"Total papers:            {len(df)}")
    print(f"Papers con DOI:          {df['doi'].notna().sum()}")
    print(f"Papers con abstract:     {df['abstract'].notna().sum()}")

    if not df['year'].isna().all():
        print(f"Rango años:              {int(df['year'].min())} - {int(df['year'].max())}")

    if 'database' in df.columns:
        print("\nDistribución por base de datos:")
        for db, count in df['database'].value_counts().items():
            print(f"  - {db}: {count}")

    print("\nTop 5 fuentes:")
    top_sources = df['source'].value_counts().head(5)
    for source, count in top_sources.items():
        print(f"  - {source}: {count}")

    print("\nPrimeros 3 papers:")
    for i, row in df.head(3).iterrows():
        print(f"\n{i+1}. {row['title']}")
        print(f"   {str(row['authors'])[:100]}...")
        print(f"   {row['source']} ({row['year']}) [{row.get('database','?')}]")
        print(f"   DOI: {row['doi'] if row['doi'] else 'N/A'}")
    print("="*60)


# ════════════════════════════════════════════════════════════════════════════
#  FUNCIÓN PRINCIPAL — ORQUESTA LA BÚSQUEDA EN UNA O VARIAS BDs
# ════════════════════════════════════════════════════════════════════════════

def execute_se(query: str, max_results: int = 100,
               min_year: int = None, max_year: int = None,
               doc_types: list = None,
               database: str = "openalex",
               qsp_filepath: str = "",
               verbose: bool = True) -> tuple:
    """
    Punto de entrada principal del módulo SE.

    Args:
        query       : Query de búsqueda
        max_results : Máximo de resultados por base de datos
        min_year    : Año mínimo
        max_year    : Año máximo
        doc_types   : Tipos de documento ['article', 'review', ...]
        database    : 'openalex' | 'pubmed' | 'both'
        qsp_filepath: Ruta al archivo QSP de origen (para metadata)
        verbose     : Mostrar progreso

    Returns:
        (csv_path, dedup_stats): Ruta al CSV de resultados y estadísticas
        de deduplicación para el módulo PRISMA
    """
    frames = []

    if database in ("openalex", "both"):
        raw = search_openalex(query, max_results, verbose, min_year, max_year, doc_types)
        if raw:
            df_oa = parse_openalex_results(raw)
            frames.append(df_oa)
            if verbose:
                print(f"   ✓ OpenAlex: {len(df_oa)} papers")

    if database in ("pubmed", "both"):
        raw_pm = search_pubmed(query, max_results, verbose, min_year, max_year, doc_types)
        if raw_pm:
            df_pm = parse_pubmed_results(raw_pm)
            frames.append(df_pm)
            if verbose:
                print(f"   ✓ PubMed: {len(df_pm)} papers")

    if not frames:
        print("❌ No se encontraron resultados en ninguna base de datos.")
        sys.exit(1)

    df = pd.concat(frames, ignore_index=True)
    df, dedup_stats = remove_duplicates(df, verbose)  # ← desempaquetar tupla

    output_path = save_results(df, qsp_filepath)

    # Persistir dedup_stats en la metadata JSON del SE
    metadata_path = output_path.replace('.csv', '_metadata.json')
    try:
        with open(metadata_path, 'r', encoding='utf-8') as f:
            metadata = json.load(f)
        metadata['dedup_stats'] = dedup_stats
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2)
    except Exception as e:
        print(f"⚠️  No se pudieron guardar dedup_stats en metadata: {e}")

    print_summary(df)

    return output_path, dedup_stats


# ════════════════════════════════════════════════════════════════════════════
#  EJECUCIÓN STANDALONE (python scripts/se_module.py)
# ════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("="*60)
    print("  MÓDULO SE - Search Execution")
    print("="*60)

    # Seleccionar QSP output
    outputs_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'outputs', 'json')
    qsp_files   = [f for f in os.listdir(outputs_dir) if f.startswith('qsp_output_')]

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

    qsp_data = load_qsp_output(qsp_path)
    query    = qsp_data['boolean_query']
    print(f"\nQuery cargada: {query[:80]}...")

    # Configuración
    max_results = input("\nMáximo de resultados por BD (default 100): ").strip()
    max_results = int(max_results) if max_results.isdigit() else 100

    db_choice = input("Base de datos [openalex / pubmed / both] (default openalex): ").strip().lower()
    if db_choice not in ("openalex", "pubmed", "both"):
        db_choice = "openalex"

    # Ejecutar
    se_path, _ = execute_se(
        query=query,
        max_results=max_results,
        database=db_choice,
        qsp_filepath=qsp_path
)

    print("\n✅ Módulo SE completado")
    print("Próximo paso: Analizar abstracts con módulo MAP")
