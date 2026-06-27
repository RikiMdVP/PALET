# scripts/report_generator_v2.py
# Generador de reporte PDF en LaTeX - Versión mejorada

import os
import sys
import json
import pandas as pd
import numpy as np
from datetime import datetime
import subprocess
import networkx as nx
from collections import Counter
from itertools import combinations
import matplotlib
matplotlib.use('Agg')  # Backend sin GUI
import matplotlib.pyplot as plt


def load_map_summary(summary_path: str) -> dict:
    """Carga resumen de MAP."""
    with open(summary_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_map_results(results_path: str) -> list:
    """Carga resultados detallados de MAP."""
    with open(results_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def load_arq_output(arq_path: str) -> dict:
    """Carga output de ARQ."""
    with open(arq_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def load_papers_csv(csv_path: str) -> pd.DataFrame:
    """Carga CSV de papers."""
    return pd.read_csv(csv_path)

def load_seed_prompt(arq_data: dict) -> str:
    """Intenta recuperar seed prompt original."""
    # Si ARQ guardó el reasoning, puede contener pistas
    # Por ahora retornamos placeholder
    return "Seed prompt not directly available in pipeline outputs."


def escape_latex(text: str) -> str:
    """Escapa caracteres especiales de LaTeX."""
    if pd.isna(text):
        return ""

    text = str(text)

    replacements = {
        '&': r'\&',
        '%': r'\%',
        '$': r'\$',
        '#': r'\#',
        '_': r'\_',
        '{': r'\{',
        '}': r'\}',
        '~': r'\textasciitilde{}',
        '^': r'\^{}',
        '\\': r'\textbackslash{}',
    }

    for char, replacement in replacements.items():
        text = text.replace(char, replacement)

    return text


def generate_temporal_distribution(papers_df: pd.DataFrame, output_dir: str) -> str:
    """Genera gráfico de barras de distribución temporal."""
    fig, ax = plt.subplots(figsize=(12, 6))

    valid_years = papers_df[papers_df['year'].notna()]['year']

    if len(valid_years) == 0:
        ax.text(0.5, 0.5, 'No year data available',
                ha='center', va='center', fontsize=14, transform=ax.transAxes)
    else:
        year_counts = valid_years.value_counts().sort_index()

        # Barras verticales
        bars = ax.bar(year_counts.index, year_counts.values,
                     color='steelblue', edgecolor='black', alpha=0.8, width=0.8)

        # Añadir valores encima de barras
        for bar in bars:
            height = bar.get_height()
            if height > 0:
                ax.text(bar.get_x() + bar.get_width()/2., height,
                       f'{int(height)}',
                       ha='center', va='bottom', fontsize=9)

        ax.set_xlabel('Year', fontsize=12, fontweight='bold')
        ax.set_ylabel('Number of Papers', fontsize=12, fontweight='bold')
        ax.set_title('Temporal Distribution of Retrieved Papers',
                    fontsize=14, fontweight='bold', pad=20)
        ax.grid(axis='y', alpha=0.3, linestyle='--')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)

        # Rotar labels si hay muchos años
        if len(year_counts) > 15:
            plt.xticks(rotation=45, ha='right')

    output_path = os.path.join(output_dir, 'temporal_distribution.png')
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()

    return output_path

def generate_publications_by_rq_year(papers_df: pd.DataFrame, assignments: dict,
                                     rqs: list, output_dir: str) -> str:
    """
    Genera gráfico de líneas: publicaciones por año para cada RQ.
    """
    fig, ax = plt.subplots(figsize=(14, 8))

    # Filtrar papers con año válido
    valid_papers = papers_df[papers_df['year'].notna()].copy()

    if len(valid_papers) == 0:
        ax.text(0.5, 0.5, 'No year data available',
               ha='center', va='center', fontsize=14, transform=ax.transAxes)
    else:
        # Colores para cada RQ (paleta profesional)
        colors = plt.cm.tab10(np.linspace(0, 1, len(rqs)))

        # Para cada RQ, contar papers por año
        for i, rq in enumerate(rqs, 1):
            rq_key = f"RQ{i}"
            paper_ids = assignments.get(rq_key, [])

            if not paper_ids:
                continue

            # Filtrar papers de esta RQ
            rq_papers = valid_papers.iloc[[int(pid) for pid in paper_ids
                                          if int(pid) < len(valid_papers)]]

            if len(rq_papers) == 0:
                continue

            # Contar por año
            year_counts = rq_papers['year'].value_counts().sort_index()

            # Plotear línea
            ax.plot(year_counts.index, year_counts.values,
                   marker='o', linewidth=2, markersize=6,
                   color=colors[i-1], label=f'RQ-{i}', alpha=0.8)

        # Línea total (papers únicos)
        total_year_counts = valid_papers['year'].value_counts().sort_index()
        ax.plot(total_year_counts.index, total_year_counts.values,
               marker='s', linewidth=3, markersize=7,
               color='green', linestyle='--', label='Total', alpha=0.9)

        # Configuración
        ax.set_xlabel('Year', fontsize=13, fontweight='bold')
        ax.set_ylabel('Number of Articles', fontsize=13, fontweight='bold')
        ax.set_title('Annual Publications by Research Question (Admitted Articles)',
                    fontsize=15, fontweight='bold', pad=20)

        ax.legend(title='Research Question', fontsize=10, title_fontsize=11,
                 loc='upper left', framealpha=0.9)

        ax.grid(True, alpha=0.3, linestyle='--')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)

        # Forzar años como enteros en eje X
        ax.xaxis.set_major_locator(plt.MaxNLocator(integer=True))

    output_path = os.path.join(output_dir, 'publications_by_rq_year.png')
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()

    print(f"✓ Gráfico de publicaciones por RQ y año generado")

    return output_path

def generate_cumulative_distribution(papers_df: pd.DataFrame, output_dir: str) -> str:
    """Genera gráfico de línea acumulativa de papers por año."""
    fig, ax = plt.subplots(figsize=(12, 6))

    valid_years = papers_df[papers_df['year'].notna()]['year']

    if len(valid_years) == 0:
        ax.text(0.5, 0.5, 'No year data available',
                ha='center', va='center', fontsize=14, transform=ax.transAxes)
    else:
        year_counts = valid_years.value_counts().sort_index()
        cumulative = year_counts.cumsum()

        # Línea con markers
        ax.plot(cumulative.index, cumulative.values,
               marker='o', linewidth=2.5, markersize=7,
               color='darkblue', markerfacecolor='steelblue',
               markeredgewidth=1.5, markeredgecolor='darkblue')

        # Área bajo la curva
        ax.fill_between(cumulative.index, cumulative.values,
                       alpha=0.2, color='steelblue')

        ax.set_xlabel('Year', fontsize=12, fontweight='bold')
        ax.set_ylabel('Cumulative Papers', fontsize=12, fontweight='bold')
        ax.set_title('Cumulative Growth of Literature',
                    fontsize=14, fontweight='bold', pad=20)
        ax.grid(True, alpha=0.3, linestyle='--')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)

        # Añadir anotación del total
        total = cumulative.values[-1]
        ax.annotate(f'Total: {int(total)} papers',
                   xy=(cumulative.index[-1], total),
                   xytext=(10, -20), textcoords='offset points',
                   fontsize=11, fontweight='bold',
                   bbox=dict(boxstyle='round,pad=0.5', facecolor='white',
                            edgecolor='darkblue', linewidth=1.5),
                   arrowprops=dict(arrowstyle='->', color='darkblue', lw=1.5))

    output_path = os.path.join(output_dir, 'cumulative_distribution.png')
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()

    return output_path

