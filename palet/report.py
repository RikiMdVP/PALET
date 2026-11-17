"""Reporting of a review run (WP9): PRISMA flow, checklist, methods appendix,
tables and figures. Every number comes from the artefacts of the run.
"""

import csv
import statistics
from datetime import date
from collections import Counter
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

from palet import figstyle
from palet.assign import RecordAssignment, short_citation, summarize
from palet.models import Record
from palet.protocol import Protocol
from palet.runs import Run
from palet.screening import (METADATA_DIMENSIONS, FinalDecision, ScreeningDecision, agreement,
                             summarize as summarize_screening)

REASON_LABELS = {
    "WRONG_DOC_TYPE": "Document type not eligible",
    "WRONG_LANGUAGE": "Language not eligible",
    "OUT_OF_PERIOD": "Published outside the review period",
    "NOT_IN_JOURNAL_LIST": "Journal not in eligible indexes",
    "NO_AGREEMENT": "No agreement between screeners",
    "WRONG_CONTEXT": "Outside the geographical scope",
    "WRONG_CONCEPT": "No labour-market dimension",
    "WRONG_PHENOMENON": "No link to the twin transition",
    "NO_POLICY_CONTENT": "No policy content",
    "NO_ABSTRACT": "No abstract available",
    "OTHER": "Other reason",
}
REASON_ORDER = list(REASON_LABELS)


def source_label(protocol: Protocol, query_id: str, search: dict) -> str:
    try:
        source = protocol.source(query_id)
    except Exception:
        return query_id
    if source.type == "manual_import":
        when = str(search.get("executed_at") or "").split(" ")[0]
        return f"Scopus (web export{', ' + when if when else ''})"
    rqs = ", ".join(source.applies_to_rqs)
    name = {"openalex": "OpenAlex", "scopus": "Scopus", "pubmed": "PubMed", "wos": "Web of Science"}[source.type]
    return f"{name}, search" + (f" for {rqs}" if rqs else "")


# ── Counts ──────────────────────────────────────────────────────────────────

def prisma_counts(run: Run, protocol: Protocol) -> dict:
    """All the numbers of the flow diagram, from the artefacts of the run."""
    manifest = run.manifest
    records = run.read_models("records.jsonl", Record)
    duplicates = run.read_models("duplicates.jsonl", Record)
    finals = run.read_models("final_decisions.jsonl", FinalDecision)
    decisions = run.read_models("decisions.jsonl", ScreeningDecision)

    sources = []
    for search in manifest["searches"]:
        try:
            source_type = protocol.source(search["query_id"]).type
        except Exception:
            source_type = None
        sources.append({
            "query_id": search["query_id"],
            "type": source_type,
            "label": source_label(protocol, search["query_id"], search),
            "total_hits": search.get("total_hits"),
            "downloaded": search.get("downloaded"),
            "truncated": bool(search.get("truncated")),
            "executed_at": search.get("executed_at"),
            "query_string": search.get("query_string"),
            "filters": search.get("filters"),
            "platform": search.get("platform"),
        })

    screening = summarize_screening(finals)
    decided_by = Counter()
    for final in finals:
        key = "authors" if final.decided_by.startswith("human:") else final.decided_by
        key = "agreement" if key == "single_screener" else key      # both: decided by the AI screening alone
        decided_by[(final.decision, key)] += 1
    model_screeners = sorted({d.screener for d in decisions
                              if d.screener != "metadata" and not d.screener.startswith("human:")})
    human_initials = sorted({f.decided_by.split(":", 1)[1] for f in finals if f.decided_by.startswith("human:")})

    return {
        "sources": sources,
        "model_screeners": model_screeners,
        "identified": sum(s["downloaded"] or 0 for s in sources),
        "not_downloaded": sum((s["total_hits"] or 0) - (s["downloaded"] or 0) for s in sources if s["truncated"]),
        "duplicates_removed": len(duplicates),
        "screened": len(records),
        "screening_decisions_recorded": len(finals),
        "excluded": screening["exclude"],
        # Known reasons in a fixed order, then any reason code defined by the protocol itself.
        "exclusion_reasons": {code: screening["exclusion_reasons"][code]
                              for code in [*REASON_ORDER, *sorted(set(screening["exclusion_reasons"]) - set(REASON_ORDER))]
                              if screening["exclusion_reasons"].get(code)},
        "pending": screening["pending"],
        "included": screening["include"],
        "included_by_agreement": decided_by[("include", "agreement")],
        "included_by_authors": decided_by[("include", "authors")],
        "excluded_by_agreement": decided_by[("exclude", "agreement")],
        "excluded_by_authors": decided_by[("exclude", "authors")],
        "excluded_by_metadata": decided_by[("exclude", "metadata")],
        "excluded_no_agreement": decided_by[("exclude", "no_agreement")],
        "decided_by_authors": decided_by[("include", "authors")] + decided_by[("exclude", "authors")],
        "author_initials": human_initials,
        "agreement": agreement(decisions),
    }


# ── PRISMA flow diagram ─────────────────────────────────────────────────────

