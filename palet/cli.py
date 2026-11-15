"""Command line of PALET 2.0 (review workflow on a run directory).

    python -m palet init     --protocol config/protocol.yaml --label "chapter"
    python -m palet search   --run <run> --source <source id> [--count-only]
    python -m palet dedup    --run <run>
    python -m palet screen   --run <run> [--limit N] [--estimate] [--replay]
    python -m palet adjudicate --run <run> --file adjudication.xlsx --initials XX
    python -m palet assign   --run <run> [--estimate] [--replay]
    python -m palet report   --run <run>
    python -m palet check-citations --manuscript chapter.docx [--run <run>]
    python -m palet approve-search --protocol config/protocol.yaml --source <source id> --by XX
    python -m palet set-protocol --run <run> --protocol config/protocol_v2.yaml
    python -m palet reparse  --run <run>
    python -m palet journals --run <run>
    python -m palet status   --run <run>

Messages for the user are in Spanish; code and artefacts are in English.
"""

import argparse
import csv
import json
import re
import sys
from datetime import date
from pathlib import Path

from palet import adjudication, assign, citations, config, drafting, journals, llm, report, screening
from palet.dedup import deduplicate
from palet.errors import PaletError
from palet.importers import import_scopus_csv
from palet.models import Record
from palet.protocol import load_protocol, require_approved
from palet.runs import ROOT, RUNS_DIR, Run
from palet.search import build_query, openalex_filter, openalex_work_to_record, sample_openalex, search_openalex


def _open_run(value: str) -> Run:
    path = Path(value)
    if not path.exists():
        path = RUNS_DIR / value
    return Run.open(path)


def _protocol_of(run: Run):
    info = run.manifest.get("protocol")
    if not info:
        raise PaletError("This run has no protocol recorded")
    path = Path(info["path"])
    if not path.is_absolute():
        path = ROOT / path
    elif not path.is_file() and (ROOT / "config" / path.name).is_file():
        path = ROOT / "config" / path.name          # run created in another checkout of the repository
    return path, load_protocol(path)


def _load_sources(run: Run) -> list[Record]:
    records = []
    for path in sorted((run.path / "sources").glob("*.jsonl")):
        records.extend(run.read_models(f"sources/{path.name}", Record))
    return records