def generate_citation_by_year(papers_df: pd.DataFrame, output_dir: str) -> str:
    """Genera scatter plot de citaciones vs año."""
    fig, ax = plt.subplots(figsize=(12, 6))

    # Filtrar papers con año y citaciones
    valid_data = papers_df[papers_df['year'].notna() & papers_df['cited_by_count'].notna()]

    if len(valid_data) == 0:
        ax.text(0.5, 0.5, 'No citation/year data available',
                ha='center', va='center', fontsize=14, transform=ax.transAxes)
    else:
        # Scatter plot con tamaño proporcional a citaciones
        sizes = valid_data['cited_by_count'] / valid_data['cited_by_count'].max() * 200 + 20

        scatter = ax.scatter(valid_data['year'], valid_data['cited_by_count'],
                           s=sizes, alpha=0.6, c=valid_data['cited_by_count'],
                           cmap='YlOrRd', edgecolors='black', linewidth=0.5)

        # Colorbar
        cbar = plt.colorbar(scatter, ax=ax)
        cbar.set_label('Citations', fontsize=11, fontweight='bold')

        ax.set_xlabel('Year', fontsize=12, fontweight='bold')
        ax.set_ylabel('Citations', fontsize=12, fontweight='bold')
        ax.set_title('Citation Distribution by Publication Year',
                    fontsize=14, fontweight='bold', pad=20)
        ax.grid(True, alpha=0.3, linestyle='--')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)

        # Destacar paper más citado
        max_cited = valid_data.loc[valid_data['cited_by_count'].idxmax()]
        ax.annotate(f"Most cited: {int(max_cited['cited_by_count'])} citations",
                   xy=(max_cited['year'], max_cited['cited_by_count']),
                   xytext=(20, 20), textcoords='offset points',
                   fontsize=10, fontweight='bold',
                   bbox=dict(boxstyle='round,pad=0.5', facecolor='yellow', alpha=0.7),
                   arrowprops=dict(arrowstyle='->', color='red', lw=2))

    output_path = os.path.join(output_dir, 'citations_by_year.png')
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()

    return output_path

def generate_citation_distribution(papers_df: pd.DataFrame, output_dir: str) -> str:
    """Genera boxplot y violin plot combinados de citaciones."""
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))

    citations = papers_df['cited_by_count'].dropna()

    if len(citations) == 0:
        for ax in [ax1, ax2]:
            ax.text(0.5, 0.5, 'No citation data',
                   ha='center', va='center', fontsize=14, transform=ax.transAxes)
    else:
        # Boxplot
        bp = ax1.boxplot(citations, vert=True, patch_artist=True,
                        boxprops=dict(facecolor='lightblue', alpha=0.7),
                        medianprops=dict(color='red', linewidth=2),
                        whiskerprops=dict(linewidth=1.5),
                        capprops=dict(linewidth=1.5))

        ax1.set_ylabel('Citations', fontsize=12, fontweight='bold')
        ax1.set_title('Citation Distribution (Boxplot)', fontsize=12, fontweight='bold')
        ax1.grid(axis='y', alpha=0.3, linestyle='--')
        ax1.spines['top'].set_visible(False)
        ax1.spines['right'].set_visible(False)
        ax1.set_xticklabels(['All Papers'])

        # Estadísticas en texto
        stats_text = f"Mean: {citations.mean():.1f}\nMedian: {citations.median():.0f}\nMax: {citations.max():.0f}"
        ax1.text(0.02, 0.98, stats_text, transform=ax1.transAxes,
                fontsize=10, verticalalignment='top',
                bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.5))

        # Histograma
        ax2.hist(citations, bins=min(30, len(citations.unique())),
                color='steelblue', alpha=0.7, edgecolor='black')
        ax2.set_xlabel('Citations', fontsize=12, fontweight='bold')
        ax2.set_ylabel('Frequency', fontsize=12, fontweight='bold')
        ax2.set_title('Citation Distribution (Histogram)', fontsize=12, fontweight='bold')
        ax2.grid(axis='y', alpha=0.3, linestyle='--')
        ax2.spines['top'].set_visible(False)
        ax2.spines['right'].set_visible(False)

    output_path = os.path.join(output_dir, 'citation_distribution.png')
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()

    return output_path

