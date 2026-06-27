#!/usr/bin/env python3
"""
PALET GUI — FastAPI backend
Servidor local para la interfaz gráfica de PALET.
Lanzar desde el directorio raíz de PALET:
    uvicorn app:app --reload --port 8000
"""

import os
import sys
import json
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse, FileResponse

# ── Paths ────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = BASE_DIR / "scripts"
PROMPTS_DIR = BASE_DIR / "prompts"
RESULTS_DIR = BASE_DIR / "results"
HISTORY_FILE = BASE_DIR / "runs_history.json"

# Añadir scripts/ al path para importar módulos PALET
sys.path.insert(0, str(SCRIPTS_DIR))

# ── FastAPI app ──────────────────────────────────────────────────────────
app = FastAPI(title="PALET GUI", version="1.0.0")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# ── Estado global del pipeline en ejecución ──────────────────────────────
pipeline_state = {
    "running": False,
    "phase": None,
    "phase_index": 0,
    "total_phases": 7,
    "message": "",
    "completed_phases": [],
    "error": None,
    "result": None,
    "auto_accept": True,
    "waiting_approval": False,
    "seed_prompt_text": "",
    "params": {},
}

PHASES = ["ARQ", "QSP", "SE", "MAP", "PRISMA", "Synthesis", "Report"]


# ── Historial ────────────────────────────────────────────────────────────

def load_history():
    if HISTORY_FILE.exists():
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_history(runs: list):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(runs, f, indent=2, ensure_ascii=False)


def add_run_to_history(run_data: dict):
    runs = load_history()
    runs.insert(0, run_data)
    save_history(runs)


# ── Estimación de coste ──────────────────────────────────────────────────

def estimate_cost(seed_prompt: str, max_results: int) -> dict:
    """
    Estima el coste aproximado del pipeline completo.
    Precios Claude Sonnet 4.5: input $3/MTok, output $15/MTok
    IMPORTANTE: verificar precios actuales en docs.anthropic.com
    """
    INPUT_PRICE_PER_MTOK = 3.0   # USD
    OUTPUT_PRICE_PER_MTOK = 15.0  # USD

    # Estimación de tokens por carácter (aprox 1 token = 4 chars en inglés)
    chars_per_token = 4

    # ARQ: system prompt (~4000 tokens) + seed prompt + respuesta (~2000 tokens)
    arq_system_tokens = 4000
    arq_seed_tokens = len(seed_prompt) / chars_per_token
    arq_input = arq_system_tokens + arq_seed_tokens
    arq_output = 2000

    # QSP: system prompt (~2000 tokens) + keywords (~500 tokens) + respuesta (~1000 tokens)
    qsp_input = 2500
    qsp_output = 1000

    # MAP: por cada paper, system prompt (~6000 tokens) + abstract (~300 tokens) + respuesta (~200 tokens)
    # Se procesan en batches de 5, pero el coste total es similar
    map_input_per_paper = 6300
    map_output_per_paper = 200
    map_input = map_input_per_paper * max_results
    map_output = map_output_per_paper * max_results

    # Synthesis: system prompt (~3000 tokens) + context (~2000 tokens per RQ, ~4 RQs) + respuesta
    synth_input = 3000 + 2000 * 4
    synth_output = 4000

    total_input = arq_input + qsp_input + map_input + synth_input
    total_output = arq_output + qsp_output + map_output + synth_output

    cost_input = (total_input / 1_000_000) * INPUT_PRICE_PER_MTOK
    cost_output = (total_output / 1_000_000) * OUTPUT_PRICE_PER_MTOK
    total_cost = cost_input + cost_output

    return {
        "total_input_tokens": int(total_input),
        "total_output_tokens": int(total_output),
        "cost_input_usd": round(cost_input, 4),
        "cost_output_usd": round(cost_output, 4),
        "total_cost_usd": round(total_cost, 4),
        "total_cost_eur": round(total_cost * 0.92, 4),  # Aproximación EUR
        "note": "Estimación aproximada. Precios Claude Sonnet 4.5: $3/MTok input, $15/MTok output.",
        "breakdown": {
            "ARQ": {"input": int(arq_input), "output": int(arq_output)},
            "QSP": {"input": int(qsp_input), "output": int(qsp_output)},
            "MAP": {"input": int(map_input), "output": int(map_output)},
            "Synthesis": {"input": int(synth_input), "output": int(synth_output)},
        }
    }