def _do_dedup(run: Run) -> dict:
    result = deduplicate(_load_sources(run))
    run.write_models("records.jsonl", result.records)
    run.write_models("duplicates.jsonl", result.duplicates)
    with open(run.file("dedup_review.csv"), "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["record_id_a", "record_id_b", "similarity", "reason", "title_a", "title_b"])
        for pair in result.doubtful:
            writer.writerow([pair.record_id_a, pair.record_id_b, pair.similarity, pair.reason,
                             pair.title_a, pair.title_b])
    run.write_json("dedup_merges.json", result.merges)
    run.log_step("dedup", **result.stats)
    return result.stats


# ── init ────────────────────────────────────────────────────────────────────

def cmd_init(args) -> int:
    protocol_path = Path(args.protocol).resolve()
    protocol = load_protocol(protocol_path)
    run = Run.create(args.label, run_id=args.run_id)
    run.record_protocol(protocol_path, protocol)
    print(f"Ejecución creada: {run.path}")

    for source in protocol.sources:
        if source.type != "manual_import":
            continue
        file_path = Path(source.model_extra.get("file", ""))
        if not file_path.is_absolute():
            file_path = ROOT / file_path
        records = import_scopus_csv(file_path, query_id=source.id)
        run.write_models(f"sources/{source.id}.jsonl", records)
        run.record_search({
            "query_id": source.id, "source": "manual_import",
            "platform": source.model_extra.get("platform"),
            "query_string": source.model_extra.get("query_string"),
            "executed_at": source.model_extra.get("exported_at"),
            "total_hits": len(records), "downloaded": len(records), "truncated": False,
            "file": str(file_path), "note": "search string not archived" if not source.model_extra.get("query_string") else "",
        })
        print(f"  {source.id}: {len(records)} registros importados")

    stats = _do_dedup(run)
    print(f"Deduplicación: {stats['input']} → {stats['unique']} únicos "
          f"({stats['duplicates_removed']} duplicados, {stats['doubtful_pairs']} pares dudosos)")
    return 0


# ── search ──────────────────────────────────────────────────────────────────

def cmd_search(args) -> int:
    run = _open_run(args.run)
    _, protocol = _protocol_of(run)
    source = protocol.source(args.source)
    if source.type != "openalex":
        raise PaletError(f"La fuente '{source.id}' no es de tipo openalex")
    blocks = source.model_extra.get("blocks")
    if not blocks:
        raise PaletError(f"La fuente '{source.id}' no tiene bloques de términos (blocks) en el protocolo")
    query = build_query(blocks)
    approved = source.model_extra.get("status") == "approved"

    # A source may narrow the languages of the protocol (never widen them).
    languages = source.model_extra.get("languages") or protocol.languages
    not_allowed = sorted(set(languages) - set(protocol.languages))
    if not_allowed:
        raise PaletError(f"La fuente '{source.id}' pide idiomas que el protocolo no admite: {not_allowed}")
    limits = dict(year_from=protocol.year_from, year_to=protocol.year_to,
                  document_types=protocol.document_types, languages=languages)
    print(f"Fuente: {source.id}\nCadena ({len(query)} caracteres):\n  {query}\n")
    print("Filtros del protocolo aplicados (también con --count-only y --sample): "
          f"años {protocol.year_from}–{protocol.year_to}, tipos {'|'.join(protocol.document_types)}, "
          f"idiomas {'|'.join(languages)}; búsqueda solo en título y resumen.")
    if args.show_filter:
        print(f"Filtro enviado a OpenAlex:\n  {openalex_filter(query, **limits)}\n")

    if args.sample:
        works, total, _ = sample_openalex(query, n=args.sample, seed=args.seed, **limits)
        print(f"Resultados totales (con filtros): {total}")
        print(f"Muestra aleatoria de {len(works)} títulos (semilla {args.seed}); no se criba ni se registra nada:\n")
        rows = []
        for i, work in enumerate(works, 1):
            journal = ((work.get("primary_location") or {}).get("source") or {}).get("display_name") or ""
            title = " ".join(str(work.get("title") or "(sin título)").split())
            rows.append([i, work.get("publication_year"), work.get("type"), work.get("language"), title, journal,
                         work.get("doi") or work.get("id")])
            print(f"{i:>2}. [{work.get('publication_year')}] {title}" + (f" — {journal}" if journal else ""))
        path = run.file(f"previews/{source.id}_sample_n{args.sample}_seed{args.seed}.csv")
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["n", "year", "type", "language", "title", "source", "link"])
            writer.writerows(rows)
        print(f"\nGuardado también en: {path}")
        return 0

    if not args.count_only and not approved:
        raise PaletError(
            f"La cadena de '{source.id}' aún no está aprobada (status: {source.model_extra.get('status')}). "
            "Usa --count-only para ver el recuento y pon status: approved en el protocolo cuando la deis por buena."
        )

    works, execution = search_openalex(
        source.id, query, **limits,
        max_records=args.max_records, count_only=args.count_only, allow_truncation=args.allow_truncation,
    )
    print(f"Resultados totales en OpenAlex (con filtros): {execution['total_hits']} "
          f"(consultado {execution['executed_at']})")
    if args.count_only:
        print("Solo recuento: no se ha descargado ni registrado nada.")
        return 0

    records = [openalex_work_to_record(work, source.id) for work in works]
    run.write_models(f"sources/{source.id}.jsonl", records)
    run.write_json(f"sources/{source.id}_raw.json", works)
    manifest = run.manifest
    manifest["searches"] = [s for s in manifest["searches"] if s["query_id"] != source.id] + [execution]
    run._save(manifest)
    print(f"Descargados: {execution['downloaded']}" + ("  ¡TRUNCADA!" if execution["truncated"] else ""))

    stats = _do_dedup(run)
    print(f"Deduplicación: {stats['input']} → {stats['unique']} únicos "
          f"({stats['duplicates_removed']} duplicados, {stats['doubtful_pairs']} pares dudosos)")
    return 0


def cmd_dedup(args) -> int:
    run = _open_run(args.run)
    stats = _do_dedup(run)
    print(json.dumps(stats, indent=2, ensure_ascii=False))
    return 0


# ── screen ──────────────────────────────────────────────────────────────────