def identification_lines(counts: dict) -> list[str]:
    """Lines of the identification box: the total, then the sources grouped as database exports and
    supplementary searches. No database is named in the figure; the methods appendix (section A) names
    them, with their dates, strings and counts, and the caption of the figure can refer to it."""
    def year_of(sources):
        years = sorted({str(s.get("executed_at") or "")[:4] for s in sources if s.get("executed_at")})
        return ", " + "–".join([years[0], years[-1]] if len(years) > 1 else years) if years else ""

    exports = [s for s in counts["sources"] if s.get("type") == "manual_import"]
    searches = [s for s in counts["sources"] if s.get("type") != "manual_import"]
    lines = [f"Records identified (n = {counts['identified']})"]
    if exports:
        lines.append(f"Database export{'s' if len(exports) > 1 else ''}{year_of(exports)} "
                     f"(n = {sum(s['downloaded'] or 0 for s in exports)})")
    if searches:
        kind = "Supplementary" if exports else "Database"     # "supplementary" only next to an export
        lines.append(f"{kind} search{'es' if len(searches) > 1 else ''}{year_of(searches)} "
                     f"(n = {sum(s['downloaded'] or 0 for s in searches)})")
    return lines


def source_limitation(counts: dict) -> str:
    """Limitation about the information sources, as a bullet of the methods appendix."""
    searches = "earches were run in one database (OpenAlex), whose language and document-type metadata are imperfect."
    if any(s.get("type") == "manual_import" and not s.get("query_string") for s in counts["sources"]):
        return ("- The search string of the original Scopus export was not archived; coverage of that source "
                "cannot be reproduced exactly. Supplementary s" + searches)
    return "- S" + searches


def draw_prisma(counts: dict, path_without_extension) -> list[str]:
    figstyle.apply_style()
    palette = figstyle.PALETTE
    fig, ax = plt.subplots(figsize=(figstyle.FIG_WIDTH, 7.6))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 100)
    ax.axis("off")

    def box(x, y, w, h, text, fill, bold_first_line=True, align="left", size=8, dashed=False):
        ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.4,rounding_size=1.2",
                                    facecolor=fill, edgecolor=palette["ink"], linewidth=0.8,
                                    linestyle="--" if dashed else "-"))
        lines = text.split("\n")
        top = y + h - 2.6
        for i, line in enumerate(lines):
            ax.text(x + (1.6 if align == "left" else w / 2), top - i * 2.7, line, fontsize=size,
                    ha="left" if align == "left" else "center", va="center", color=palette["ink"],
                    fontweight="bold" if (bold_first_line and i == 0) else "normal")

    def arrow(x1, y1, x2, y2):
        ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                    arrowprops=dict(arrowstyle="-|>", color=palette["ink"], lw=0.9, shrinkA=0, shrinkB=0))

    def stage(y, h, label):
        ax.add_patch(FancyBboxPatch((0.5, y), 5, h, boxstyle="round,pad=0.3,rounding_size=1",
                                    facecolor=palette["primary"], edgecolor="none"))
        ax.text(3, y + h / 2, label, rotation=90, ha="center", va="center", color="white",
                fontsize=9, fontweight="bold")

    left_x, left_w, right_x, right_w = 9, 46, 60, 39

    # Identification
    id_lines = identification_lines(counts)
    id_text = "\n".join(id_lines)
    id_h = max(11.4, 6 + 2.7 * (len(id_lines) - 1))       # tall enough for the rotated stage label
    id_y = 97 - id_h
    box(left_x, id_y, left_w, id_h, id_text, palette["box_main"])
    removed = f"Records removed before screening\nDuplicates (n = {counts['duplicates_removed']})"
    if counts["not_downloaded"]:
        removed += f"\nNot downloaded, search truncated (n = {counts['not_downloaded']})"
    removed_h = 6 + 2.7 * (removed.count("\n"))
    box(right_x, id_y + id_h - removed_h, right_w, removed_h, removed, palette["box_side"])
    arrow(left_x + left_w, id_y + id_h - removed_h / 2, right_x, id_y + id_h - removed_h / 2)
    stage(id_y, id_h, "Identification")

    # Screening
    reason_lines = [f"{REASON_LABELS.get(code, code)} (n = {n})" for code, n in counts["exclusion_reasons"].items()]
    excl_text = f"Records excluded (n = {counts['excluded']})\n" + "\n".join(reason_lines)
    excl_h = 6 + 2.7 * max(1, len(reason_lines))
    screen_h = 8.7
    screen_y = id_y - 9 - max(screen_h, excl_h)
    screen_box_y = screen_y + max(screen_h, excl_h) - screen_h
    box(left_x, screen_box_y, left_w, screen_h,
        f"Records screened (n = {counts['screened']})\nTitle, keywords and abstract", palette["box_main"])
    box(right_x, screen_y + max(screen_h, excl_h) - excl_h, right_w, excl_h, excl_text, palette["box_side"])
    arrow(left_x + left_w / 2, id_y, left_x + left_w / 2, screen_box_y + screen_h)
    arrow(left_x + left_w, screen_box_y + screen_h / 2, right_x, screen_box_y + screen_h / 2)
    stage(screen_y, max(screen_h, excl_h), "Screening")

    # Included
    selection = counts.get("selection") or {}
    narrowed = selection.get("rule") == "core_only"
    incl_lines = [(f"Studies meeting the eligibility criteria (n = {counts['included']})" if narrowed else
                   f"Studies included in the review (n = {counts['included']})"),
                  (f"By agreement of two AI screeners (n = {counts['included_by_agreement']})"
                   if len(counts.get("model_screeners", [])) != 1 else
                   f"By a single AI screener (n = {counts['included_by_agreement']})"),
                  f"By decision of the authors (n = {counts['included_by_authors']})"]
    incl_h = 6 + 2.7 * (len(incl_lines) - 1)
    incl_y = screen_y - 9 - incl_h
    box(left_x, incl_y, left_w, incl_h, "\n".join(incl_lines),
        palette["box_main"] if narrowed else palette["box_final"])
    arrow(left_x + left_w / 2, screen_box_y, left_x + left_w / 2, incl_y + incl_h)
    stage(incl_y, incl_h, "Eligibility" if narrowed else "Included")
    if counts["pending"]:
        # Not yet decided: shown apart, so that a provisional diagram cannot be mistaken for a final one.
        box(right_x, incl_y + incl_h - 8.7, right_w, 8.7,
            f"Awaiting the authors' decision (n = {counts['pending']})\nProvisional diagram", palette["box_side"],
            dashed=True)

    bottom = incl_y
    if narrowed:
        # Last step: only the studies that are core to a research question are synthesised.
        syn_h = 8.7
        syn_y = incl_y - 9 - syn_h
        box(left_x, syn_y, left_w, syn_h,
            f"Studies synthesised (n = {selection['selected']})\nCore to at least one research question",
            palette["box_final"])
        box(right_x, syn_y, right_w, syn_h,
            f"Eligible, not synthesised (n = {selection['not_selected']})\nNot core to any research question",
            palette["box_side"])
        arrow(left_x + left_w / 2, incl_y, left_x + left_w / 2, syn_y + syn_h)
        arrow(left_x + left_w, syn_y + syn_h / 2, right_x, syn_y + syn_h / 2)
        stage(syn_y, syn_h, "Included")
        bottom = syn_y

    ax.set_ylim(bottom - 3, 100)
    return figstyle.save(fig, path_without_extension)


