"""Command line of PALET 2.0 (review workflow on a run directory).

    python -m palet init     --protocol config/protocol.yaml --label "chapter"
    python -m palet search   --run <run> --source <source id> [--count-only]
    python -m palet dedup    --run <run>
    python -m palet screen   --run <run> [--limit N] [--estimate] [--replay]
    python -m palet adjudicate --run <run> --file adjudication.xlsx --initials XX
    python -m palet status   --run <run>

Messages for the user are in Spanish; code and artefacts are in English.
"""

import argparse
import csv
import json
import sys
from pathlib import Path

from palet import adjudication, config, llm, screening
from palet.dedup import deduplicate
from palet.errors import PaletError
from palet.importers import import_scopus_csv
from palet.models import Record
from palet.protocol import load_protocol, require_approved
from palet.runs import ROOT, RUNS_DIR, Run
from palet.search import build_query, openalex_work_to_record, search_openalex


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

    print(f"Fuente: {source.id}\nCadena ({len(query)} caracteres):\n  {query}\n")
    if not args.count_only and not approved:
        raise PaletError(
            f"La cadena de '{source.id}' aún no está aprobada (status: {source.model_extra.get('status')}). "
            "Usa --count-only para ver el recuento y pon status: approved en el protocolo cuando la deis por buena."
        )

    works, execution = search_openalex(
        source.id, query, year_from=protocol.year_from, year_to=protocol.year_to,
        document_types=protocol.document_types, languages=protocol.languages,
        max_records=args.max_records, count_only=args.count_only, allow_truncation=args.allow_truncation,
    )
    print(f"Resultados totales en OpenAlex: {execution['total_hits']} (consultado {execution['executed_at']})")
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
    p.set_defaults(func=cmd_screen)

    p = sub.add_parser("adjudicate", help="import the human decisions from the filled workbook")
    p.add_argument("--run", required=True)
    p.add_argument("--file", required=True)
    p.add_argument("--initials", required=True)
    p.set_defaults(func=cmd_adjudicate)

    p = sub.add_parser("status", help="show what has been done in a run")
    p.add_argument("--run", required=True)
    p.set_defaults(func=cmd_status)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except PaletError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1