def generate_rq_distribution(assignments: dict, rqs: list, output_dir: str) -> str:
    """Genera gráfico de barras horizontal de papers por RQ."""
    fig, ax = plt.subplots(figsize=(10, max(6, len(rqs) * 0.8)))

    rq_counts = [len(assignments.get(f"RQ{i+1}", [])) for i in range(len(rqs))]
    rq_labels = [f"RQ{i+1}" for i in range(len(rqs))]

    # Barras horizontales con gradiente
    colors = plt.cm.Blues(np.linspace(0.4, 0.8, len(rqs)))
    bars = ax.barh(rq_labels, rq_counts, color=colors, edgecolor='black', linewidth=1.5)

    ax.set_xlabel('Number of Papers', fontsize=12, fontweight='bold')
    ax.set_ylabel('Research Question', fontsize=12, fontweight='bold')
    ax.set_title('Papers Assigned per Research Question', fontsize=14, fontweight='bold', pad=20)
    ax.grid(axis='x', alpha=0.3, linestyle='--')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    # Valores al final de barras
    for i, (bar, count) in enumerate(zip(bars, rq_counts)):
        ax.text(count + 0.3, i, str(count), va='center', fontsize=11, fontweight='bold')

    output_path = os.path.join(output_dir, 'rq_distribution.png')
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()

    return output_path

def extract_concepts_from_csv(papers_df: pd.DataFrame) -> list:
    """
    Extrae concepts del CSV (formato: "concept1; concept2; concept3").

    Returns:
        Lista de listas de concepts por paper
    """
    all_concepts = []

    for concepts_str in papers_df['concepts'].dropna():
        if not isinstance(concepts_str, str) or not concepts_str.strip():
            continue

        # Separar por ; y limpiar
        concepts = [c.strip().lower() for c in concepts_str.split(';')]
        concepts = [c for c in concepts if c and len(c) > 2]

        if concepts:
            all_concepts.append(concepts)

    return all_concepts

def generate_concept_cooccurrence(papers_df: pd.DataFrame, output_dir: str) -> str:
    """
    Genera red de co-ocurrencias de concepts de OpenAlex.
    """

    all_concepts = extract_concepts_from_csv(papers_df)

    if len(all_concepts) < 2:
        print("⚠️  Insuficientes concepts para análisis de co-ocurrencias")
        return None

    # Contar co-ocurrencias (pares de concepts que aparecen juntos)
    cooccurrences = Counter()
    for concepts in all_concepts:
        if len(concepts) > 1:
            # Todas las combinaciones de pares
            for pair in combinations(sorted(concepts), 2):
                cooccurrences[pair] += 1

    # Filtrar: solo pares con al menos 2 co-ocurrencias
    min_cooccurrence = 2
    filtered_cooccurrences = {k: v for k, v in cooccurrences.items()
                             if v >= min_cooccurrence}

    if not filtered_cooccurrences:
        print("⚠️  No hay co-ocurrencias suficientes (min=2)")
        return None

    # Crear grafo
    G = nx.Graph()
    for (c1, c2), weight in filtered_cooccurrences.items():
        G.add_edge(c1, c2, weight=weight)

    # Calcular centralidad (importancia de cada concept)
    degree_centrality = nx.degree_centrality(G)

    # Visualización
    fig, ax = plt.subplots(figsize=(18, 14))

    # Layout físico
    pos = nx.spring_layout(G, k=0.5, iterations=50, seed=42)

    # Tamaño de nodos proporcional a centralidad
    node_sizes = [5000 * degree_centrality[node] for node in G.nodes()]

    # Ancho de aristas proporcional a co-ocurrencias
    edges = G.edges()
    weights = [G[u][v]['weight'] for u, v in edges]
    max_weight = max(weights) if weights else 1
    edge_widths = [3 * (w / max_weight) for w in weights]

    # Dibujar aristas
    nx.draw_networkx_edges(
        G, pos,
        width=edge_widths,
        alpha=0.3,
        edge_color='gray',
        ax=ax
    )

    # Dibujar nodos
    nx.draw_networkx_nodes(
        G, pos,
        node_size=node_sizes,
        node_color='#3498db',
        alpha=0.7,
        edgecolors='black',
        linewidths=1.5,
        ax=ax
    )

    # Etiquetas: top 30 nodos más centrales
    top_nodes = sorted(degree_centrality, key=degree_centrality.get, reverse=True)[:30]
    labels = {node: node for node in top_nodes}

    nx.draw_networkx_labels(
        G, pos, labels,
        font_size=9,
        font_weight='bold',
        font_family='sans-serif',
        ax=ax
    )

    # Título
    ax.set_title(
        f'Concept Co-occurrence Network\n'
        f'{len(G.nodes())} concepts · {len(G.edges())} connections · '
        f'Minimum co-occurrence: {min_cooccurrence}',
        fontsize=16,
        fontweight='bold',
        pad=20
    )

    # Estadísticas de red
    density = nx.density(G)
    avg_degree = sum(dict(G.degree()).values()) / len(G.nodes()) if G.nodes() else 0

    stats_text = f"Network density: {density:.3f}\n"
    stats_text += f"Avg degree: {avg_degree:.1f}\n"
    stats_text += f"Components: {nx.number_connected_components(G)}"

    ax.text(0.02, 0.98, stats_text, transform=ax.transAxes,
           fontsize=11, verticalalignment='top',
           bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.7))

    ax.axis('off')

    output_path = os.path.join(output_dir, 'concept_cooccurrence.png')
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()

    print(f"✓ Red de co-ocurrencias: {len(G.nodes())} concepts, {len(G.edges())} conexiones")

    return output_path