# ── Figures ─────────────────────────────────────────────────────────────────

def rq_figure_label(selection_rule: str) -> str:
    """X-axis label of the figure by research question: it counts the studies that reach the synthesis."""
    if selection_rule == "core_only":
        return "Studies synthesised"          # the double counting is explained in the note of the figure
    return "Included studies (a study may address several questions)"


def draw_included_by_rq(protocol: Protocol, assignments: list[RecordAssignment], path_without_extension) -> list[str]:
    """Bars by research question for the given studies. Under ``core_only`` they are the synthesised
    studies and each is counted only in the questions it is core to (one plain bar per question)."""
    core_only = protocol.synthesis_selection == "core_only"
    figstyle.apply_style()
    palette = figstyle.PALETTE
    per_rq = summarize(protocol, assignments)["per_rq"]
    rqs = list(per_rq)[::-1]
    core = [per_rq[rq]["core"] for rq in rqs]
    partial = [0 if core_only else per_rq[rq]["partial"] for rq in rqs]

    fig, ax = plt.subplots(figsize=(figstyle.FIG_WIDTH, 0.42 * len(rqs) + 1.1))
    ax.barh(rqs, core, color=palette["bar"], label="Core to the question", height=0.62)
    if not core_only:
        ax.barh(rqs, partial, left=core, color=palette["bar_light"], hatch="///", edgecolor="white",
                label="Partially relevant", height=0.62)
    for i, (c, p) in enumerate(zip(core, partial)):
        ax.text(c + p + max(core + partial + [1]) * 0.015, i, f"{c + p}", va="center", fontsize=9,
                color=palette["ink"])
    ax.set_xlabel(rq_figure_label(protocol.synthesis_selection), labelpad=6)
    ax.xaxis.get_major_locator().set_params(integer=True)
    ax.tick_params(axis="y", length=0)
    if not core_only:
        ax.legend(frameon=False, loc="lower right", bbox_to_anchor=(1.0, 1.0), ncol=2, borderaxespad=0.2)
    return figstyle.save(fig, path_without_extension)


def draw_included_by_year(records: list[Record], path_without_extension, partial_year: int | None = None,
                          ylabel: str = "Included studies") -> list[str]:
    figstyle.apply_style()
    palette = figstyle.PALETTE
    years = [r.year for r in records if r.year]
    fig, ax = plt.subplots(figsize=(figstyle.FIG_WIDTH, figstyle.FIG_WIDTH / 2.3))
    if years:
        span = list(range(min(years), max(years) + 1))
        counts = Counter(years)
        bars = ax.bar(span, [counts.get(y, 0) for y in span], color=palette["bar"], width=0.72)
        if partial_year in span:
            bar = bars[span.index(partial_year)]
            bar.set_facecolor(palette["bar_light"])
            bar.set_hatch("///")
            bar.set_edgecolor("white")
            ax.text(partial_year, counts.get(partial_year, 0) + max(counts.values()) * 0.03,
                    "partial\nyear", ha="center", va="bottom", fontsize=8, color=palette["muted"])
        ax.set_xticks(span)
        ax.set_ylim(0, max(counts.values()) * 1.22)
    ax.set_ylabel(ylabel, labelpad=6)
    ax.set_xlabel("Year of publication", labelpad=6)
    ax.yaxis.get_major_locator().set_params(integer=True)
    return figstyle.save(fig, path_without_extension)


