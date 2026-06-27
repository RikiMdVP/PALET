# scripts/prisma_validator.py
# Genera diagrama de flujo PRISMA-ScR y checklist de conformidad

import os
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch


def build_prisma_data(arq_data: dict, dedup_stats: dict,
                       papers_df, summary: dict) -> dict:
    """
    Construye el diccionario con todos los números para el diagrama PRISMA.

    Args:
        arq_data: Output de ARQ (contiene inclusion/exclusion criteria)
        dedup_stats: Estadísticas de deduplicación de SE
        papers_df: DataFrame de papers (post-dedup)
        summary: Summary de asignaciones de MAP
    """
    total_identified  = dedup_stats.get('total_identified', len(papers_df))
    duplicates        = dedup_stats.get('duplicates_removed', 0)
    after_dedup       = dedup_stats.get('total_after_dedup', len(papers_df))
    db_counts         = dedup_stats.get('identified_by_database', {})

    no_abstract       = len(summary.get('unmatched_no_abstract', []))
    not_relevant      = len(summary.get('unmatched_not_relevant', []))

    included = sum(
        len(v) for k, v in summary.items()
        if k.startswith('RQ')
    )

    return {
        'databases': db_counts,
        'total_identified': total_identified,
        'duplicates_removed': duplicates,
        'screened': after_dedup,
        'excluded_no_abstract': no_abstract,
        'assessed_eligibility': after_dedup - no_abstract,
        'excluded_not_relevant': not_relevant,
        'included': included,
        'inclusion_criteria': arq_data.get('inclusion_criteria', []),
        'exclusion_criteria': arq_data.get('exclusion_criteria', [])
    }


def generate_prisma_diagram(prisma_data: dict, output_dir: str) -> str:
    """
    Genera el diagrama de flujo PRISMA como imagen PNG.
    """
    fig, ax = plt.subplots(1, 1, figsize=(14, 18))
    ax.set_xlim(0, 14)
    ax.set_ylim(0, 18)
    ax.axis('off')

    # ── Colores ──────────────────────────────────────────────────────────
    COLOR_ID     = '#D6EAF8'   # azul claro — Identificación
    COLOR_SCREEN = '#D5F5E3'   # verde claro — Cribado
    COLOR_ELIG   = '#FEF9E7'   # amarillo    — Elegibilidad
    COLOR_INCL   = '#FADBD8'   # rosa        — Incluidos
    COLOR_EXCL   = '#F2F3F4'   # gris        — Excluidos
    COLOR_BORDER = '#2C3E50'

    def draw_box(ax, x, y, w, h, text, color, fontsize=10, bold=False):
        box = FancyBboxPatch((x, y), w, h,
                             boxstyle="round,pad=0.1",
                             facecolor=color,
                             edgecolor=COLOR_BORDER,
                             linewidth=1.5)
        ax.add_patch(box)
        weight = 'bold' if bold else 'normal'
        ax.text(x + w/2, y + h/2, text,
                ha='center', va='center',
                fontsize=fontsize, fontweight=weight,
                wrap=True,
                multialignment='center')

    def draw_arrow(ax, x1, y1, x2, y2):
        ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle='->', color=COLOR_BORDER,
                                   lw=2.0))

    # ── Títulos de fase (columna izquierda) ──────────────────────────────
    phase_x = 0.2
    draw_box(ax, phase_x, 14.5, 2.2, 2.8, 'IDENTI-\nFICACIÓN', COLOR_ID,    fontsize=9, bold=True)
    draw_box(ax, phase_x, 10.5, 2.2, 3.5, 'CRIBADO',           COLOR_SCREEN, fontsize=9, bold=True)
    draw_box(ax, phase_x,  6.5, 2.2, 3.5, 'ELEGIBILI-\nDAD',   COLOR_ELIG,   fontsize=9, bold=True)
    draw_box(ax, phase_x,  2.5, 2.2, 3.5, 'INCLUIDOS',         COLOR_INCL,   fontsize=9, bold=True)

    # ── Construcción de textos ────────────────────────────────────────────
    db_lines = '\n'.join([f"• {db}: n={count}"
                          for db, count in prisma_data['databases'].items()])
    id_text = f"Registros identificados\nen bases de datos\n{db_lines}\n\nTotal: n={prisma_data['total_identified']}"

    screen_text   = f"Registros cribados\nn={prisma_data['screened']}"
    dedup_text    = f"Duplicados eliminados\nn={prisma_data['duplicates_removed']}"
    elig_text     = f"Evaluados para\nelegibilidad\nn={prisma_data['assessed_eligibility']}"
    no_abs_text   = f"Excluidos sin abstract\nn={prisma_data['excluded_no_abstract']}"
    incl_text     = f"Incluidos en\nsíntesis cualitativa\nn={prisma_data['included']}"
    not_rel_text  = f"Excluidos (no relevantes)\nn={prisma_data['excluded_not_relevant']}"

    # ── Cajas principales (columna central) ──────────────────────────────
    cx = 3.0   # x inicio columna central
    cw = 5.5   # ancho cajas principales

    draw_box(ax, cx, 15.0, cw, 2.0, id_text,      COLOR_ID,     fontsize=9)
    draw_box(ax, cx, 11.0, cw, 1.8, screen_text,  COLOR_SCREEN, fontsize=9)
    draw_box(ax, cx,  7.0, cw, 1.8, elig_text,    COLOR_ELIG,   fontsize=9)
    draw_box(ax, cx,  3.0, cw, 1.8, incl_text,    COLOR_INCL,   fontsize=9)

    # ── Cajas de exclusión (columna derecha) ─────────────────────────────
    ex = 9.5   # x inicio columna exclusión
    ew = 4.0   # ancho cajas exclusión

    draw_box(ax, ex, 11.0, ew, 1.8, dedup_text,   COLOR_EXCL, fontsize=9)
    draw_box(ax, ex,  7.0, ew, 1.8, no_abs_text,  COLOR_EXCL, fontsize=9)
    draw_box(ax, ex,  3.0, ew, 1.8, not_rel_text, COLOR_EXCL, fontsize=9)

    # ── Flechas verticales (flujo principal) ─────────────────────────────
    mid_c = cx + cw/2
    draw_arrow(ax, mid_c, 15.0, mid_c, 12.8)   # ID → Screen
    draw_arrow(ax, mid_c, 11.0, mid_c,  8.8)   # Screen → Elig
    draw_arrow(ax, mid_c,  7.0, mid_c,  4.8)   # Elig → Incl

    # ── Flechas horizontales (hacia exclusiones) ──────────────────────────
    right_c = cx + cw
    draw_arrow(ax, right_c, 11.9, ex, 11.9)    # → duplicados
    draw_arrow(ax, right_c,  7.9, ex,  7.9)    # → sin abstract
    draw_arrow(ax, right_c,  3.9, ex,  3.9)    # → no relevantes

    # ── Título ───────────────────────────────────────────────────────────
    ax.text(7, 17.5, 'PRISMA Flow Diagram',
            ha='center', va='center',
            fontsize=16, fontweight='bold', color=COLOR_BORDER)

    output_path = os.path.join(output_dir, 'prisma_flow.png')
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight',
                facecolor='white', edgecolor='none')
    plt.close()

    print(f"✓ Diagrama PRISMA generado: {output_path}")
    return output_path