def generate_concept_frequency(papers_df: pd.DataFrame, output_dir: str, top_n: int = 30) -> str:
    """
    Genera gráfico de barras horizontales con los concepts más frecuentes.
    """

    all_concepts = extract_concepts_from_csv(papers_df)

    # Contar frecuencias
    concept_counts = Counter()
    for concepts in all_concepts:
        concept_counts.update(concepts)

    if not concept_counts:
        print("⚠️  No hay concepts para analizar")
        return None

    # Top N concepts
    top_concepts = concept_counts.most_common(top_n)
    concepts, counts = zip(*top_concepts)

    # Visualización
    fig, ax = plt.subplots(figsize=(12, max(10, len(concepts) * 0.35)))

    y_pos = np.arange(len(concepts))
    colors = plt.cm.viridis(np.linspace(0.3, 0.9, len(concepts)))

    bars = ax.barh(y_pos, counts, color=colors, alpha=0.8,
                  edgecolor='black', linewidth=0.8)

    ax.set_yticks(y_pos)
    ax.set_yticklabels(concepts, fontsize=10)
    ax.invert_yaxis()
    ax.set_xlabel('Frequency', fontsize=12, fontweight='bold')
    ax.set_title(f'Top {top_n} Most Frequent Concepts',
                fontsize=14, fontweight='bold', pad=15)
    ax.grid(axis='x', alpha=0.3, linestyle='--')
    ax.spines['top'].set_visible(False)
    ax.spines['right'].set_visible(False)

    # Valores al final de barras
    for i, (bar, count) in enumerate(zip(bars, counts)):
        ax.text(count + max(counts)*0.01, i, str(count),
               va='center', fontsize=9, fontweight='bold')

    output_path = os.path.join(output_dir, 'concept_frequency.png')
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()

    print(f"✓ Frecuencia de concepts: top {len(concepts)}")

    return output_path

def calculate_statistics(papers_df: pd.DataFrame) -> dict:
    """Calcula estadísticas descriptivas."""
    stats = {}

    # Básicas
    stats['total_papers'] = len(papers_df)
    stats['with_doi'] = int(papers_df['doi'].notna().sum())
    stats['with_abstract'] = int(papers_df['abstract'].notna().sum())
    stats['open_access'] = int(papers_df['open_access'].sum())

    # Temporales
    if not papers_df['year'].isna().all():
        stats['year_min'] = int(papers_df['year'].min())
        stats['year_max'] = int(papers_df['year'].max())
        stats['year_median'] = int(papers_df['year'].median())
    else:
        stats['year_min'] = stats['year_max'] = stats['year_median'] = None

    # Citaciones (solo OpenAlex, PubMed siempre tiene None)
    oa_papers = papers_df[papers_df['database'] == 'OpenAlex'] if 'database' in papers_df.columns else papers_df
    citations = oa_papers['cited_by_count'].dropna()

    if len(citations) > 0:
        stats['citations_mean'] = float(citations.mean())
        stats['citations_median'] = float(citations.median())
        stats['citations_max'] = int(citations.max())
        stats['citations_min'] = int(citations.min())
    else:
        stats['citations_mean'] = stats['citations_median'] = None
        stats['citations_min'] = None

    # Top journals
    top_sources = papers_df['source'].value_counts().head(10)
    stats['top_sources'] = list(zip(top_sources.index, top_sources.values))

    # Top cited
    top_cited = papers_df.nlargest(10, 'cited_by_count')[['title', 'cited_by_count', 'year']]
    stats['top_cited'] = top_cited.to_dict('records')

    return stats


