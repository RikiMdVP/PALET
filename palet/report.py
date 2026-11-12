"""Reporting of a review run (WP9): PRISMA flow, checklist, methods appendix,
tables and figures. Every number comes from the artefacts of the run.
"""

import csv
import statistics
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
        date = str(search.get("executed_at") or "").split(" ")[0]
        return f"Scopus (web export{', ' + date if date else ''})"
    rqs = ", ".join(source.applies_to_rqs)
    name = {"openalex": "OpenAlex", "scopus": "Scopus", "pubmed": "PubMed", "wos": "Web of Science"}[source.type]
    return f"{name}, supplementary search" + (f" for {rqs}" if rqs else "")


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
        sources.append({
            "query_id": search["query_id"],
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
        decided_by[(final.decision, key)] += 1
    human_initials = sorted({f.decided_by.split(":", 1)[1] for f in finals if f.decided_by.startswith("human:")})

    return {
        "sources": sources,
        "identified": sum(s["downloaded"] or 0 for s in sources),
        "not_downloaded": sum((s["total_hits"] or 0) - (s["downloaded"] or 0) for s in sources if s["truncated"]),
        "duplicates_removed": len(duplicates),
        "screened": len(records),
        "screening_decisions_recorded": len(finals),
        "excluded": screening["exclude"],
        "exclusion_reasons": {code: screening["exclusion_reasons"].get(code, 0)
                              for code in REASON_ORDER if screening["exclusion_reasons"].get(code)},
        "pending": screening["pending"],
        "included": screening["include"],
        "included_by_agreement": decided_by[("include", "agreement")],
        "included_by_authors": decided_by[("include", "authors")],
        "excluded_by_agreement": decided_by[("exclude", "agreement")],
        "excluded_by_authors": decided_by[("exclude", "authors")],
        "excluded_by_metadata": decided_by[("exclude", "metadata")],
        "decided_by_authors": decided_by[("include", "authors")] + decided_by[("exclude", "authors")],
        "author_initials": human_initials,
        "agreement": agreement(decisions),
    }


# ── PRISMA flow diagram ─────────────────────────────────────────────────────

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
    source_lines = [f"{s['label']} (n = {s['downloaded']})" for s in counts["sources"]]
    id_text = f"Records identified (n = {counts['identified']})\n" + "\n".join(source_lines)
    id_h = 6 + 2.7 * len(source_lines)
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
    incl_lines = [f"Studies included in the review (n = {counts['included']})",
                  f"By agreement of two AI screeners (n = {counts['included_by_agreement']})",
                  f"By decision of the authors (n = {counts['included_by_authors']})"]
    incl_h = 6 + 2.7 * (len(incl_lines) - 1)
    incl_y = screen_y - 9 - incl_h
    box(left_x, incl_y, left_w, incl_h, "\n".join(incl_lines), palette["box_final"])
    arrow(left_x + left_w / 2, screen_box_y, left_x + left_w / 2, incl_y + incl_h)
    stage(incl_y, incl_h, "Included")
    if counts["pending"]:
        # Not yet decided: shown apart, so that a provisional diagram cannot be mistaken for a final one.
        box(right_x, incl_y + incl_h - 8.7, right_w, 8.7,
            f"Awaiting the authors' decision (n = {counts['pending']})\nProvisional diagram", palette["box_side"],
            dashed=True)

    ax.set_ylim(incl_y - 3, 100)
    return figstyle.save(fig, path_without_extension)


# ── Figures ─────────────────────────────────────────────────────────────────

def draw_included_by_rq(protocol: Protocol, assignments: list[RecordAssignment], path_without_extension) -> list[str]:
    figstyle.apply_style()
    palette = figstyle.PALETTE
    per_rq = summarize(protocol, assignments)["per_rq"]
    rqs = list(per_rq)[::-1]
    core = [per_rq[rq]["core"] for rq in rqs]
    partial = [per_rq[rq]["partial"] for rq in rqs]

    fig, ax = plt.subplots(figsize=(figstyle.FIG_WIDTH, 0.42 * len(rqs) + 1.1))
    ax.barh(rqs, core, color=palette["primary"], label="Core to the question", height=0.62)
    ax.barh(rqs, partial, left=core, color=palette["secondary"], hatch="///", edgecolor="white",
            label="Partially relevant", height=0.62)
    for i, (c, p) in enumerate(zip(core, partial)):
        ax.text(c + p + max(core + partial + [1]) * 0.015, i, f"{c + p}", va="center", fontsize=9,
                color=palette["ink"])
    ax.set_xlabel("Included studies (a study may address several questions)", labelpad=6)
    ax.xaxis.get_major_locator().set_params(integer=True)
    ax.tick_params(axis="y", length=0)
    ax.legend(frameon=False, loc="lower right", bbox_to_anchor=(1.0, 1.0), ncol=2, borderaxespad=0.2)
    return figstyle.save(fig, path_without_extension)


def draw_included_by_year(records: list[Record], path_without_extension, partial_year: int | None = None) -> list[str]:
    figstyle.apply_style()
    palette = figstyle.PALETTE
    years = [r.year for r in records if r.year]
    fig, ax = plt.subplots(figsize=(figstyle.FIG_WIDTH, figstyle.FIG_WIDTH / 2.3))
    if years:
        span = list(range(min(years), max(years) + 1))
        counts = Counter(years)
        bars = ax.bar(span, [counts.get(y, 0) for y in span], color=palette["primary"], width=0.72)
        if partial_year in span:
            bar = bars[span.index(partial_year)]
            bar.set_facecolor(palette["secondary"])
            bar.set_hatch("///")
            bar.set_edgecolor("white")
            ax.text(partial_year, counts.get(partial_year, 0) + max(counts.values()) * 0.03,
                    "partial\nyear", ha="center", va="bottom", fontsize=8, color=palette["muted"])
        ax.set_xticks(span)
        ax.set_ylim(0, max(counts.values()) * 1.22)
    ax.set_ylabel("Included studies", labelpad=6)
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
        9: ("Material available", "Selection process (two AI screeners, decision rule, adjudication by the authors): "
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
    out.append("")
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
    if screeners:
        models = list(dict.fromkeys(s["model"] for s in screeners))
        if len(models) == 1:
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
            "Document type, language and period were checked against the bibliographic metadata.", "",
            "A decision was final only when both models reached it. Records on which the models disagreed, "
            "records either model found unclear, and records without an abstract were decided by the authors.", "",
            "| | Records |", "|---|---|",
            f"| Screened | {counts['screened']} |",
            f"| Excluded from metadata | {counts['excluded_by_metadata']} |",
            f"| Included by agreement of the two models | {counts['included_by_agreement']} |",
            f"| Excluded by agreement of the two models | {counts['excluded_by_agreement']} |",
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
            "sample; its sensitivity and precision are therefore unknown. Agreement between the two models "
            "is reported instead, and all uncertain or contested records were decided by the authors.",
            "- Screening and charting used titles, keywords and abstracts only. Studies whose relevance is "
            "apparent only in the full text may have been excluded, and charted contributions reflect "
            "what the abstract states.",
            "- Results depend on the model versions named above.",
            "- The search string of the original Scopus export was not archived; coverage of that source "
            "cannot be reproduced exactly. Supplementary searches were run in one database (OpenAlex), "
            "whose language and document-type metadata are imperfect.", ""]
    return "\n".join(out)


# ── Everything ──────────────────────────────────────────────────────────────

def build_report(run: Run, protocol: Protocol, partial_year: int | None = None) -> dict:
    """Write every reporting artefact under <run>/report/ and return what was written."""
    out_dir = run.path / "report"
    out_dir.mkdir(exist_ok=True)
    counts = prisma_counts(run, protocol)
    run.write_json("report/prisma_counts.json", counts)
    written = ["report/prisma_counts.json"]

    draw_prisma(counts, out_dir / "prisma_flow")
    written += ["report/prisma_flow.pdf", "report/prisma_flow.png"]

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
        (out_dir / "table_included_by_rq.md").write_text(
            included_by_rq_markdown(protocol, records, assignments), encoding="utf-8")
        header, rows = evidence_rows(protocol, records, assignments)
        _write_csv(out_dir / "evidence_table.csv", header, rows)
        header, rows = citations_by_rq(protocol, records, assignments)
        _write_csv(out_dir / "citations_by_rq.csv", header, rows)
        draw_included_by_rq(protocol, assignments, out_dir / "fig_included_by_rq")
        draw_included_by_year([records[a.record_id] for a in assignments], out_dir / "fig_included_by_year",
                              partial_year=partial_year)
        written += ["report/table_included_by_rq.md", "report/evidence_table.csv", "report/citations_by_rq.csv",
                    "report/fig_included_by_rq.pdf", "report/fig_included_by_rq.png",
                    "report/fig_included_by_year.pdf", "report/fig_included_by_year.png"]

    rows = checklist_rows(counts, has_assignments)
    (out_dir / "prisma_scr_checklist.md").write_text(checklist_markdown(rows), encoding="utf-8")
    _write_csv(out_dir / "prisma_scr_checklist.csv",
               ["number", "section", "item", "description", "status", "where_or_note", "reported_on_page"], rows)
    (out_dir / "methods_appendix.md").write_text(
        methods_appendix(run, protocol, counts, assignment_summary), encoding="utf-8")
    written += ["report/prisma_scr_checklist.md", "report/prisma_scr_checklist.csv", "report/methods_appendix.md"]

    return {"counts": counts, "assignments": assignment_summary, "written": written,
            "directory": str(Path(out_dir))}