# ── Tables ──────────────────────────────────────────────────────────────────

def _write_csv(path, header, rows) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)


def included_by_rq_markdown(protocol: Protocol, records: dict[str, Record],
                            assignments: list[RecordAssignment]) -> str:
    lines = ["| RQ | Core | Partially relevant | Studies |", "|---|---|---|---|"]
    for rq in protocol.research_questions:
        core = sorted(short_citation(records[a.record_id]) for a in assignments if rq in a.rqs("core"))
        partial = sorted(short_citation(records[a.record_id]) for a in assignments if rq in a.rqs("partial"))
        studies = "; ".join(core) + ("; *partially:* " + "; ".join(partial) if partial else "")
        lines.append(f"| {rq} | {len(core)} | {len(partial)} | {studies} |")
    return "\n".join(lines) + "\n"


def evidence_rows(protocol: Protocol, records: dict[str, Record], assignments: list[RecordAssignment]) -> tuple[list, list]:
    header = ["citation", "year", "title", "source", "doi", "found_by", "core_rqs", "partial_rqs",
              "evidence_type", "geography", "contribution", "contribution_quote", "quotes_by_rq", "needs_review",
              "record_id"]
    rows = []
    for assignment in sorted(assignments, key=lambda a: short_citation(records[a.record_id])):
        record = records[assignment.record_id]
        quotes = " | ".join(f"{i.rq} ({i.relevance}): “{i.evidence_quote}”" for i in assignment.items if i.counts)
        rows.append([short_citation(record), record.year, record.title, record.source_title, record.doi or "",
                     "; ".join(record.found_by_queries), ", ".join(assignment.rqs("core")),
                     ", ".join(assignment.rqs("partial")), assignment.evidence_type or "",
                     "; ".join(assignment.geography), assignment.contribution,
                     assignment.contribution_quote or "", quotes, "; ".join(assignment.needs_review),
                     record.record_id])
    return header, rows


def evidence_by_rq_markdown(protocol: Protocol, records: dict[str, Record],
                           assignments: list[RecordAssignment]) -> str:
    """For each research question, its core studies with what each contributes and the passage behind it.

    This is the material to write the synthesis from: nothing here is generated beyond the one-sentence
    contribution of the charting step, and every sentence comes with the verbatim passage it rests on.
    """
    this_year = date.today().year

    def cites_per_year(record: Record) -> float:
        return (record.cited_by_count or 0) / max(1, this_year - (record.year or this_year))

    out = ["# Evidence by research question (core studies only)", "",
           "Generated by PALET from the charting step. Each entry: citation, journal, type of evidence, "
           "geography; the contribution as summarised by the model; and the verbatim passages of the record "
           "that support the contribution and the assignment to the question. Check each study against its "
           "full text before citing it. Within a question, studies are ordered by citations per year.", ""]
    for rq, question in protocol.research_questions.items():
        core = [a for a in assignments if rq in a.rqs("core")]
        core.sort(key=lambda a: cites_per_year(records[a.record_id]), reverse=True)
        out += [f"## {rq} — {len(core)} core studies", "", f"*{question}*", ""]
        for a in core:
            record = records[a.record_id]
            quote = next((i.evidence_quote for i in a.items if i.rq == rq), "")
            where = "; ".join(a.geography) or "not stated"
            out += [f"### {short_citation(record)}. {record.title}",
                    f"{record.source_title or 'journal not stated'} · {a.evidence_type or 'type not stated'} · "
                    f"{where} · cited {record.cited_by_count or 0} times · "
                    + (f"https://doi.org/{record.doi}" if record.doi else "no DOI"), "",
                    f"- **Contribution:** {a.contribution}",
                    f"- **Passage behind it:** “{a.contribution_quote or ''}”"
                    + ("" if a.contribution_quote_verified else " *(not found verbatim in the record: check)*"),
                    f"- **Why core to {rq}:** “{quote}”", ""]
    return "\n".join(out)


def citations_by_rq(protocol: Protocol, records: dict[str, Record], assignments: list[RecordAssignment]) -> tuple[list, list]:
    header = ["rq", "studies", "with_citation_count", "median_citations", "min", "max"]
    rows = []
    for rq in protocol.research_questions:
        ids = [a.record_id for a in assignments if rq in a.assigned_rqs]
        cited = [records[i].cited_by_count for i in ids if records[i].cited_by_count is not None]
        rows.append([rq, len(ids), len(cited),
                     statistics.median(cited) if cited else "", min(cited) if cited else "",
                     max(cited) if cited else ""])
    return header, rows