def generate_latex_report(summary_data: dict, arq_data: dict, papers_df: pd.DataFrame,
                          map_results: list, output_path: str, seed_prompt: str = None,
                          prisma_checklist: list = None, prisma_diagram: bool = True,
                          syntheses: list = None, gaps: dict = None) -> str:
    """Genera reporte LaTeX mejorado."""

    timestamp = summary_data.get('timestamp', datetime.now().strftime("%Y%m%d_%H%M%S"))
    rqs = arq_data['research_questions']
    keywords = arq_data['keywords']
    assignments = summary_data['assignments']

    search_query = None
    try:
        qsp_path = summary_data.get('source_qsp')
        if qsp_path and os.path.exists(qsp_path):
            with open(qsp_path, 'r', encoding='utf-8') as f:
                qsp_data = json.load(f)
                search_query = qsp_data.get('boolean_query')
    except Exception as e:
        print(f"⚠️  No se pudo cargar la query de búsqueda: {e}")

    # Calcular estadísticas
    stats = calculate_statistics(papers_df)

    # Generar gráficos
    output_dir = os.path.dirname(output_path)
    temporal_plot = generate_temporal_distribution(papers_df, output_dir)
    cumulative_plot = generate_cumulative_distribution(papers_df, output_dir)
    publications_rq_year = generate_publications_by_rq_year(papers_df, assignments, rqs, output_dir)
    citations_year_plot = generate_citation_by_year(papers_df, output_dir)
    citation_plot = generate_citation_distribution(papers_df, output_dir)
    rq_plot = generate_rq_distribution(assignments, rqs, output_dir)
    keyword_freq_plot = generate_concept_frequency(papers_df, output_dir, top_n=30)
    cooccurrence_plot = generate_concept_cooccurrence(papers_df, output_dir)

    # Crear diccionario de reasoning por paper_id
    reasoning_map = {}
    for result in map_results:
        paper_id = result.get('paper_id')
        reasoning_map[int(paper_id)] = {
            'reasoning': result.get('reasoning', ''),
            'confidence': result.get('confidence', 'n/a')
        }

    # ============================================================
    # DOCUMENTO LATEX
    # ============================================================

    latex_content = r"""\documentclass[11pt,a4paper]{article}

% Paquetes
\usepackage[utf8]{inputenc}
\usepackage[spanish,english]{babel}
\usepackage{geometry}
\usepackage{hyperref}
\usepackage{graphicx}
\usepackage{fancyhdr}
\usepackage{booktabs}
\usepackage{longtable}
\usepackage{enumitem}
\usepackage{xcolor}
\usepackage{float}
\usepackage{amssymb}

% Configuración
\geometry{margin=2.5cm}
\setlength{\headheight}{14pt}

\pagestyle{fancy}
\fancyhf{}
\fancyhead[L]{PALET Literature Review Report}
\fancyhead[R]{\thepage}

\hypersetup{
    colorlinks=true,
    linkcolor=blue,
    urlcolor=blue,
    citecolor=blue
}

% Comandos personalizados
\newcommand{\rqbox}[2]{
    \noindent\fcolorbox{black}{gray!10}{
        \parbox{\textwidth}{
            \textbf{#1} \\[0.5em]
            #2
        }
    }
}

\begin{document}

% Portada
\begin{titlepage}
    \centering
    \vspace*{2cm}

    {\Huge\bfseries Systematic Literature Review Report\\}
    \vspace{0.5cm}
    {\Large Generated with PALET\\}
    \vspace{1cm}
    {\large Prompt-based Automated Literature Extraction Tool\\}
    {Author: Ricardo MdV Perancho}
    \vspace{2cm}

"""

    latex_content += f"    {{\\large Generated: {timestamp}\\\\}}\n"
    latex_content += f"    {{\\large Total Papers: {stats['total_papers']}\\\\}}\n"
    latex_content += f"    {{\\large Research Questions: {len(rqs)}\\\\}}\n"

    latex_content += r"""
    \vfill
\end{titlepage}

\tableofcontents
\newpage

"""

    # ============================================================
    # SECCIÓN 1: SEED PROMPT
    # ============================================================

    if seed_prompt and seed_prompt != "Seed prompt not directly available in pipeline outputs.":
        latex_content += r"""\section{Original Seed Prompt}

The following seed prompt was provided to initiate the systematic review:

\begin{quote}
\itshape
"""
        latex_content += escape_latex(seed_prompt)
        latex_content += r"""
\end{quote}

\newpage

"""

    # ============================================================
    # SECCIÓN 2: RESEARCH QUESTIONS
    # ============================================================

    latex_content += r"""\section{Research Questions}

The following research questions were extracted and refined from the seed prompt:

\bigskip

"""

    for i, rq in enumerate(rqs, 1):
        # Limpiar duplicación RQi:
        rq_clean = rq.replace(f"RQ{i}:", "").strip()
        rq_escaped = escape_latex(rq_clean)
        count = len(assignments.get(f"RQ{i}", []))

        latex_content += f"\\rqbox{{RQ{i} ({count} papers)}}{{{rq_escaped}}}\n\n"
        latex_content += r"\bigskip" + "\n\n"

    latex_content += r"\newpage" + "\n\n"

    # ============================================================
    # SECCIÓN 3: KEYWORDS
    # ============================================================

    latex_content += r"""\section{Search Strategy}

\subsection{Keywords}

The following keywords were used to construct the boolean search query:

\medskip

\noindent\textit{
"""

    keywords_escaped = [escape_latex(kw) for kw in keywords]
    latex_content += ", ".join(keywords_escaped)

    latex_content += r"""}

"""

    # Añadir la query de búsqueda si está disponible
    if search_query:
        latex_content += r"""
\subsection{Boolean Search Query}

The following boolean query was generated and executed in OpenAlex:

\begin{quote}
\ttfamily
"""
        latex_content += escape_latex(search_query)
        latex_content += r"""
\end{quote}

"""

    latex_content += r"\newpage" + "\n\n"

    # ============================================================
    # SECCIÓN 3b: PRISMA COMPLIANCE
    # ============================================================

    latex_content += r"\section{PRISMA-ScR Compliance}" + "\n\n"

    # Diagrama de flujo
    prisma_flow_path = os.path.join(os.path.dirname(output_path), 'prisma_flow.png')
    if prisma_diagram and os.path.exists(prisma_flow_path):
        latex_content += r"""
\subsection{Flow Diagram}

\begin{figure}[H]
\centering
\includegraphics[width=0.85\textwidth]{prisma_flow.png}
\caption{PRISMA-ScR flow diagram showing the number of records identified,
screened, assessed for eligibility, and included in the synthesis.}
\end{figure}

"""
    else:
        latex_content += "\\textit{PRISMA flow diagram not available.}\n\n"

    # Checklist de conformidad
    if prisma_checklist:
        latex_content += r"\subsection{Conformity Checklist}" + "\n\n"
        latex_content += r"""
\begin{table}[H]
\centering
\begin{tabular}{p{7cm}cp{5.5cm}}
\toprule
\textbf{Item} & \textbf{Status} & \textbf{Note} \\
\midrule
"""
        for item, passes, note in prisma_checklist:
            status = r"\checkmark" if passes else r"\times"
            latex_content += f"{escape_latex(item)} & ${status}$ & {escape_latex(note)} \\\\\n"

        passed = sum(1 for _, p, _ in prisma_checklist if p)
        latex_content += r"\bottomrule" + "\n"
        latex_content += r"\end{tabular}" + "\n"
        latex_content += f"\\caption{{PRISMA-ScR conformity: {passed}/{len(prisma_checklist)} items met}}\n"
        latex_content += r"\end{table}" + "\n\n"

    # Criterios de inclusión/exclusión
    inclusion = arq_data.get('inclusion_criteria', [])
    exclusion = arq_data.get('exclusion_criteria', [])

    if inclusion or exclusion:
        latex_content += r"\subsection{Inclusion and Exclusion Criteria}" + "\n\n"

        if inclusion:
            latex_content += r"\textbf{Inclusion criteria:}" + "\n"
            latex_content += r"\begin{itemize}[leftmargin=*]" + "\n"
            for criterion in inclusion:
                latex_content += f"\\item {escape_latex(criterion)}\n"
            latex_content += r"\end{itemize}" + "\n\n"

        if exclusion:
            latex_content += r"\textbf{Exclusion criteria:}" + "\n"
            latex_content += r"\begin{itemize}[leftmargin=*]" + "\n"
            for criterion in exclusion:
                latex_content += f"\\item {escape_latex(criterion)}\n"
            latex_content += r"\end{itemize}" + "\n\n"

    latex_content += r"\newpage" + "\n\n"
    # ============================================================
    # SECCIÓN 4: SUMMARY STATISTICS
    # ============================================================

    latex_content += r"""\section{Summary Statistics}

\subsection{Overview}

\begin{table}[h]
\centering
\begin{tabular}{lr}
\toprule
\textbf{Metric} & \textbf{Value} \\
\midrule
"""

    latex_content += f"Total papers retrieved & {stats['total_papers']} \\\\\n"
    latex_content += f"Papers with DOI & {stats['with_doi']} ({stats['with_doi']/stats['total_papers']*100:.1f}\\%) \\\\\n"
    latex_content += f"Papers with abstract & {stats['with_abstract']} ({stats['with_abstract']/stats['total_papers']*100:.1f}\\%) \\\\\n"
    latex_content += f"Open Access papers & {stats['open_access']} ({stats['open_access']/stats['total_papers']*100:.1f}\\%) \\\\\n"

    if stats['year_min']:
        latex_content += f"Year range & {stats['year_min']}--{stats['year_max']} \\\\\n"
        latex_content += f"Median year & {stats['year_median']} \\\\\n"

    unmatched = len(assignments.get('unmatched', []))
    latex_content += f"Unmatched papers & {unmatched} ({unmatched/stats['total_papers']*100:.1f}\\%) \\\\\n"

    latex_content += r"""\bottomrule
\end{tabular}
\caption{Overview of retrieved literature}
\end{table}

"""

    # Estadísticas de citaciones
    if stats['citations_mean']:
        latex_content += r"""\subsection{Citation Statistics}

\begin{table}[h]
\centering
\begin{tabular}{lr}
\toprule
\textbf{Metric} & \textbf{Citations} \\
\midrule
"""
        latex_content += f"Mean & {stats['citations_mean']:.1f} \\\\\n"
        latex_content += f"Median & {stats['citations_median']:.0f} \\\\\n"
        latex_content += f"Maximum & {stats['citations_max']} \\\\\n"
        latex_content += f"Minimum & {stats['citations_min']} \\\\\n"

        latex_content += r"""\bottomrule
\end{tabular}
\caption{Citation statistics}
\end{table}

"""

    # Top journals
    if stats['top_sources']:
        latex_content += r"""\subsection{Top Publication Venues}

\begin{longtable}{lc}
\toprule
\textbf{Source} & \textbf{Papers} \\
\midrule
\endhead
"""

        for source, count in stats['top_sources'][:10]:
            source_escaped = escape_latex(source) if source else "Unknown"
            latex_content += f"{source_escaped} & {count} \\\\\n"

        latex_content += r"""\bottomrule
\caption{Most frequent publication venues}
\end{longtable}

"""