def _estimate(protocol, records, screeners) -> list[dict]:
    """Rough cost per screener: 4 characters per token, ~1,300 output tokens per call."""
    system = screening.build_system_prompt(protocol)
    to_model = [r for r in records if screening.metadata_decision(protocol, r) is None]
    input_tokens = sum((len(system) + len(screening.build_user_message(r))) / 4 for r in to_model)
    output_tokens = 1300 * len(to_model)
    rows = []
    for screener in screeners:
        price_in, price_out = config.get_price(screener["model"])
        rows.append({"screener": screener["name"], "model": screener["model"], "calls": len(to_model),
                     "input_tokens": int(input_tokens), "output_tokens": output_tokens,
                     "cost_usd": round((input_tokens * price_in + output_tokens * price_out) / 1e6, 2)})
    return rows


def _write_screening_outputs(run: Run, records, decisions, finals) -> None:
    by_id = {r.record_id: r for r in records}
    run.write_models("decisions.jsonl", decisions)
    run.write_models("final_decisions.jsonl", finals)
    with open(run.file("screening_summary.csv"), "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["record_id", "title", "year", "source_title", "found_by", "decision", "reason_code",
                         "reasons_shared", "decided_by", "pending_reason", "screeners"])
        for final in finals:
            record = by_id[final.record_id]
            writer.writerow([record.record_id, record.title, record.year, record.source_title,
                             "; ".join(record.found_by_queries), final.decision, final.reason_code or "",
                             "" if final.reasons_shared is None else final.reasons_shared,
                             final.decided_by, final.pending_reason or "",
                             "; ".join(f"{k}={v}" for k, v in final.screener_decisions.items())])
    status = {"include": "ta_included", "exclude": "ta_excluded", "pending": "ta_unclear"}
    final_by_id = {f.record_id: f for f in finals}
    updated = [r.model_copy(update={"status": status[final_by_id[r.record_id].decision]})
               if r.record_id in final_by_id else r for r in run.read_models("records.jsonl", Record)]
    run.write_models("records.jsonl", updated)
    pending = adjudication.export_pending(run.file("adjudication.xlsx"), records, decisions, finals)
    stats = {"summary": screening.summarize(finals), "agreement": screening.agreement(decisions),
             "pending_for_humans": pending}
    run.write_json("screening_stats.json", stats)


def _apply_saved_human_decisions(run: Run, finals):
    path = run.path / "human_decisions.jsonl"
    if not path.is_file():
        return finals, []
    human = run.read_models("human_decisions.jsonl", screening.ScreeningDecision)
    latest = {d.record_id: d for d in human}
    updated = []
    for final in finals:
        decision = latest.get(final.record_id)
        if decision is not None and final.decision == "pending":
            final = final.model_copy(update={
                "decision": decision.decision, "reason_code": decision.reason_code,
                "decided_by": decision.screener, "pending_reason": None,
                "screener_decisions": {**final.screener_decisions, decision.screener: decision.decision}})
        updated.append(final)
    return updated, list(latest.values())