# ── Ejecución del pipeline en background ─────────────────────────────────

def run_pipeline_thread(seed_prompt: str, params: dict):
    """Ejecuta el pipeline PALET en un hilo separado."""
    global pipeline_state

    output_dir = str(RESULTS_DIR)
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    run_record = {
        "timestamp": timestamp,
        "started_at": datetime.now().isoformat(),
        "seed_prompt_preview": seed_prompt[:300],
        "params": params,
        "status": "running",
        "cost_actual": None,
        "result_paths": {},
        "error": None,
        "papers_count": 0,
        "rqs_count": 0,
    }

    try:
        # ── FASE 1: ARQ ──────────────────────────────────────────────
        pipeline_state["phase"] = "ARQ"
        pipeline_state["phase_index"] = 0
        pipeline_state["message"] = "Extrayendo Research Questions y keywords..."

        from arq_module import extract_keywords, save_arq_output

        arq_result = extract_keywords(seed_prompt, verbose=False)
        arq_filename = f"arq_output_{timestamp}.json"
        arq_path = save_arq_output(arq_result, filename=arq_filename)

        rqs = arq_result["research_questions"]
        keywords = arq_result["keywords"]

        pipeline_state["completed_phases"].append({
            "phase": "ARQ",
            "summary": f"{len(rqs)} Research Questions, {len(keywords)} keywords extraídos",
            "details": {
                "rqs": [{"index": i+1, "text": rq} for i, rq in enumerate(rqs)],
                "keywords": keywords,
                "inclusion_criteria": arq_result.get("inclusion_criteria", []),
                "exclusion_criteria": arq_result.get("exclusion_criteria", []),
            }
        })

        # Esperar aprobación si no es auto-accept
        if not pipeline_state["auto_accept"]:
            pipeline_state["waiting_approval"] = True
            pipeline_state["message"] = "ARQ completado. Esperando aprobación..."
            while pipeline_state["waiting_approval"]:
                time.sleep(0.5)
                if pipeline_state.get("rejected"):
                    raise Exception("Pipeline rechazado por el usuario en fase ARQ.")

        # ── FASE 2: QSP ──────────────────────────────────────────────
        pipeline_state["phase"] = "QSP"
        pipeline_state["phase_index"] = 1
        pipeline_state["message"] = "Generando queries de búsqueda..."

        from qsp_module import suggest_query_structure, save_qsp_output

        database = params.get("database", "openalex")
        suggestion = suggest_query_structure(arq_result["keywords"], database)
        query = suggestion["query"]
        qsp_path, _ = save_qsp_output(query, arq_result, arq_path, database, timestamp=timestamp)

        pipeline_state["completed_phases"].append({
            "phase": "QSP",
            "summary": f"Query generada para {database.upper()}",
            "details": {
                "query": query,
                "reasoning": suggestion.get("reasoning", ""),
                "alternatives": suggestion.get("alternative_queries", []),
                "database": database.upper(),
            }
        })

        if not pipeline_state["auto_accept"]:
            pipeline_state["waiting_approval"] = True
            pipeline_state["message"] = "QSP completado. Esperando aprobación..."
            while pipeline_state["waiting_approval"]:
                time.sleep(0.5)
                if pipeline_state.get("rejected"):
                    raise Exception("Pipeline rechazado por el usuario en fase QSP.")

        # ── FASE 3: SE ───────────────────────────────────────────────
        pipeline_state["phase"] = "SE"
        pipeline_state["phase_index"] = 2
        pipeline_state["message"] = f"Buscando papers en {database.upper()}..."

        from se_module import execute_se

        se_path, dedup_stats = execute_se(
            query=query,
            max_results=params.get("max_results", 100),
            min_year=params.get("min_year"),
            max_year=params.get("max_year"),
            doc_types=params.get("doc_types"),
            database=database,
            qsp_filepath=qsp_path,
            verbose=True
        )

        import pandas as pd
        df = pd.read_csv(se_path, encoding="utf-8")

        # Build rich SE summary
        se_details = {
            "total": len(df),
            "with_abstract": int(df["abstract"].notna().sum()),
            "without_abstract": int(df["abstract"].isna().sum()),
            "with_doi": int(df["doi"].notna().sum()),
        }

        # Year range
        if "year" in df.columns and df["year"].notna().any():
            se_details["year_min"] = int(df["year"].dropna().min())
            se_details["year_max"] = int(df["year"].dropna().max())

        # Distribution by source database
        if "source_db" in df.columns:
            db_counts = df["source_db"].value_counts().to_dict()
            se_details["by_database"] = {str(k): int(v) for k, v in db_counts.items()}

        # Top sources/journals
        source_col = None
        for col in ["source", "journal", "primary_location_source"]:
            if col in df.columns:
                source_col = col
                break
        if source_col and df[source_col].notna().any():
            top_sources = df[source_col].dropna().value_counts().head(5).to_dict()
            se_details["top_sources"] = {str(k): int(v) for k, v in top_sources.items()}

        # Dedup stats if available
        if dedup_stats:
            se_details["dedup_stats"] = dedup_stats

        pipeline_state["completed_phases"].append({
            "phase": "SE",
            "summary": f"{len(df)} papers recuperados ({df['abstract'].notna().sum()} con abstract)",
            "details": se_details,
        })
        run_record["papers_count"] = len(df)

        if not pipeline_state["auto_accept"]:
            pipeline_state["waiting_approval"] = True
            pipeline_state["message"] = "SE completado. Esperando aprobación..."
            while pipeline_state["waiting_approval"]:
                time.sleep(0.5)
                if pipeline_state.get("rejected"):
                    raise Exception("Pipeline rechazado por el usuario en fase SE.")

        # ── FASE 4: MAP ──────────────────────────────────────────────
        pipeline_state["phase"] = "MAP"
        pipeline_state["phase_index"] = 3
        pipeline_state["message"] = f"Analizando {len(df)} papers contra {len(rqs)} RQs..."

        from map_module_v2 import process_batch, generate_assignment_summary, save_map_output

        map_results = process_batch(df, rqs, batch_size=params.get("batch_size", 5))
        summary = generate_assignment_summary(map_results, rqs)
        map_results_path, map_summary_path = save_map_output(map_results, summary, se_path, arq_path)

        assigned_count = sum(len(v) for k, v in summary.items() if k.startswith("RQ"))
        
        # Build per-RQ breakdown with text
        rq_breakdown = []
        for i, rq in enumerate(rqs, 1):
            key = f"RQ{i}"
            count = len(summary.get(key, []))
            rq_breakdown.append({"key": key, "text": rq, "count": count})

        pipeline_state["completed_phases"].append({
            "phase": "MAP",
            "summary": f"{assigned_count} papers asignados a RQs, {len(summary.get('unmatched_not_relevant', []))} no relevantes, {len(summary.get('unmatched_no_abstract', []))} sin abstract",
            "details": {
                "rq_breakdown": rq_breakdown,
                "unmatched_not_relevant": len(summary.get("unmatched_not_relevant", [])),
                "unmatched_no_abstract": len(summary.get("unmatched_no_abstract", [])),
                "total_assigned": assigned_count,
            }
        })

        if not pipeline_state["auto_accept"]:
            pipeline_state["waiting_approval"] = True
            pipeline_state["message"] = "MAP completado. Esperando aprobación..."
            while pipeline_state["waiting_approval"]:
                time.sleep(0.5)
                if pipeline_state.get("rejected"):
                    raise Exception("Pipeline rechazado por el usuario en fase MAP.")

        # ── FASE 5: PRISMA ───────────────────────────────────────────
        pipeline_state["phase"] = "PRISMA"
        pipeline_state["phase_index"] = 4
        pipeline_state["message"] = "Generando validación PRISMA..."

        from prisma_validator import run_prisma_validation

        prisma_diagram_path, prisma_checklist = run_prisma_validation(
            arq_data=arq_result,
            dedup_stats=dedup_stats,
            papers_df=df,
            summary=summary,
            output_dir=output_dir
        )

        pipeline_state["completed_phases"].append({
            "phase": "PRISMA",
            "summary": "Diagrama PRISMA y checklist generados",
        })

        # ── FASE 6: SYNTHESIS ────────────────────────────────────────
        pipeline_state["phase"] = "Synthesis"
        pipeline_state["phase_index"] = 5
        pipeline_state["message"] = "Generando síntesis narrativa y detección de gaps..."

        from synthesis_module import run_synthesis

        syntheses, gaps, synthesis_path, gaps_path = run_synthesis(
            rqs=rqs,
            assignments=summary,
            papers_df=df,
            map_results=map_results,
            output_dir=os.path.join(os.path.dirname(__file__), "outputs", "json"),
            verbose=True
        )

        pipeline_state["completed_phases"].append({
            "phase": "Synthesis",
            "summary": f"Síntesis para {len(syntheses)} RQs, {len(gaps)} gaps detectados",
            "details": {
                "rqs_synthesized": len(syntheses),
                "gaps_detected": len(gaps),
                "gap_titles": [g.get("title", g.get("gap", str(g)))[:80] for g in gaps] if isinstance(gaps, list) else [],
            }
        })

        # ── FASE 7: REPORT ───────────────────────────────────────────
        pipeline_state["phase"] = "Report"
        pipeline_state["phase_index"] = 6
        pipeline_state["message"] = "Generando reporte PDF..."

        from report_generator_v2 import generate_latex_report, compile_pdf

        tex_path = os.path.join(output_dir, f"report_{timestamp}.tex")

        # Cargar map results detallados
        try:
            with open(map_results_path, "r", encoding="utf-8") as f:
                map_results_detailed = json.load(f)
        except Exception:
            map_results_detailed = []

        generate_latex_report(
            summary_data={
                "timestamp": timestamp,
                "assignments": summary,
                "source_arq": arq_path,
                "source_csv": se_path,
                "source_qsp": qsp_path,
            },
            arq_data=arq_result,
            papers_df=df,
            map_results=map_results_detailed,
            output_path=tex_path,
            seed_prompt=seed_prompt,
            prisma_checklist=prisma_checklist,
            prisma_diagram=True,
            syntheses=syntheses,
            gaps=gaps,
        )

        pdf_path = compile_pdf(tex_path)

        # BibTeX
        from export_bibtex import export_to_bibtex
        bibtex_path = os.path.join(output_dir, f"references_{timestamp}.bib")
        export_to_bibtex(se_path, bibtex_path)

        pipeline_state["completed_phases"].append({
            "phase": "Report",
            "summary": "PDF y BibTeX generados",
            "details": {"pdf_path": pdf_path, "bibtex_path": bibtex_path}
        })

        # ── COMPLETADO ───────────────────────────────────────────────
        pipeline_state["phase"] = "Completado"
        pipeline_state["message"] = "Pipeline completado exitosamente."
        pipeline_state["result"] = {
            "pdf_path": pdf_path,
            "bibtex_path": bibtex_path,
            "output_dir": output_dir,
            "timestamp": timestamp,
        }

        run_record["status"] = "completed"
        run_record["completed_at"] = datetime.now().isoformat()
        run_record["rqs_count"] = len(rqs)
        run_record["result_paths"] = {
            "pdf": pdf_path,
            "bibtex": bibtex_path,
            "arq": arq_path,
            "qsp": qsp_path,
            "se": se_path,
            "map_summary": map_summary_path,
        }

    except Exception as e:
        pipeline_state["error"] = str(e)
        pipeline_state["message"] = f"Error: {str(e)}"
        run_record["status"] = "error"
        run_record["error"] = str(e)
        import traceback
        traceback.print_exc()

    finally:
        pipeline_state["running"] = False
        run_record["finished_at"] = datetime.now().isoformat()
        add_run_to_history(run_record)