# Gráficos
    latex_content += r"""\subsection{Temporal Analysis}

\begin{figure}[H]
\centering
\includegraphics[width=0.95\textwidth]{temporal_distribution.png}
\caption{Annual distribution of papers}
\end{figure}

\begin{figure}[H]
\centering
\includegraphics[width=0.95\textwidth]{publications_by_rq_year.png}
\caption{Annual publication trends by research question. Each line represents papers assigned to a specific RQ.}
\end{figure}

\begin{figure}[H]
\centering
\includegraphics[width=0.95\textwidth]{cumulative_distribution.png}
\caption{Cumulative growth of literature over time}
\end{figure}

\begin{figure}[H]
\centering
\includegraphics[width=0.95\textwidth]{citations_by_year.png}
\caption{Citation patterns across publication years}
\end{figure}

\subsection{Citation Analysis}

\begin{figure}[H]
\centering
\includegraphics[width=0.95\textwidth]{citation_distribution.png}
\caption{Distribution of citation counts}
\end{figure}

\subsection{Coverage}

\begin{figure}[H]
\centering
\includegraphics[width=0.85\textwidth]{rq_distribution.png}
\caption{Papers assigned to each research question}
\end{figure}

\begin{figure}[H]
\centering
\includegraphics[width=0.85\textwidth]{concept_frequency.png}
\caption{Most frequent keywords in the retrieved literature.}
\end{figure}

\begin{figure}[H]
\centering
\includegraphics[width=0.85\textwidth]{concept_cooccurrence.png}
\caption{Keyword co-occurrence network. Node size indicates centrality (importance),
edge width indicates co-occurrence frequency. Only keywords appearing together at least twice are shown.}
\end{figure}

\newpage

"""

    # ============================================================
    # SECCIÓN 5: PAPERS POR RQ
    # ============================================================

    latex_content += r"""\section{Papers by Research Question}

"""

    for i, rq in enumerate(rqs, 1):
        rq_key = f"RQ{i}"
        paper_ids = assignments.get(rq_key, [])

        rq_clean = rq.replace(f"RQ{i}:", "").strip()
        rq_escaped = escape_latex(rq_clean)

        latex_content += f"\\subsection{{{rq_escaped}}}\n\n"
        latex_content += f"\\textit{{Research Question {i}}} \\\\\n"
        latex_content += f"Papers assigned: {len(paper_ids)}\n\n"

        if not paper_ids:
            latex_content += "\\textit{No papers were assigned to this research question.}\n\n"
            continue

        latex_content += r"\begin{enumerate}[leftmargin=*, itemsep=1em]" + "\n"

        for paper_id in paper_ids:
            try:
                paper = papers_df.iloc[int(paper_id)]
            except (IndexError, ValueError, KeyError):
                continue

            # Metadata del paper
            title = escape_latex(paper.get('title', 'Untitled'))
            authors = escape_latex(paper.get('authors', 'Unknown'))
            year = paper.get('year', 'N/A')
            doi = paper.get('doi')

            # Reasoning de Claude
            paper_reasoning = reasoning_map.get(int(paper_id), {})
            reasoning_text = escape_latex(paper_reasoning.get('reasoning', 'N/A'))
            confidence = paper_reasoning.get('confidence', 'n/a')

            latex_content += f"\\item \\textbf{{{title}}} \\\\\n"
            latex_content += f"      {authors} ({year}) \\\\\n"

            if pd.notna(doi):
                doi_escaped = escape_latex(doi)
                latex_content += f"      DOI: \\href{{https://doi.org/{doi_escaped}}}{{{doi_escaped}}} \\\\\n"

            latex_content += f"      \\textit{{Assignment rationale}} (confidence: {confidence}): {reasoning_text}\n\n"

        latex_content += r"\end{enumerate}" + "\n\n"
        latex_content += r"\newpage" + "\n\n"

    # ============================================================
    # SECCIÓN 6: TOP CITED PAPERS
    # ============================================================

    if stats['top_cited'] and len(stats['top_cited']) > 0:
        latex_content += r"""\section{Most Cited Papers}

The following papers have received the highest number of citations:

\begin{enumerate}[leftmargin=*]
"""

        for paper_dict in stats['top_cited']:
            title = escape_latex(paper_dict.get('title', 'Untitled'))
            citations = int(paper_dict.get('cited_by_count', 0))
            year = paper_dict.get('year', 'N/A')

            latex_content += f"\\item \\textbf{{{title}}} ({year}) --- {citations} citations\n"

        latex_content += r"""\end{enumerate}

\newpage

"""

    # ============================================================
    # SECCIÓN 7: UNMATCHED PAPERS
    # ============================================================

    unmatched_ids = assignments.get('unmatched', [])

    if unmatched_ids:
        latex_content += r"""\section{Unmatched Papers}

The following papers could not be confidently assigned to any research question:

\begin{itemize}[leftmargin=*]
"""

        for paper_id in unmatched_ids:
            try:
                paper = papers_df.iloc[int(paper_id)]
            except (IndexError, ValueError, KeyError):
                continue

            title = escape_latex(paper.get('title', 'Untitled'))
            authors = escape_latex(paper.get('authors', 'Unknown'))
            year = paper.get('year', 'N/A')

            latex_content += f"\\item \\textbf{{{title}}} --- {authors} ({year})\n"

        latex_content += r"""\end{itemize}

"""
    # ============================================================
    # SECCIÓN 8: SÍNTESIS NARRATIVA POR RQ
    # ============================================================

    if syntheses:
        latex_content += r"\section{Narrative Synthesis by Research Question}" + "\n\n"
        latex_content += (
            r"\textit{The following syntheses were generated automatically by PALET "
            r"based on the papers assigned to each Research Question. "
            r"They are intended as a scholarly scaffold for the researcher's own analysis.}"
            + "\n\n"
        )

        for synth in syntheses:
            rq_idx   = synth.get('rq_index', '?')
            rq_text  = escape_latex(synth.get('rq', ''))
            conf     = synth.get('confidence', 'n/a')
            n_used   = synth.get('paper_count_used', 0)
            n_total  = synth.get('paper_count_assigned', n_used)
            s        = synth.get('synthesis', {})

            latex_content += f"\\subsection{{RQ{rq_idx}: {rq_text}}}\n\n"
            latex_content += (
                f"\\textit{{Confidence: {conf} | "
                f"Papers used: {n_used}/{n_total}}}\n\n"
            )

            conf_note = escape_latex(synth.get('confidence_note', ''))
            if conf_note:
                latex_content += f"\\textit{{{conf_note}}}\n\n"

            components = [
                ("Overview",                 s.get('overview', '')),
                ("Main Findings",            s.get('main_findings', '')),
                ("Tensions and Contradictions", s.get('tensions', '')),
                ("Methodological Patterns",  s.get('methodological_patterns', '')),
                ("Emerging Themes",          s.get('emerging_themes', '')),
                ("Synthesis Statement",      s.get('synthesis_statement', '')),
            ]

            for label, content in components:
                if content and content != 'N/A':
                    latex_content += f"\\textbf{{{label}}}\n\n"
                    latex_content += escape_latex(content) + "\n\n"

            latex_content += r"\newpage" + "\n\n"

    # ============================================================
    # SECCIÓN 9: DETECCIÓN DE GAPS
    # ============================================================

    if gaps and 'gap_analysis' in gaps:
        ga = gaps['gap_analysis']
        latex_content += r"\section{Literature Gap Analysis}" + "\n\n"
        latex_content += (
            r"\textit{The following gap analysis identifies underexplored areas "
            r"in the retrieved literature. Gaps are framed as research opportunities "
            r"that the researcher may consider addressing.}"
            + "\n\n"
        )

        gap_sections = [
            ("Coverage Overview",        ga.get('coverage_overview', '')),
            ("Geographic Gaps",          ga.get('geographic_gaps', '')),
            ("Temporal Gaps",            ga.get('temporal_gaps', '')),
            ("Methodological Gaps",      ga.get('methodological_gaps', '')),
            ("Thematic Gaps",            ga.get('thematic_gaps', '')),
            ("Cross-RQ Gaps",            ga.get('cross_rq_gaps', '')),
        ]

        for label, content in gap_sections:
            if content and content != 'N/A':
                latex_content += f"\\subsection{{{label}}}\n\n"
                latex_content += escape_latex(content) + "\n\n"

        # Oportunidades prioritarias
        opportunities = ga.get('priority_opportunities', [])
        if opportunities:
            latex_content += r"\subsection{Priority Research Opportunities}" + "\n\n"
            latex_content += r"\begin{enumerate}[leftmargin=*, itemsep=1em]" + "\n"
            for opp in opportunities:
                title = escape_latex(opp.get('title', ''))
                desc  = escape_latex(opp.get('description', ''))
                latex_content += f"\\item \\textbf{{{title}}} \\\\\n{desc}\n\n"
            latex_content += r"\end{enumerate}" + "\n\n"

        # Caveats
        caveats = ga.get('caveats', '')
        if caveats and caveats != 'N/A':
            latex_content += r"\subsection{Caveats and Limitations}" + "\n\n"
            latex_content += escape_latex(caveats) + "\n\n"

        latex_content += r"\newpage" + "\n\n"

    # Cerrar documento
    latex_content += r"""\end{document}
"""

    # Guardar
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(latex_content)

    print(f"✓ LaTeX generado: {output_path}")

    return output_path