def cmd_screen(args) -> int:
    run = _open_run(args.run)
    protocol_path, protocol = _protocol_of(run)
    require_approved(protocol)
    run.record_protocol(protocol_path, protocol)
    settings = config.get_screening_settings()
    screeners = settings["screeners"]
    if args.screeners:
        screeners = config.make_screeners(args.screeners.split(","))
    records = run.read_models("records.jsonl", Record)
    if args.limit:
        records = records[:args.limit]

    estimate = _estimate(protocol, records, screeners)
    print(f"Registros a cribar: {len(records)} ({estimate[0]['calls']} van al modelo; el resto se decide por metadatos)")
    for row in estimate:
        print(f"  Cribador {row['screener']} ({row['model']}): ~{row['input_tokens']:,} tokens de entrada, "
              f"~{row['output_tokens']:,} de salida ≈ {row['cost_usd']} $")
    print(f"  Estimación total: ≈ {sum(r['cost_usd'] for r in estimate):.2f} $ "
          "(menos si parte está ya en la caché)")
    if len(screeners) == 1:
        print("  AVISO: un solo cribador. Sus decisiones serán firmes sin contraste; solo irán a revisión "
              "humana los registros dudosos, con error o sin resumen.")
    elif screeners[0]["model"] == screeners[1]["model"]:
        print("  AVISO: los dos cribadores usan el mismo modelo; su acuerdo mide la consistencia del modelo, "
              "no un contraste entre evaluadores distintos.")
    if args.estimate:
        return 0

    llm.configure(replay=args.replay)
    llm.reset_usage()
    workers = args.workers or settings["workers"]

    def progress(done, total):
        print(f"  {done}/{total} llamadas", flush=True)

    decisions, finals, prompt_sha = screening.screen_records(protocol, records, screeners,
                                                             workers=workers, progress=progress)
    finals, human = _apply_saved_human_decisions(run, finals)
    decisions = decisions + human

    manifest = run.manifest
    manifest["prompts"]["screen_system_v1"] = prompt_sha
    run._save(manifest)
    _write_screening_outputs(run, records, decisions, finals)
    summary = screening.summarize(finals)
    stats = screening.agreement(decisions)
    run.log_step("screen", limit=args.limit, screeners=screeners, replay=args.replay, **summary)
    run.record_llm_usage("screen")

    usage = llm.usage_summary()
    spent = sum(phase["cost_usd"] for phase in usage.values())
    cached = sum(phase["cached_calls"] for phase in usage.values())
    calls = sum(phase["calls"] for phase in usage.values())
    print(f"\nIncluidos: {summary['include']} | Excluidos: {summary['exclude']} | "
          f"Pendientes de decisión humana: {summary['pending']}")
    if summary["exclusion_reasons"]:
        print("Razones de exclusión: " + ", ".join(f"{k}={v}" for k, v in summary["exclusion_reasons"].items()))
    if stats.get("records_compared"):
        print(f"Acuerdo entre cribadores: {stats['same_decision']}/{stats['records_compared']} "
              f"({stats['percent_agreement']} %), kappa de Cohen = {stats['cohen_kappa']}")
    print(f"Llamadas: {calls} ({cached} desde la caché). Coste de esta ejecución: {spent:.2f} $")
    print(f"Excel para adjudicar: {run.path / 'adjudication.xlsx'}")
    return 0


# ── adjudicate ──────────────────────────────────────────────────────────────

def cmd_adjudicate(args) -> int:
    run = _open_run(args.run)
    finals = run.read_models("final_decisions.jsonl", screening.FinalDecision)
    records = run.read_models("records.jsonl", Record)
    decisions = run.read_models("decisions.jsonl", screening.ScreeningDecision)
    updated, human, report = adjudication.import_decisions(args.file, finals, args.initials)

    previous = []
    if (run.path / "human_decisions.jsonl").is_file():
        previous = run.read_models("human_decisions.jsonl", screening.ScreeningDecision)
    run.write_models("human_decisions.jsonl", previous + human)
    model_decisions = [d for d in decisions if not d.screener.startswith("human:")]
    _write_screening_outputs(run, records, model_decisions + previous + human, updated)
    summary = screening.summarize(updated)
    run.log_step("adjudicate", file=str(args.file), initials=args.initials.upper(), **report, **summary)
    print(f"Decisiones humanas importadas: {report['adjudicated']} "
          f"(en blanco: {report['left_blank']}; siguen pendientes: {report['still_pending']})")
    print(f"Incluidos: {summary['include']} | Excluidos: {summary['exclude']} | Pendientes: {summary['pending']}")
    return 0


# ── assign ──────────────────────────────────────────────────────────────────