# ── PRISMA-ScR checklist ────────────────────────────────────────────────────

_CHECKLIST = [
    (1, "Title", "Title", "Identify the report as a scoping review."),
    (2, "Abstract", "Structured summary", "Background, objectives, eligibility criteria, sources of evidence, charting methods, results and conclusions."),
    (3, "Introduction", "Rationale", "Rationale for the review in the context of what is already known."),
    (4, "Introduction", "Objectives", "Questions and objectives, with reference to their key elements."),
    (5, "Methods", "Protocol and registration", "Whether a protocol exists, where it can be accessed and its registration."),
    (6, "Methods", "Eligibility criteria", "Characteristics of the sources of evidence used as eligibility criteria, with rationale."),
    (7, "Methods", "Information sources", "All information sources and the date of the most recent search."),
    (8, "Methods", "Search", "Full electronic search strategy for at least one database, including limits."),
    (9, "Methods", "Selection of sources of evidence", "The process for selecting sources of evidence (screening and eligibility)."),
    (10, "Methods", "Data charting process", "Methods of charting data from the included sources."),
    (11, "Methods", "Data items", "All variables for which data were sought."),
    (12, "Methods", "Critical appraisal of individual sources of evidence", "If done, rationale and methods of critical appraisal."),
    (13, "Methods", "Synthesis of results", "Methods of handling and summarising the charted data."),
    (14, "Results", "Selection of sources of evidence", "Numbers screened, assessed and included, with reasons for exclusion, ideally in a flow diagram."),
    (15, "Results", "Characteristics of sources of evidence", "Characteristics for which data were charted, with citations."),
    (16, "Results", "Critical appraisal within sources of evidence", "If done, data on critical appraisal."),
    (17, "Results", "Results of individual sources of evidence", "For each source, the relevant charted data."),
    (18, "Results", "Synthesis of results", "Summary of the charting results in relation to the questions and objectives."),
    (19, "Discussion", "Summary of evidence", "Main results, linked to the questions and objectives."),
    (20, "Discussion", "Limitations", "Limitations of the scoping review process."),
    (21, "Discussion", "Conclusions", "General interpretation and implications."),
    (22, "Funding", "Funding", "Sources of funding and the role of the funders."),
]


def checklist_rows(counts: dict, has_assignments: bool) -> list[list]:
    """PRISMA-ScR items with what PALET can supply for each; nothing is ticked on trust."""
    supplied = {
        5: ("Material available", "Protocol file with research questions, criteria and sources, fixed before screening "
            "(sha256 in the run manifest). Not registered: state this in the text."),
        6: ("Material available", "Eligibility criteria as applied: methods appendix, section B."),
        7: ("Material available", "Sources, platforms and search dates: methods appendix, section A."),
        8: ("Material available" if all(s["query_string"] for s in counts["sources"]) else "Partly available",
            "Full strings and limits of the supplementary searches: methods appendix, section A."
            + ("" if all(s["query_string"] for s in counts["sources"]) else
               " The string of the original Scopus search was not archived and cannot be reported: state this.")),
        9: ("Material available", "Selection process (AI screening, decision rule, adjudication by the authors): "
            "methods appendix, section D."),
        10: ("Material available" if has_assignments else "Authors to complete",
             "Charting from titles and abstracts by one AI model with verified quotes: methods appendix, section E."
             if has_assignments else "Charting step not run yet."),
        11: ("Material available" if has_assignments else "Authors to complete",
             "Research questions addressed, contribution, evidence type and geography: evidence table."
             if has_assignments else ""),
        12: ("Not done", "No critical appraisal of individual sources was carried out (optional in PRISMA-ScR): state this."),
        14: ("Material available" if not counts["pending"] else "Incomplete",
             "Flow diagram with reasons for exclusion (prisma_flow) and counts (prisma_counts.json)."
             + (f" {counts['pending']} records still await the authors' decision." if counts["pending"] else "")),
        15: ("Material available" if has_assignments else "Authors to complete",
             "Table of included studies by research question; figures by question and by year."
             if has_assignments else ""),
        16: ("Not applicable", "No critical appraisal (see item 12)."),
        17: ("Material available" if has_assignments else "Authors to complete",
             "Evidence table: one row per included study." if has_assignments else ""),
        20: ("Draft available", "Limitations of the process: methods appendix, section G (to be adapted by the authors)."),
    }
    rows = []
    for number, section, item, description in _CHECKLIST:
        status, where = supplied.get(number, ("Authors to complete", "To be reported in the manuscript by the authors."))
        rows.append([number, section, item, description, status, where, ""])
    return rows


def checklist_markdown(rows: list[list]) -> str:
    lines = ["# PRISMA-ScR checklist", "",
             "Items follow Tricco et al. (2018), PRISMA Extension for Scoping Reviews. The column "
             "\"Status\" says what this run can supply; the authors must add the page or section "
             "where each item is reported in the manuscript.", "",
             "| # | Section | Item | Status | Where / note | Reported on page |", "|---|---|---|---|---|---|"]
    for number, section, item, _description, status, where, page in rows:
        lines.append(f"| {number} | {section} | {item} | {status} | {where} | {page} |")
    return "\n".join(lines) + "\n"