def compile_pdf(tex_path: str) -> str:
    """Compila LaTeX a PDF."""
    work_dir = os.path.dirname(tex_path)
    tex_filename = os.path.basename(tex_path)

    print(f"\nCompilando PDF (puede tardar 30-60s)...")

    for i in range(2):
        try:
            result = subprocess.run(
                ['pdflatex', '-interaction=nonstopmode', tex_filename],
                cwd=work_dir,
                capture_output=True,
                text=True,
                timeout=90
            )

            # No considerar warnings como errores
            # Solo verificar que el PDF se generó

        except FileNotFoundError:
            print("\nERROR: pdflatex no encontrado")
            sys.exit(1)
        except subprocess.TimeoutExpired:
            print("\nERROR: Timeout en compilación")
            sys.exit(1)

    pdf_path = tex_path.replace('.tex', '.pdf')

    if os.path.exists(pdf_path):
        print(f"✓ PDF generado: {pdf_path}")

        # Limpiar auxiliares
        for ext in ['.aux', '.log', '.out', '.toc']:
            aux_file = tex_path.replace('.tex', ext)
            if os.path.exists(aux_file):
                os.remove(aux_file)

        return pdf_path
    else:
        raise RuntimeError("PDF no generado")


if __name__ == "__main__":
    print("="*70)
    print("  GENERADOR DE REPORTE PDF - Versión Mejorada")
    print("="*70)

    results_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'results')

    if not os.path.exists(results_dir):
        print("\nERROR: No existe results/")
        sys.exit(1)

    # Buscar archivos
    summary_files = [f for f in os.listdir(results_dir) if f.startswith('summary_')]

    if not summary_files:
        print("\nERROR: No se encontró summary")
        sys.exit(1)

    summary_file = sorted(summary_files, reverse=True)[0]
    summary_path = os.path.join(results_dir, summary_file)

    print(f"\nUsando: {summary_file}")

    # Cargar datos
    summary_data = load_map_summary(summary_path)

    # Buscar MAP results detallados
    timestamp = summary_data.get('timestamp')
    map_results_file = f"map_results_{timestamp}.json"

    outputs_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'outputs', 'json')
    map_results_path = os.path.join(outputs_dir, map_results_file)

    if not os.path.exists(map_results_path):
        print(f"\nWARNING: No se encontró {map_results_file}")
        print("El reporte no incluirá reasoning de Claude")
        map_results = []
    else:
        map_results = load_map_results(map_results_path)
        print(f"MAP results cargados: {len(map_results)} papers")

    arq_path = summary_data.get('source_arq')
    csv_path = summary_data.get('source_csv')

    if not arq_path or not os.path.exists(arq_path):
        print("\nERROR: ARQ no encontrado")
        sys.exit(1)

    if not csv_path or not os.path.exists(csv_path):
        print("\nERROR: CSV no encontrado")
        sys.exit(1)

    arq_data = load_arq_output(arq_path)
    papers_df = load_papers_csv(csv_path)

    print(f"Papers: {len(papers_df)}, RQs: {len(arq_data['research_questions'])}")

    # Generar LaTeX
    tex_filename = f"report_{timestamp}.tex"
    tex_path = os.path.join(results_dir, tex_filename)

    generate_latex_report(summary_data, arq_data, papers_df, map_results, tex_path)

    # Compilar
    try:
        pdf_path = compile_pdf(tex_path)

        print("\n" + "="*70)
        print("  REPORTE COMPLETADO")
        print("="*70)
        print(f"\nPDF: {pdf_path}")

        subprocess.run(['open', pdf_path], check=False)

    except Exception as e:
        print(f"\nError: {e}")
        print(f"LaTeX disponible: {tex_path}")
        sys.exit(1)