# ══════════════════════════════════════════════════════════════════════════
# ENDPOINTS
# ══════════════════════════════════════════════════════════════════════════

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.post("/api/estimate-cost")
async def api_estimate_cost(request: Request):
    body = await request.json()
    seed_prompt = body.get("seed_prompt", "")
    max_results = body.get("max_results", 100)
    estimate = estimate_cost(seed_prompt, max_results)
    return JSONResponse(estimate)


@app.post("/api/run")
async def api_run_pipeline(request: Request):
    global pipeline_state

    if pipeline_state["running"]:
        return JSONResponse({"error": "Ya hay un pipeline en ejecución."}, status_code=409)

    body = await request.json()
    seed_prompt = body.get("seed_prompt", "").strip()

    if not seed_prompt:
        return JSONResponse({"error": "El seed prompt no puede estar vacío."}, status_code=400)

    params = {
        "max_results": body.get("max_results", 100),
        "min_year": body.get("min_year"),
        "max_year": body.get("max_year"),
        "doc_types": body.get("doc_types", ["article", "review"]),
        "database": body.get("database", "openalex"),
        "batch_size": body.get("batch_size", 5),
    }

    # Reset state
    pipeline_state = {
        "running": True,
        "phase": None,
        "phase_index": 0,
        "total_phases": 7,
        "message": "Iniciando pipeline...",
        "completed_phases": [],
        "error": None,
        "result": None,
        "auto_accept": body.get("auto_accept", True),
        "waiting_approval": False,
        "seed_prompt_text": seed_prompt,
        "params": params,
    }

    # Guardar seed prompt en fichero temporal
    temp_seed_path = str(BASE_DIR / "prompts" / f"_gui_seed_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt")
    with open(temp_seed_path, "w", encoding="utf-8") as f:
        f.write(seed_prompt)

    # Lanzar pipeline en thread
    thread = threading.Thread(
        target=run_pipeline_thread,
        args=(seed_prompt, params),
        daemon=True
    )
    thread.start()

    return JSONResponse({"status": "started", "message": "Pipeline iniciado."})