# ── Methods appendix ────────────────────────────────────────────────────────

def methods_appendix(run: Run, protocol: Protocol, counts: dict, assignment_summary: dict | None) -> str:
    manifest = run.manifest
    settings = manifest["settings"]
    screen_steps = [s for s in manifest["steps"] if s["step"] == "screen"]
    screeners = screen_steps[-1]["screeners"] if screen_steps else []
    stats = counts["agreement"]
    out = ["# Methods appendix (generated by PALET)", "",
           f"Run `{manifest['run_id']}` — PALET {manifest['palet_version']}, git commit "
           f"`{str(manifest['git_commit'])[:10]}`. Generated from the artefacts of the run; "
           "edit the wording freely, but not the numbers.", ""]

    out += ["## A. Information sources and searches", "",
            "| Source | Platform | Date | Records found | Records downloaded |", "|---|---|---|---|---|"]
    for s in counts["sources"]:
        out.append(f"| {s['label']} | {s['platform'] or ''} | {s['executed_at'] or ''} | "
                   f"{s['total_hits']} | {s['downloaded']}{' (truncated)' if s['truncated'] else ''} |")
    grouping = ("groups these sources into database exports and supplementary searches"
                if any(s["type"] == "manual_import" for s in counts["sources"]) else "gives their total")
    out += ["", f"The flow diagram {grouping} and names no database; refer to this table (or name the "
            "databases in a footnote) in its caption.", ""]
    for s in counts["sources"]:
        out.append(f"**{s['label']}**")
        if s["query_string"]:
            filters = s["filters"] or {}
            out += ["", "Search string (title and abstract):", "", "```", s["query_string"], "```", "",
                    f"Limits: years {filters.get('year_from')}–{filters.get('year_to')}; document types "
                    f"{', '.join(filters.get('document_types') or [])}; languages "
                    f"{', '.join(filters.get('languages') or [])}.", ""]
        else:
            out += ["", "The search string used for this export was not archived at the time and cannot be "
                    "reported. The records were re-screened in full against the eligibility criteria below.", ""]

    out += ["## B. Eligibility criteria", "",
            f"Period {protocol.year_from}–{protocol.year_to}; languages: {', '.join(protocol.languages)}; "
            f"document types: {', '.join(protocol.document_types)}.", "",
            "| ID | Type | Dimension | Criterion |", "|---|---|---|---|"]
    for c in protocol.criteria:
        how = " *(checked against metadata)*" if c.dimension in METADATA_DIMENSIONS else ""
        out.append(f"| {c.id} | {'Inclusion' if c.kind == 'include' else 'Exclusion'} | {c.dimension} | {c.rule}{how} |")
    out.append("")

    out += ["## C. De-duplication", "",
            "Records were merged when they shared a normalised DOI, or when their titles were "
            "near-identical (similarity of at least 0.92 after removing case, accents and punctuation, "
            "comparing each language version of bilingual titles), they shared an author surname and "
            "their years differed by at most one. "
            f"{counts['duplicates_removed']} duplicate record(s) were removed.", ""]

    out += ["## D. Selection of sources of evidence", ""]
    single = len(screeners) == 1
    by_ai = "the single AI screener" if single else "agreement of the two models"
    if screeners:
        models = list(dict.fromkeys(s["model"] for s in screeners))
        if len(screeners) == 1:
            who = f"once, by a single AI model (`{models[0]}`),"
        elif len(models) == 1:
            who = f"twice, in two separate passes of the same AI model (`{models[0]}`),"
        else:
            who = "independently by two AI models (" + " and ".join(f"`{m}`" for m in models) + ")"
        out.append(f"Each record was screened {who} through the "
                   "Anthropic API, with the same instructions "
                   f"(prompt sha256 `{manifest['prompts'].get('screen_system_v1', '')[:16]}…`). "
                   "The models saw only the title, the author keywords and the abstract.")
    out += ["",
            "The models did not decide inclusion. For every eligibility criterion they answered yes, no or "
            "unclear and quoted the passage supporting the answer; software then (i) checked that each "
            "quoted passage occurs in the record and (ii) applied a fixed rule: exclude if an inclusion "
            "criterion is not met or an exclusion criterion applies; include if every inclusion criterion "
            "is met with a verified quote and no exclusion criterion applies; otherwise unclear. "
            "Document type, language and period were checked against the bibliographic metadata."
            + (" Indexing of the journal was checked by ISSN (journal title when the record had no ISSN) against "
               + " and ".join(j.description or j.id for j in protocol.journal_lists)
               + f"; {counts['exclusion_reasons'].get('NOT_IN_JOURNAL_LIST', 0)} record(s) were excluded on this "
               "ground before any model was called. The lists reflect indexing at the date of the list, not "
               "at the date of publication." if protocol.journal_lists else ""), "",
            ("The outcome of that rule was final: there was no second screener and no cross-check. Only "
             "records the model found unclear and records without an abstract were decided by the authors."
             if single else
             "A record was included only when both models included it. Records that one model included and "
             "the other found unclear were decided by the authors. Records excluded by both models were "
             "excluded for the reason they shared. All other records (both models unsure, one excluding and "
             "the other unsure, or one including and the other excluding) were excluded without human "
             "review; this rule is conservative and may have excluded relevant studies. Only records for "
             "which an abstract could be retrieved were eligible: "
             f"{counts['exclusion_reasons'].get('NO_ABSTRACT', 0)} record(s) without an abstract were "
             "excluded on that ground before any model was called."
             if protocol.decision_rule == "agreement_or_exclude" else
             "A decision was final only when both models reached it. Records on which the models disagreed, "
             "records either model found unclear, and records without an abstract were decided by the authors."), "",
            "| | Records |", "|---|---|",
            f"| Screened | {counts['screened']} |",
            f"| Excluded from metadata (document type, language, period, journal list, no abstract) | "
            f"{counts['excluded_by_metadata']} |",
            f"| Excluded for lack of agreement between the models | {counts['excluded_no_agreement']} |",
            f"| Included by {by_ai} | {counts['included_by_agreement']} |",
            f"| Excluded by {by_ai} | {counts['excluded_by_agreement']} |",
            f"| Decided by the authors | {counts['decided_by_authors']} "
            f"({counts['included_by_authors']} included, {counts['excluded_by_authors']} excluded) |",
            f"| Awaiting the authors' decision | {counts['pending']} |", ""]
    if stats.get("records_compared"):
        out.append(f"The two models reached the same outcome (include, exclude or unclear) on "
                   f"{stats['same_decision']} of the {stats['records_compared']} records both assessed "
                   f"({stats['percent_agreement']}%; Cohen's kappa = {stats['cohen_kappa']}). This measures "
                   "agreement between the two screening passes, not accuracy against human screening."
                   + (" As both passes used the same model, it reflects the consistency of that model "
                      "and cannot reveal errors it makes systematically."
                      if len({s["model"] for s in screeners}) == 1 else ""))
        out.append("")
    if counts["exclusion_reasons"]:
        out += ["Reasons for exclusion:", ""]
        out += [f"- {REASON_LABELS.get(code, code)}: {n}" for code, n in counts["exclusion_reasons"].items()]
        out.append("")

    out += ["## E. Data charting", ""]
    if assignment_summary:
        assign_steps = [s for s in manifest["steps"] if s["step"] == "assign"]
        model = assign_steps[-1].get("model") if assign_steps else ""
        out += [f"Included studies were charted from their title, keywords and abstract by one AI model "
                f"(`{model}`), which stated for each research question whether the study was core, partially "
                "relevant or not relevant, quoting the supporting passage, and summarised the study's "
                "contribution, type of evidence and geography. Assignments whose quote could not be found in "
                "the record were not counted.", "",
                "The categories were defined to the model as follows (prompt "
                f"`assign_system_v1`, sha256 `{manifest['prompts'].get('assign_system_v1', '')[:16]}…`): "
                "*core*: answering the question is a main purpose or main result of the study; "
                "*partial*: the study gives some evidence or discussion relevant to the question, but it is "
                "not its focus; *none*: the text does not address the question. The model was told to be "
                "conservative: sharing a general topic with a question was not enough. A study could be core "
                "or partial for several questions, or for none. This classification was made by one model "
                "from the abstract and was not checked by a second model or by the authors.", "",
                *([f"**Selection for the synthesis.** Only the studies that were core to at least one research "
                   f"question were synthesised: {counts['selection']['selected']} of the {counts['included']} "
                   f"eligible studies. The remaining {counts['selection']['not_selected']} met the eligibility "
                   "criteria but addressed the questions only partially or not at all; they are listed in "
                   "`evidence_table.csv`. The review is therefore not exhaustive: it synthesises the studies "
                   "most directly concerned with each question.", ""]
                  if (counts.get("selection") or {}).get("rule") == "core_only" else []),
                "| Research question | Core | Partially relevant |", "|---|---|---|"]
        out += [f"| {rq} | {n['core']} | {n['partial']} |" for rq, n in assignment_summary["per_rq"].items()]
        out += ["", f"{assignment_summary['assigned_to_several_rqs']} studies address more than one question; "
                f"{assignment_summary['not_assigned_to_any_rq']} included studies were not assigned to any.", ""]
    else:
        out += ["Not run yet.", ""]

    usage = manifest.get("llm_usage", {})
    out += ["## F. Software and reproducibility", "",
            f"PALET {manifest['palet_version']} (commit `{manifest['git_commit']}`), Python {manifest['python']}. "
            f"Protocol version {manifest['protocol']['version']} (sha256 `{manifest['protocol']['sha256'][:16]}…`). "
            "The raw reply of every model call is stored with the hash of its request, so the run can be "
            "replayed without calling the models and yields the same decisions.", ""]
    if usage:
        out += ["| Step | Model | Calls | Input tokens | Output tokens |", "|---|---|---|---|---|"]
        for step, phases in usage.items():
            for phase, u in phases.items():
                out.append(f"| {step} / {phase} | {', '.join(u['models'])} | {u['calls']} | "
                           f"{u['input_tokens']:,} | {u['output_tokens']:,} |")
        out.append("")
    out += [f"Sampling temperature cannot be set for these models (settings in the manifest: "
            f"`{settings.get('model_options') or 'none'}`); reproducibility rests on the stored replies.", ""]

    out += ["## G. Use of AI and limitations (draft for the authors)", "",
            "- AI models were used to screen records against pre-specified criteria and to chart included "
            "studies. They were not used to decide the criteria, the research questions or the synthesis.",
            "- The AI-assisted screening was **not validated against independent human screening** of a "
            "sample; its sensitivity and precision are therefore unknown. "
            + ("A single AI screener was used, so no inter-screener agreement can be reported; only records "
               "it found unclear were decided by the authors." if single else
               "Agreement between the two models "
               "is reported instead, and all uncertain or contested records were decided by the authors."),
            "- Screening and charting used titles, keywords and abstracts only. Studies whose relevance is "
            "apparent only in the full text may have been excluded, and charted contributions reflect "
            "what the abstract states.",
            "- Results depend on the model versions named above.",
            source_limitation(counts), ""]
    return "\n".join(out)


