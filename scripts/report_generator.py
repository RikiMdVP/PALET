# scripts/report_generator.py
# Generador de reporte PDF en LaTeX

import os
import sys
import json
import pandas as pd
from datetime import datetime
import subprocess


def load_map_summary(summary_path: str) -> dict:
    """Carga resumen de MAP."""
    with open(summary_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_arq_output(arq_path: str) -> dict:
    """Carga output de ARQ."""
    with open(arq_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_papers_csv(csv_path: str) -> pd.DataFrame:
    """Carga CSV de papers."""
    return pd.read_csv(csv_path)


def escape_latex(text: str) -> str:
    """Escapa caracteres especiales de LaTeX."""
    if pd.isna(text):
        return ""

    text = str(text)

    # Caracteres especiales LaTeX
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


def generate_latex_report(summary_data: dict, arq_data: dict, papers_df: pd.DataFrame,
                          output_path: str) -> str:
    """
    Genera archivo LaTeX del reporte.

    Returns:
        Path al archivo .tex generado
    """

    # Metadata
    timestamp = summary_data.get('timestamp', datetime.now().strftime("%Y%m%d_%H%M%S"))
    rqs = arq_data['research_questions']
    keywords = arq_data['keywords']
    assignments = summary_data['assignments']

    # Comenzar documento LaTeX
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

% Configuración de página
\geometry{margin=2.5cm}
\pagestyle{fancy}
\fancyhf{}
\fancyhead[L]{PALET Literature Review Report}
\fancyhead[R]{\thepage}

% Configuración hyperref
\hypersetup{
    colorlinks=true,
    linkcolor=blue,
    urlcolor=blue,
    citecolor=blue
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
    \vspace{2cm}

"""

    latex_content += f"    {{\\large Generated: {timestamp}\\\\}}\n"
    latex_content += f"    {{\\large Total Papers: {len(papers_df)}\\\\}}\n"
    latex_content += f"    {{\\large Research Questions: {len(rqs)}\\\\}}\n"

    latex_content += r"""
    \vfill
\end{titlepage}

\tableofcontents
\newpage

"""

    # Sección 1: Research Questions
    latex_content += r"""\section{Research Questions}

The following research questions were extracted from the seed prompt:

\begin{enumerate}[leftmargin=*]
"""

    for i, rq in enumerate(rqs, 1):
    # Eliminar prefijo "RQX:" si ya existe
        rq_clean = rq.replace(f"RQ{i}:", "").strip()
        rq_escaped = escape_latex(rq_clean)
        count = len(assignments.get(f"RQ{i}", []))
        latex_content += f"    \\item \\textbf{{RQ{i}}} ({count} papers): {rq_escaped}\n"

    latex_content += r"""\end{enumerate}

"""

    # Sección 2: Keywords
    latex_content += r"""\section{Keywords Used in Search}

The following keywords were used to construct the search query:

\begin{itemize}[leftmargin=*]
"""

    for keyword in keywords:
        kw_escaped = escape_latex(keyword)
        latex_content += f"    \\item {kw_escaped}\n"

    latex_content += r"""\end{itemize}

\newpage

"""

    # Sección 3: Summary Statistics
    latex_content += r"""\section{Summary Statistics}

"""

    total_papers = len(papers_df)
    papers_with_doi = papers_df['doi'].notna().sum()
    papers_with_abstract = papers_df['abstract'].notna().sum()

    if not papers_df['year'].isna().all():
        year_min = int(papers_df['year'].min())
        year_max = int(papers_df['year'].max())
        year_range = f"{year_min}--{year_max}"
    else:
        year_range = "N/A"

    latex_content += r"""\begin{table}[h]
\centering
\begin{tabular}{lr}
\toprule
\textbf{Metric} & \textbf{Value} \\
\midrule
"""

    latex_content += f"Total papers & {total_papers} \\\\\n"
    latex_content += f"Papers with DOI & {papers_with_doi} \\\\\n"
    latex_content += f"Papers with abstract & {papers_with_abstract} \\\\\n"
    latex_content += f"Year range & {year_range} \\\\\n"

    unmatched = len(assignments.get('unmatched', []))
    latex_content += f"Unmatched papers & {unmatched} \\\\\n"

    latex_content += r"""\bottomrule
\end{tabular}
\caption{Overview of retrieved literature}
\end{table}

\newpage

"""

# Sección 4: Papers por Research Question
    latex_content += r"""\section{Papers by Research Question}

"""
    for i, rq in enumerate(rqs, 1):
        rq_key = f"RQ{i}"
        paper_ids = assignments.get(rq_key, [])

        rq_clean = rq.replace(f"RQ{i}:", "").strip()
        rq_escaped = escape_latex(rq_clean)
        latex_content += f"\\subsection{{RQ{i}: {rq_escaped}}}\n\n"

        if not paper_ids:
            latex_content += "No papers were assigned to this research question.\n\n"
            continue

        latex_content += f"Total papers assigned: {len(paper_ids)}\n\n"

        # Listar papers
        for paper_id in paper_ids:
            try:
                # Acceder por iloc directamente sin validación de índice
                paper = papers_df.iloc[int(paper_id)]
            except (IndexError, ValueError, KeyError):
                print(f"Warning: Paper ID {paper_id} not found in DataFrame")
                continue

            title = escape_latex(paper.get('title', 'Untitled'))
            authors = escape_latex(paper.get('authors', 'Unknown'))
            year = paper.get('year', 'N/A')
            source = escape_latex(paper.get('source', 'Unknown'))
            doi = paper.get('doi')
            abstract = escape_latex(paper.get('abstract', 'No abstract available'))

            # Limitar abstract a 500 caracteres
            if len(abstract) > 500:
                abstract = abstract[:497] + "..."

            latex_content += r"""\begin{itemize}[leftmargin=*]
"""
            latex_content += f"    \\item \\textbf{{{title}}}\\\\\n"
            latex_content += f"          \\textit{{{authors}}} ({year})\\\\\n"
            latex_content += f"          {source}\\\\\n"

            if pd.notna(doi):
                doi_escaped = escape_latex(doi)
                latex_content += f"          DOI: \\href{{https://doi.org/{doi_escaped}}}{{{doi_escaped}}}\\\\\n"

            latex_content += f"          \\textit{{Abstract}}: {abstract}\n"
            latex_content += r"""\end{itemize}

"""

        latex_content += "\\newpage\n\n"

    # Sección 5: Unmatched papers
    unmatched_ids = assignments.get('unmatched', [])

    if unmatched_ids:
        latex_content += r"""\section{Unmatched Papers}

The following papers could not be confidently assigned to any research question:

"""

        for paper_id in unmatched_ids:
            try:
                paper = papers_df.iloc[int(paper_id)]
            except (IndexError, ValueError, KeyError):
                continue

            title = escape_latex(paper.get('title', 'Untitled'))
            authors = escape_latex(paper.get('authors', 'Unknown'))
            year = paper.get('year', 'N/A')

            latex_content += f"\\begin{{itemize}}[leftmargin=*]\n"
            latex_content += f"    \\item \\textbf{{{title}}}\\\\\n"
            latex_content += f"          {authors} ({year})\n"
            latex_content += f"\\end{{itemize}}\n\n"

    # Cerrar documento
    latex_content += r"""\end{document}
"""

    # Guardar archivo .tex
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(latex_content)

    print(f"✓ Archivo LaTeX generado: {output_path}")

    return output_path


def compile_pdf(tex_path: str) -> str:
    """
    Compila archivo .tex a PDF usando pdflatex.

    Returns:
        Path al PDF generado
    """

    # Directorio del archivo .tex
    work_dir = os.path.dirname(tex_path)
    tex_filename = os.path.basename(tex_path)

    print(f"\nCompilando PDF...")
    print(f"Directorio: {work_dir}")

    # Compilar dos veces para resolver referencias
    for i in range(2):
        try:
            result = subprocess.run(
                ['pdflatex', '-interaction=nonstopmode', tex_filename],
                cwd=work_dir,
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode != 0:
                print(f"\nError en compilación LaTeX (intento {i+1}):")
                print(result.stdout[-1000:])  # Últimas 1000 chars del log

                if i == 0:
                    print("Intentando segunda compilación...")
                    continue
                else:
                    raise RuntimeError("Compilación LaTeX falló")

        except FileNotFoundError:
            print("\nERROR: pdflatex no encontrado")
            print("Instala LaTeX:")
            print("  macOS: brew install basictex")
            print("  Linux: sudo apt-get install texlive")
            sys.exit(1)
        except subprocess.TimeoutExpired:
            print("\nERROR: Compilación LaTeX timeout")
            sys.exit(1)

    # Path al PDF generado
    pdf_path = tex_path.replace('.tex', '.pdf')

    if os.path.exists(pdf_path):
        print(f"\n✓ PDF generado: {pdf_path}")

        # Limpiar archivos auxiliares
        for ext in ['.aux', '.log', '.out', '.toc']:
            aux_file = tex_path.replace('.tex', ext)
            if os.path.exists(aux_file):
                os.remove(aux_file)

        return pdf_path
    else:
        raise RuntimeError("PDF no se generó correctamente")


if __name__ == "__main__":
    print("="*70)
    print("  GENERADOR DE REPORTE PDF")
    print("="*70)

    # Buscar summary más reciente en results/
    results_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'results')

    if not os.path.exists(results_dir):
        print("\nERROR: No existe directorio results/")
        print("Ejecuta primero: python palet.py --seed-prompt ...")
        sys.exit(1)

    summary_files = [f for f in os.listdir(results_dir) if f.startswith('summary_')]

    if not summary_files:
        print("\nERROR: No se encontraron archivos summary en results/")
        sys.exit(1)

    # Usar el más reciente
    summary_file = sorted(summary_files, reverse=True)[0]
    summary_path = os.path.join(results_dir, summary_file)

    print(f"\nUsando: {summary_file}")

    # Cargar datos
    summary_data = load_map_summary(summary_path)

    # Buscar ARQ correspondiente
    arq_path = summary_data.get('source_arq')
    if not arq_path or not os.path.exists(arq_path):
        print("\nERROR: No se encontró archivo ARQ fuente")
        sys.exit(1)

    arq_data = load_arq_output(arq_path)

    # Buscar CSV correspondiente
    csv_path = summary_data.get('source_csv')
    if not csv_path or not os.path.exists(csv_path):
        print("\nERROR: No se encontró archivo CSV fuente")
        sys.exit(1)

    papers_df = load_papers_csv(csv_path)

    print(f"Papers cargados: {len(papers_df)}")
    print(f"Research Questions: {len(arq_data['research_questions'])}")

    # Generar LaTeX
    timestamp = summary_data.get('timestamp', datetime.now().strftime("%Y%m%d_%H%M%S"))
    tex_filename = f"report_{timestamp}.tex"
    tex_path = os.path.join(results_dir, tex_filename)

    generate_latex_report(summary_data, arq_data, papers_df, tex_path)

    # Compilar PDF
    try:
        pdf_path = compile_pdf(tex_path)

        print("\n" + "="*70)
        print("  REPORTE GENERADO EXITOSAMENTE")
        print("="*70)
        print(f"\nPDF: {pdf_path}")

        # Abrir PDF automáticamente (macOS)
        subprocess.run(['open', pdf_path], check=False)

    except Exception as e:
        print(f"\nError generando PDF: {e}")
        print(f"Archivo LaTeX disponible en: {tex_path}")
        sys.exit(1)