@app.get("/api/status")
async def api_status():
    return JSONResponse(pipeline_state)


@app.post("/api/approve")
async def api_approve():
    global pipeline_state
    pipeline_state["waiting_approval"] = False
    pipeline_state["rejected"] = False
    return JSONResponse({"status": "approved"})


@app.post("/api/reject")
async def api_reject():
    global pipeline_state
    pipeline_state["waiting_approval"] = False
    pipeline_state["rejected"] = True
    return JSONResponse({"status": "rejected"})


@app.get("/api/history")
async def api_history():
    return JSONResponse(load_history())


@app.get("/api/prompts")
async def api_list_prompts():
    """Lista los seed prompts disponibles en prompts/."""
    seeds = []
    for f in sorted(PROMPTS_DIR.glob("seed_*.txt")):
        content = f.read_text(encoding="utf-8")
        seeds.append({
            "filename": f.name,
            "preview": content[:200],
            "chars": len(content),
        })
    return JSONResponse(seeds)


@app.get("/api/download/{filename:path}")
async def api_download(filename: str):
    filepath = Path(filename)
    if not filepath.exists():
        # Intentar en results/
        filepath = RESULTS_DIR / filename
    if filepath.exists():
        return FileResponse(str(filepath), filename=filepath.name)
    return JSONResponse({"error": "Archivo no encontrado."}, status_code=404)