# ── Everything ──────────────────────────────────────────────────────────────

def build_report(run: Run, protocol: Protocol, partial_year: int | None = None) -> dict:
    """Write every reporting artefact under <run>/report/ and return what was written."""
    out_dir = run.path / "report"
    out_dir.mkdir(exist_ok=True)
    counts = prisma_counts(run, protocol)
    run.write_json("report/prisma_counts.json", counts)
    written = ["report/prisma_counts.json"]

    records = {r.record_id: r for r in run.read_models("records.jsonl", Record)}
    finals = run.read_models("final_decisions.jsonl", FinalDecision)

    excluded = [[f.record_id, short_citation(records[f.record_id]), records[f.record_id].title,
                 f.reason_code, REASON_LABELS.get(f.reason_code, ""), f.decided_by]
                for f in finals if f.decision == "exclude"]
    _write_csv(out_dir / "excluded_records.csv",
               ["record_id", "citation", "title", "reason_code", "reason", "decided_by"], excluded)
    written.append("report/excluded_records.csv")

    assignment_summary = None
    has_assignments = (run.path / "assignments.jsonl").is_file()
    if has_assignments:
        included_ids = {f.record_id for f in finals if f.decision == "include"}
        assignments = [a for a in run.read_models("assignments.jsonl", RecordAssignment)
                       if a.record_id in included_ids]
        assignment_summary = summarize(protocol, assignments)
        selected = [a for a in assignments if a.rqs("core")] if protocol.synthesis_selection == "core_only" \
            else assignments
        counts["selection"] = {"rule": protocol.synthesis_selection, "selected": len(selected),
                               "not_selected": len(included_ids) - len(selected)}
        run.write_json("report/prisma_counts.json", counts)
        header, rows = evidence_rows(protocol, records, selected)
        _write_csv(out_dir / "selected_studies.csv", header, rows)
        (out_dir / "evidence_by_rq.md").write_text(
            evidence_by_rq_markdown(protocol, records, selected), encoding="utf-8")
        written += ["report/selected_studies.csv", "report/evidence_by_rq.md"]
        (out_dir / "table_included_by_rq.md").write_text(
            included_by_rq_markdown(protocol, records, assignments), encoding="utf-8")
        header, rows = evidence_rows(protocol, records, assignments)
        _write_csv(out_dir / "evidence_table.csv", header, rows)
        header, rows = citations_by_rq(protocol, records, assignments)
        _write_csv(out_dir / "citations_by_rq.csv", header, rows)
        draw_included_by_rq(protocol, selected, out_dir / "fig_included_by_rq")
        draw_included_by_year([records[a.record_id] for a in selected], out_dir / "fig_included_by_year",
                              partial_year=partial_year, ylabel=rq_figure_label(protocol.synthesis_selection)
                              if protocol.synthesis_selection == "core_only" else "Included studies")
        written += ["report/table_included_by_rq.md", "report/evidence_table.csv", "report/citations_by_rq.csv",
                    "report/fig_included_by_rq.pdf", "report/fig_included_by_rq.png",
                    "report/fig_included_by_year.pdf", "report/fig_included_by_year.png"]

    draw_prisma(counts, out_dir / "prisma_flow")
    written += ["report/prisma_flow.pdf", "report/prisma_flow.png"]

    rows = checklist_rows(counts, has_assignments)
    (out_dir / "prisma_scr_checklist.md").write_text(checklist_markdown(rows), encoding="utf-8")
    _write_csv(out_dir / "prisma_scr_checklist.csv",
               ["number", "section", "item", "description", "status", "where_or_note", "reported_on_page"], rows)
    (out_dir / "methods_appendix.md").write_text(
        methods_appendix(run, protocol, counts, assignment_summary), encoding="utf-8")
    written += ["report/prisma_scr_checklist.md", "report/prisma_scr_checklist.csv", "report/methods_appendix.md"]

    return {"counts": counts, "assignments": assignment_summary, "written": written,
            "directory": str(Path(out_dir))}