def cmd_assign(args) -> int:
    run = _open_run(args.run)
    _, protocol = _protocol_of(run)
    finals = run.read_models("final_decisions.jsonl", screening.FinalDecision)
    included_ids = [f.record_id for f in finals if f.decision == "include"]
    pending = sum(f.decision == "pending" for f in finals)
    by_id = {r.record_id: r for r in run.read_models("records.jsonl", Record)}
    records = [by_id[i] for i in included_ids]
    model = args.model or config.get_assignment_model()
    if model not in {m["id"] for m in config.list_models()}:
        raise PaletError(f"El modelo no está en el catálogo de palet.toml: {model}")

    system = assign.build_system_prompt(protocol)
    input_tokens = sum((len(system) + len(screening.build_user_message(r))) / 4 for r in records) * 1.35
    price_in, price_out = config.get_price(model)
    estimate = (input_tokens * price_in + 1100 * len(records) * price_out) / 1e6
    print(f"Registros incluidos a asignar: {len(records)} (modelo {model}); estimación ≈ {estimate:.2f} $")
    if pending:
        print(f"AVISO: quedan {pending} registros pendientes de decisión humana; no se asignan hasta que se decidan.")
    if args.estimate or not records:
        return 0

    llm.configure(replay=args.replay)
    llm.reset_usage()
    workers = args.workers or config.get_screening_settings()["workers"]
    results, prompt_sha = assign.assign_records(
        protocol, records, model, workers=workers,
        progress=lambda done, total: print(f"  {done}/{total} registros", flush=True))
    run.write_models("assignments.jsonl", results)
    manifest = run.manifest
    manifest["prompts"]["assign_system_v1"] = prompt_sha
    run._save(manifest)
    summary = assign.summarize(protocol, results)
    run.log_step("assign", model=model, replay=args.replay, **summary)
    run.record_llm_usage("assign")

    usage = llm.usage_summary().get("assign", {})
    print("\nEstudios por pregunta (principal / parcial):")
    for rq, n in summary["per_rq"].items():
        print(f"  {rq}: {n['core']} / {n['partial']}")
    print(f"En varias preguntas: {summary['assigned_to_several_rqs']} | Sin ninguna: "
          f"{summary['not_assigned_to_any_rq']} | Errores: {summary['errors']} | A revisar: {summary['needs_review']}")
    print(f"Llamadas: {usage.get('calls', 0)} ({usage.get('cached_calls', 0)} desde la caché). "
          f"Coste de esta ejecución: {usage.get('cost_usd', 0):.2f} $")
    return 0


# ── report ──────────────────────────────────────────────────────────────────

def cmd_report(args) -> int:
    run = _open_run(args.run)
    _, protocol = _protocol_of(run)
    result = report.build_report(run, protocol, partial_year=args.partial_year)
    counts = result["counts"]
    run.log_step("report", included=counts["included"], excluded=counts["excluded"], pending=counts["pending"])
    print(f"Identificados: {counts['identified']} | Duplicados: {counts['duplicates_removed']} | "
          f"Cribados: {counts['screened']} | Excluidos: {counts['excluded']} | Incluidos: {counts['included']} | "
          f"Pendientes: {counts['pending']}")
    if counts["pending"]:
        print("AVISO: hay registros pendientes de decisión humana; el diagrama y las tablas son provisionales.")
    if result["assignments"] is None:
        print("AVISO: falta la asignación a preguntas (python -m palet assign); sin tablas ni figuras por RQ.")
    print(f"Ficheros en {result['directory']}:")
    for name in result["written"]:
        print(f"  {name}")
    return 0


# ── check-citations ─────────────────────────────────────────────────────────

def cmd_check_citations(args) -> int:
    paragraphs = citations.read_paragraphs(args.manuscript)
    body, references = citations.split_manuscript(paragraphs, args.body_start, args.references_heading)
    result = citations.check_citations(body, references)
    text = citations.format_report(result)
    if args.run:
        run = _open_run(args.run)
        out_dir = run.path / "report"
    else:
        out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "citation_check.md").write_text(text, encoding="utf-8")
    (out_dir / "citation_check.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Referencias en la lista: {result['references_in_list']} | Citas en el texto: {result['citations_found']}")
    print(f"Citadas y no listadas: {len(result['cited_not_listed'])} | Listadas y no citadas: "
          f"{len(result['listed_not_cited'])} | Autores que no coinciden: {len(result['author_mismatches'])} | "
          f"Grafías distintas: {len(result['probable_spelling_variants'])} | "
          f"Necesitan a/b: {len(result['same_authors_and_year'])}")
    print(f"Informe: {out_dir / 'citation_check.md'}")
    return 0


# ── approve-search ──────────────────────────────────────────────────────────