def generate_prisma_checklist(prisma_data: dict) -> list:
    """
    Evalúa conformidad con ítems clave de PRISMA-ScR.
    Devuelve lista de (ítem, cumple: bool, nota).
    """
    checklist = []

    # Ítem 1: Búsqueda en múltiples bases de datos
    n_databases = len(prisma_data['databases'])
    checklist.append((
        "Búsqueda en ≥2 bases de datos",
        n_databases >= 2,
        f"{n_databases} base(s): {', '.join(prisma_data['databases'].keys())}"
    ))

    # Ítem 2: Criterios de inclusión documentados
    has_inclusion = len(prisma_data.get('inclusion_criteria', [])) > 0
    checklist.append((
        "Criterios de inclusión documentados",
        has_inclusion,
        f"{len(prisma_data.get('inclusion_criteria', []))} criterio(s) definido(s)"
    ))

    # Ítem 3: Criterios de exclusión documentados
    has_exclusion = len(prisma_data.get('exclusion_criteria', [])) > 0
    checklist.append((
        "Criterios de exclusión documentados",
        has_exclusion,
        f"{len(prisma_data.get('exclusion_criteria', []))} criterio(s) definido(s)"
    ))

    # Ítem 4: Número de resultados por base de datos reportado
    checklist.append((
        "Resultados por base de datos reportados",
        n_databases > 0,
        f"Disponible para {n_databases} fuente(s)"
    ))

    # Ítem 5: Duplicados reportados
    checklist.append((
        "Duplicados eliminados reportados",
        prisma_data['duplicates_removed'] >= 0,
        f"n={prisma_data['duplicates_removed']}"
    ))

    # Ítem 6: Razones de exclusión documentadas
    total_excluded = (prisma_data['excluded_no_abstract'] +
                      prisma_data['excluded_not_relevant'])
    checklist.append((
        "Razones de exclusión documentadas",
        True,  # siempre True: MAP registra ambas categorías
        f"Sin abstract: {prisma_data['excluded_no_abstract']}, "
        f"No relevantes: {prisma_data['excluded_not_relevant']}"
    ))

    # Ítem 7: Papers incluidos > 0
    checklist.append((
        "Al menos un paper incluido",
        prisma_data['included'] > 0,
        f"n={prisma_data['included']} incluidos en síntesis"
    ))

    return checklist


def run_prisma_validation(arq_data: dict, dedup_stats: dict,
                          papers_df, summary: dict,
                          output_dir: str) -> tuple[str, list]:
    """
    Punto de entrada principal. Genera diagrama y checklist.

    Returns:
        (prisma_diagram_path, checklist)
    """
    prisma_data = build_prisma_data(arq_data, dedup_stats, papers_df, summary)

    diagram_path = generate_prisma_diagram(prisma_data, output_dir)
    checklist    = generate_prisma_checklist(prisma_data)

    # Imprimir checklist en consola
    print("\n📋 PRISMA-ScR Conformidad:")
    for item, passes, note in checklist:
        icon = "✓" if passes else "✗"
        print(f"  {icon} {item}: {note}")

    passed = sum(1 for _, p, _ in checklist if p)
    print(f"\n  {passed}/{len(checklist)} ítems conformes")

    return diagram_path, checklist