def cmd_approve_search(args) -> int:
    """Mark one search of the protocol as approved (a deliberate act of the authors)."""
    path = Path(args.protocol)
    protocol = load_protocol(path)
    source = protocol.source(args.source)
    if source.model_extra.get("status") == "approved":
        print(f"La búsqueda '{source.id}' ya estaba aprobada.")
        return 0
    text = path.read_text(encoding="utf-8")
    block = re.search(rf"(^  - id: {re.escape(source.id)}[ \t]*(?:#[^\n]*)?\n)(.*?)(?=^  - id: |^\S|\Z)",
                      text, flags=re.M | re.S)
    if not block or "status: proposed" not in block.group(2):
        raise PaletError(f"No encuentro 'status: proposed' en la fuente '{source.id}' del protocolo")
    stamp = f"status: approved\n    approved_by: \"{args.by}\"\n    approved_at: {date.today().isoformat()}"
    new_block = block.group(1) + block.group(2).replace("status: proposed", stamp, 1)
    path.write_text(text[:block.start()] + new_block + text[block.end():], encoding="utf-8")
    load_protocol(path)                       # the file must still be a valid protocol
    print(f"Búsqueda '{source.id}' aprobada por {args.by} el {date.today().isoformat()}.")
    print(f"Cadena aprobada:\n  {build_query(source.model_extra['blocks'])}")
    return 0


# ── set-protocol / reparse / journals ───────────────────────────────────────

def cmd_set_protocol(args) -> int:
    """Point a run at a new version of its protocol (criteria changed; decisions must be redone)."""
    run = _open_run(args.run)
    path = Path(args.protocol).resolve()
    protocol = load_protocol(path)
    previous = run.manifest.get("protocol") or {}
    run.record_protocol(path, protocol)
    run.log_step("set_protocol", previous_version=previous.get("version"), previous_sha256=previous.get("sha256"),
                 version=protocol.version, sha256=run.manifest["protocol"]["sha256"])
    print(f"Protocolo de la ejecución: v{previous.get('version')} → v{protocol.version} ({protocol.status}).")
    print("Vuelve a lanzar el cribado para aplicar los criterios nuevos (con --replay no se gasta nada "
          "si las respuestas ya están en la caché).")
    return 0


def cmd_reparse(args) -> int:
    """Rebuild the records of every source from the raw data kept in the run, then deduplicate.

    Needed when the parser learns to read a new field (e.g. the ISSN). Nothing is downloaded.
    """
    run = _open_run(args.run)
    _, protocol = _protocol_of(run)
    for search in run.manifest["searches"]:
        source_id = search["query_id"]
        raw = run.path / "sources" / f"{source_id}_raw.json"
        if raw.is_file():
            works = json.loads(raw.read_text(encoding="utf-8"))
            records = [openalex_work_to_record(work, source_id) for work in works]
        elif search.get("source") == "manual_import":
            file_path = Path(protocol.source(source_id).model_extra.get("file", ""))
            records = import_scopus_csv(file_path if file_path.is_absolute() else ROOT / file_path,
                                        query_id=source_id)
        else:
            raise PaletError(f"No hay datos en bruto para la fuente '{source_id}'")
        before = len(run.read_models(f"sources/{source_id}.jsonl", Record))
        if len(records) != before:
            raise PaletError(f"'{source_id}': al releer salen {len(records)} registros y había {before}; no se cambia nada")
        run.write_models(f"sources/{source_id}.jsonl", records)
        print(f"  {source_id}: {len(records)} registros releídos, {sum(bool(r.issn) for r in records)} con ISSN")
    stats = _do_dedup(run)
    print(f"Deduplicación: {stats['input']} → {stats['unique']} únicos")
    return 0


def cmd_journals(args) -> int:
    """Show which records are in the journal lists of the protocol. Changes no decision."""
    run = _open_run(args.run)
    _, protocol = _protocol_of(run)
    index = journals.index_for(protocol, ROOT)
    if index is None:
        raise PaletError("El protocolo de esta ejecución no tiene listas de revistas (journal_lists)")
    for item in index.files:
        print(f"Lista {item['id']}: {item['journals']} revistas ({item['file']})")
    records = run.read_models("records.jsonl", Record)
    per_source: dict = {}
    how_counts: dict = {}
    with open(run.file("journal_check.csv"), "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["record_id", "in_list", "how", "journal", "issn", "year", "title", "found_by"])
        for record in records:
            listed, how = index.check(record)
            how_counts[how] = how_counts.get(how, 0) + 1
            for source_id in record.found_by_queries:
                row = per_source.setdefault(source_id, [0, 0])
                row[0 if listed else 1] += 1
            writer.writerow([record.record_id, listed, how, record.source_title, "; ".join(record.issn),
                             record.year, record.title, "; ".join(record.found_by_queries)])
    listed_total = sum(n for how, n in how_counts.items() if how in ("issn", "title"))
    print(f"\nRegistros únicos: {len(records)} | en las listas: {listed_total} | fuera: {len(records) - listed_total}")
    for how, n in sorted(how_counts.items(), key=lambda kv: -kv[1]):
        print(f"  {n:>5}  {how}")
    print("\nPor fuente (en lista / fuera):")
    for source_id, (inside, outside) in sorted(per_source.items()):
        print(f"  {source_id}: {inside} / {outside}")
    print(f"Detalle: {run.path / 'journal_check.csv'}")
    return 0


# ── protocol assistant ──────────────────────────────────────────────────────

def cmd_draft_protocol(args) -> int:
    """Draft a protocol from a context and research questions (advice first, then the draft)."""
    context = Path(args.context).read_text(encoding="utf-8")
    questions = drafting.clean_questions(Path(args.questions).read_text(encoding="utf-8").splitlines())
    llm.reset_usage()
    analysis = drafting.analyse_questions(context, questions, args.model)
    print(f"Valoración general: {analysis.overall}\n")
    for advice, original in zip(analysis.questions, questions):
        print(f"{advice.id} [{advice.change}]\n  original:  {original}")
        if advice.change != "none":
            print(f"  sugerida:  {advice.suggested}\n  motivo:    {advice.rationale}")
        for issue in advice.issues:
            print(f"  - {issue}")
    for gap in analysis.gaps:
        print(f"Sin cubrir: {gap}")
    if args.analyse_only:
        return 0
    final = [a.suggested for a in analysis.questions] if args.accept_suggestions else questions
    draft = drafting.draft_protocol(context, final, args.model)
    path = ROOT / "config" / f"{drafting.slug(args.name)}.yaml"
    drafting.write_protocol(path, drafting.protocol_data(draft, final, questions), context)
    cost = sum(phase["cost_usd"] for phase in llm.usage_summary().values())
    print(f"\nProtocolo en borrador: {path}  (coste ≈ {cost:.2f} $)")
    print("Revísalo y edítalo. Cuando los autores estén de acuerdo:\n"
          f"  python -m palet approve-protocol --protocol {path.relative_to(ROOT)} --by \"<nombres>\"")
    return 0


def cmd_approve_protocol(args) -> int:
    path = Path(args.protocol)
    drafting.approve_protocol(path if path.is_absolute() else ROOT / path, args.by)
    print(f"Protocolo {path.name} aprobado por {args.by} el {date.today().isoformat()}.")
    return 0


# ── status ──────────────────────────────────────────────────────────────────

def cmd_status(args) -> int:
    run = _open_run(args.run)
    manifest = run.manifest
    print(f"Ejecución: {manifest['run_id']}  (commit {str(manifest['git_commit'])[:7]}, PALET {manifest['palet_version']})")
    protocol = manifest.get("protocol") or {}
    print(f"Protocolo: v{protocol.get('version')} {protocol.get('status')} sha256={str(protocol.get('sha256'))[:12]}")
    for search in manifest["searches"]:
        print(f"  búsqueda {search['query_id']}: {search['total_hits']} resultados, "
              f"{search['downloaded']} descargados ({search.get('executed_at')})")
    for step in manifest["steps"]:
        info = {k: v for k, v in step.items() if k not in ("step", "at", "screeners")}
        print(f"  {step['at']}  {step['step']}: {info}")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="python -m palet", description="PALET 2.0 review workflow")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="create a run and import the manual sources of the protocol")
    p.add_argument("--protocol", required=True)
    p.add_argument("--label", required=True)
    p.add_argument("--run-id", default=None)
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("search", help="run a supplementary OpenAlex search defined in the protocol")
    p.add_argument("--run", required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--count-only", action="store_true")
    p.add_argument("--max-records", type=int, default=500)
    p.add_argument("--allow-truncation", action="store_true")
    p.add_argument("--sample", type=int, default=None, metavar="N",
                   help="show N random titles (fixed seed) and stop; nothing is screened or recorded")
    p.add_argument("--seed", type=int, default=20261112)
    p.add_argument("--show-filter", action="store_true", help="print the exact filter sent to OpenAlex")
    p.set_defaults(func=cmd_search)

    p = sub.add_parser("dedup", help="deduplicate all sources of the run")
    p.add_argument("--run", required=True)
    p.set_defaults(func=cmd_dedup)

    p = sub.add_parser("screen", help="screen records against the protocol criteria")
    p.add_argument("--run", required=True)
    p.add_argument("--limit", type=int, default=None, help="screen only the first N records (pilot)")
    p.add_argument("--workers", type=int, default=None)
    p.add_argument("--estimate", action="store_true", help="print the cost estimate and stop")
    p.add_argument("--replay", action="store_true", help="use only cached responses; never call the API")
    p.add_argument("--screeners", default=None, metavar="MODEL[,MODEL]",
                   help="one or two model ids for this run, instead of the screeners of palet.toml")
    p.set_defaults(func=cmd_screen)

    p = sub.add_parser("adjudicate", help="import the human decisions from the filled workbook")
    p.add_argument("--run", required=True)
    p.add_argument("--file", required=True)
    p.add_argument("--initials", required=True)
    p.set_defaults(func=cmd_adjudicate)

    p = sub.add_parser("assign", help="chart included records: research questions and contribution")
    p.add_argument("--run", required=True)
    p.add_argument("--model", default=None, help="model id for this run, instead of [assignment] in palet.toml")
    p.add_argument("--workers", type=int, default=None)
    p.add_argument("--estimate", action="store_true")
    p.add_argument("--replay", action="store_true")
    p.set_defaults(func=cmd_assign)

    p = sub.add_parser("report", help="PRISMA flow, checklist, methods appendix, tables and figures")
    p.add_argument("--run", required=True)
    p.add_argument("--partial-year", type=int, default=None, help="year to mark as incomplete in the figure by year")
    p.set_defaults(func=cmd_report)

    p = sub.add_parser("check-citations", help="compare the citations of a manuscript with its reference list")
    p.add_argument("--manuscript", required=True)
    p.add_argument("--run", default=None, help="write the report into this run (otherwise into --out)")
    p.add_argument("--out", default=".")
    p.add_argument("--body-start", default="Abstract")
    p.add_argument("--references-heading", default="References")
    p.set_defaults(func=cmd_check_citations)

    p = sub.add_parser("approve-search", help="mark a search string of the protocol as approved")
    p.add_argument("--protocol", required=True)
    p.add_argument("--source", required=True)
    p.add_argument("--by", required=True, help="who approves it (initials or names)")
    p.set_defaults(func=cmd_approve_search)

    p = sub.add_parser("set-protocol", help="point a run at a new version of its protocol")
    p.add_argument("--run", required=True)
    p.add_argument("--protocol", required=True)
    p.set_defaults(func=cmd_set_protocol)

    p = sub.add_parser("reparse", help="rebuild records from the raw data of the run (no download)")
    p.add_argument("--run", required=True)
    p.set_defaults(func=cmd_reparse)

    p = sub.add_parser("journals", help="which records are in the journal lists of the protocol")
    p.add_argument("--run", required=True)
    p.set_defaults(func=cmd_journals)

    p = sub.add_parser("draft-protocol", help="advice on the research questions and a draft protocol")
    p.add_argument("--context", required=True, help="text file: what the review is about")
    p.add_argument("--questions", required=True, help="text file: one research question per line")
    p.add_argument("--name", default="draft", help="name of the protocol file to write in config/")
    p.add_argument("--analyse-only", action="store_true", help="only print the advice on the questions")
    p.add_argument("--accept-suggestions", action="store_true", help="draft with the suggested wordings")
    p.add_argument("--model", default=None, help="model id, instead of [assistant] in palet.toml")
    p.set_defaults(func=cmd_draft_protocol)

    p = sub.add_parser("approve-protocol", help="mark a draft protocol as approved by the authors")
    p.add_argument("--protocol", required=True)
    p.add_argument("--by", required=True)
    p.set_defaults(func=cmd_approve_protocol)

    p = sub.add_parser("status", help="show what has been done in a run")
    p.add_argument("--run", required=True)
    p.set_defaults(func=cmd_status)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except PaletError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
