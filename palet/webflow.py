"""Dashboard API for the PALET 2.0 review workflow (runs, screening, charting, report).

The dashboard does not reimplement any step. Each action runs the same
command a person would type (``python -m palet <step> ...``) in a separate
process and shows its output, so the dashboard and the CLI cannot diverge.

Rules enforced here, not only in the page:
- one job at a time;
- a step that spends money (screen, assign) starts only after its cost
  estimate has been requested for exactly the same options, and only with an
  explicit confirmation;
- run ids, model ids and initials are validated before they reach a command.

Searches and protocol approvals stay in the CLI on purpose: they are
decisions of the authors about the method.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from palet import config
from palet.errors import PaletConfigError
from palet.runs import ROOT

router = APIRouter(prefix="/api/v2")

RUNS_DIR = ROOT / "runs"
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
MAX_LOG_LINES = 2000
PAID_STEPS = {"screen", "assign"}
STEPS = {"dedup", "screen", "assign", "report"}

_RUN_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,80}$")
_INITIALS = re.compile(r"^[A-Za-z]{2,6}$")

_lock = threading.Lock()
_job = {"running": False, "run_id": None, "step": None, "started_at": None, "finished_at": None,
        "returncode": None, "log": []}
_estimates: set = set()          # (run_id, step, options) whose estimate has been shown in this session

# Set by app.py: tells whether the old pipeline is running (both would share the API key and the cache).
other_job_running = lambda: False  # noqa: E731


class WorkflowError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


# ── Reading runs ────────────────────────────────────────────────────────────

def run_path(run_id: str) -> Path:
    if not isinstance(run_id, str) or not _RUN_ID.match(run_id) or run_id.startswith("."):
        raise WorkflowError("Identificador de ejecución no válido.")
    path = RUNS_DIR / run_id
    if not (path / "manifest.json").is_file():
        raise WorkflowError(f"No existe la ejecución '{run_id}'.", status=404)
    return path


def _read_json(path: Path, default=None):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _count_lines(path: Path) -> int | None:
    if not path.is_file():
        return None
    with open(path, encoding="utf-8") as f:
        return sum(1 for line in f if line.strip())


def _finals_summary(path: Path) -> dict | None:
    if not path.is_file():
        return None
    counts = {"include": 0, "exclude": 0, "pending": 0}
    reasons: dict = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            item = json.loads(line)
            counts[item["decision"]] = counts.get(item["decision"], 0) + 1
            if item["decision"] == "exclude":
                reasons[item.get("reason_code") or "?"] = reasons.get(item.get("reason_code") or "?", 0) + 1
    return {"records": sum(counts.values()), **counts, "exclusion_reasons": dict(sorted(reasons.items()))}


def list_runs() -> list[dict]:
    runs = []
    if RUNS_DIR.is_dir():
        for path in sorted(RUNS_DIR.iterdir()):
            manifest = _read_json(path / "manifest.json")
            if not manifest or not _RUN_ID.match(path.name):
                continue
            runs.append({"run_id": path.name, "label": manifest.get("label"),
                         "created_at": manifest.get("created_at"), "updated_at": manifest.get("updated_at")})
    return sorted(runs, key=lambda r: r["updated_at"] or "", reverse=True)


def run_overview(run_id: str) -> dict:
    path = run_path(run_id)
    manifest = _read_json(path / "manifest.json", {})
    steps = manifest.get("steps", [])
    screen_steps = [s for s in steps if s.get("step") == "screen"]
    last_screen = screen_steps[-1] if screen_steps else None
    records = _count_lines(path / "records.jsonl")
    screening = _finals_summary(path / "final_decisions.jsonl")
    stats = _read_json(path / "screening_stats.json", {}) or {}
    assignments = _count_lines(path / "assignments.jsonl")
    report_dir = path / "report"
    report_files = sorted(p.name for p in report_dir.iterdir() if p.is_file()) if report_dir.is_dir() else []
    protocol = manifest.get("protocol") or {}
    spent = sum(phase.get("cost_usd", 0) for step in (manifest.get("llm_usage") or {}).values()
                for phase in step.values())

    # What the person should do next, in plain words.
    screened = screening["records"] if screening else 0
    if records is None:
        hint = "Falta deduplicar las fuentes (paso 1)."
    elif not screening or screened < records or (last_screen or {}).get("limit"):
        hint = f"Falta el cribado completo: {screened} de {records} registros tienen decisión (paso 2)."
    elif screening["pending"]:
        hint = (f"Quedan {screening['pending']} registros pendientes de vuestra decisión: descarga el Excel, "
                "rellénalo y súbelo (paso 3).")
    elif assignments is None or assignments < screening["include"]:
        hint = "Falta asignar los estudios incluidos a las preguntas de investigación (paso 4)."
    elif "prisma_flow.pdf" not in report_files:
        hint = "Falta generar el informe (paso 5)."
    else:
        hint = "Todos los pasos están hechos. Si cambias algo, vuelve a generar el informe."

    return {
        "run_id": run_id,
        "label": manifest.get("label"),
        "created_at": manifest.get("created_at"),
        "updated_at": manifest.get("updated_at"),
        "protocol": {"version": protocol.get("version"), "status": protocol.get("status"),
                     "approved_by": protocol.get("approved_by"), "file": Path(protocol.get("path") or "").name},
        "searches": [{"query_id": s.get("query_id"), "total_hits": s.get("total_hits"),
                      "downloaded": s.get("downloaded"), "truncated": bool(s.get("truncated")),
                      "executed_at": s.get("executed_at")} for s in manifest.get("searches", [])],
        "records": records,
        "duplicates_removed": _count_lines(path / "duplicates.jsonl"),
        "screening": screening,
        "last_screen": ({"screeners": last_screen.get("screeners", []), "limit": last_screen.get("limit"),
                         "at": last_screen.get("at")} if last_screen else None),
        "agreement": stats.get("agreement"),
        "assignments": assignments,
        "has_adjudication_file": (path / "adjudication.xlsx").is_file(),
        "report_files": report_files,
        "spent_usd": round(spent, 2),
        "steps": [{"step": s.get("step"), "at": s.get("at")} for s in steps[-12:]],
        "hint": hint,
    }


# ── Commands ────────────────────────────────────────────────────────────────

def _options_key(step: str, options: dict) -> tuple:
    return (step, tuple(options.get("screeners") or ()), options.get("limit") or 0)


def clean_options(step: str, body: dict) -> dict:
    """Validated options of a step. Raises WorkflowError on anything unexpected."""
    if step not in STEPS:
        raise WorkflowError(f"Paso desconocido: {step}")
    options: dict = {}
    if step == "screen":
        models = body.get("screeners")
        if models is not None:
            if not isinstance(models, list) or not all(isinstance(m, str) for m in models):
                raise WorkflowError("La lista de cribadores no es válida.")
            try:
                options["screeners"] = [s["model"] for s in config.make_screeners(models)]
            except PaletConfigError as e:
                raise WorkflowError(str(e))
        limit = body.get("limit")
        if limit not in (None, "", 0):
            if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100000:
                raise WorkflowError("El límite de registros debe ser un número entero positivo.")
            options["limit"] = limit
    if step == "report":
        year = body.get("partial_year")
        if year not in (None, ""):
            if not isinstance(year, int) or isinstance(year, bool) or not 1900 <= year <= 2100:
                raise WorkflowError("El año parcial no es válido.")
            options["partial_year"] = year
    if step in PAID_STEPS:
        options["replay"] = bool(body.get("replay"))
    return options


def build_command(step: str, run_id: str, options: dict, estimate: bool = False) -> list[str]:
    command = [sys.executable, "-m", "palet", step, "--run", run_id]
    if options.get("screeners"):
        command += ["--screeners", ",".join(options["screeners"])]
    if options.get("limit"):
        command += ["--limit", str(options["limit"])]
    if options.get("partial_year"):
        command += ["--partial-year", str(options["partial_year"])]
    if estimate:
        command.append("--estimate")
    elif options.get("replay"):
        command.append("--replay")
    return command


def _child_env() -> dict:
    """Environment of the commands: unbuffered UTF-8 output, so progress lines arrive as they are printed."""
    return {**os.environ, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8"}


def _run_and_capture(command: list[str], timeout: int = 180) -> tuple[int, str]:
    """Run a short command and return (exit code, output)."""
    done = subprocess.run(command, cwd=str(ROOT), capture_output=True, text=True, timeout=timeout,
                          encoding="utf-8", errors="replace", env=_child_env())
    return done.returncode, (done.stdout + done.stderr).strip()


def _stream(command: list[str], on_line) -> int:
    """Run a long command, passing each output line to ``on_line``. Returns the exit code."""
    process = subprocess.Popen(command, cwd=str(ROOT), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, encoding="utf-8", errors="replace", bufsize=1, env=_child_env())
    for line in process.stdout:
        on_line(line.rstrip("\n"))
    return process.wait()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def start_job(run_id: str, step: str, command: list[str]) -> None:
    with _lock:
        if _job["running"]:
            raise WorkflowError("Ya hay un paso en ejecución. Espera a que termine.", status=409)
        if other_job_running():
            raise WorkflowError("El pipeline antiguo está en ejecución. Espera a que termine.", status=409)
        _job.update(running=True, run_id=run_id, step=step, started_at=_now(), finished_at=None,
                    returncode=None, log=[])

    def log(line: str) -> None:
        with _lock:
            _job["log"].append(line)
            del _job["log"][:-MAX_LOG_LINES]

    def work() -> None:
        code = 1
        try:
            code = _stream(command, log)
        except Exception as e:                      # the job must always end in a known state
            log(f"ERROR: {type(e).__name__}: {e}")
        finally:
            with _lock:
                _job.update(running=False, returncode=code, finished_at=_now())

    threading.Thread(target=work, daemon=True).start()


def job_state() -> dict:
    with _lock:
        return {**_job, "log": list(_job["log"])}


# ── Endpoints ───────────────────────────────────────────────────────────────

def _error(e: WorkflowError) -> JSONResponse:
    return JSONResponse({"error": str(e)}, status_code=e.status)


@router.get("/runs")
async def api_runs():
    return JSONResponse(list_runs())


@router.get("/screeners")
async def api_screeners():
    """Catalogue of models and the screeners configured in palet.toml."""
    try:
        default = [s["model"] for s in config.get_screening_settings()["screeners"]]
    except PaletConfigError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    return JSONResponse({"default": default, "models": config.list_models()})


@router.get("/runs/{run_id}")
async def api_run(run_id: str):
    try:
        return JSONResponse(run_overview(run_id))
    except WorkflowError as e:
        return _error(e)


@router.post("/runs/{run_id}/estimate")
async def api_estimate(run_id: str, request: Request):
    body = await request.json()
    step = body.get("step")
    try:
        run_path(run_id)
        if step not in PAID_STEPS:
            raise WorkflowError("Solo el cribado y la asignación tienen estimación de coste.")
        options = clean_options(step, body)
        code, output = _run_and_capture(build_command(step, run_id, options, estimate=True))
    except WorkflowError as e:
        return _error(e)
    except subprocess.TimeoutExpired:
        return JSONResponse({"error": "La estimación tardó demasiado."}, status_code=504)
    if code != 0:
        return JSONResponse({"error": output or "La estimación falló."}, status_code=400)
    _estimates.add((run_id, *_options_key(step, options)))
    return JSONResponse({"output": output})


@router.post("/runs/{run_id}/run")
async def api_run_step(run_id: str, request: Request):
    body = await request.json()
    step = body.get("step")
    try:
        run_path(run_id)
        options = clean_options(step, body)
        if step in PAID_STEPS and not options.get("replay"):
            if (run_id, *_options_key(step, options)) not in _estimates:
                raise WorkflowError("Antes de lanzar este paso hay que pedir su estimación de coste "
                                    "con las mismas opciones.")
            if body.get("confirm_cost") is not True:
                raise WorkflowError("Falta confirmar que has visto la estimación y autorizas el gasto.")
        start_job(run_id, step, build_command(step, run_id, options))
    except WorkflowError as e:
        return _error(e)
    return JSONResponse({"status": "started", "step": step})


@router.post("/runs/{run_id}/adjudicate")
async def api_adjudicate(run_id: str, request: Request, initials: str = ""):
    """Upload the filled-in adjudication workbook (raw .xlsx body) and import it."""
    try:
        path = run_path(run_id)
        if not _INITIALS.match(initials or ""):
            raise WorkflowError("Indica tus iniciales (de 2 a 6 letras).")
        content = await request.body()
        if len(content) > MAX_UPLOAD_BYTES:
            raise WorkflowError("El fichero es demasiado grande.", status=413)
        if not content.startswith(b"PK"):
            raise WorkflowError("El fichero no es un libro de Excel (.xlsx).")
        uploads = path / "uploads"
        uploads.mkdir(exist_ok=True)
        target = uploads / f"adjudication_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{initials.upper()}.xlsx"
        with _lock:
            if _job["running"]:
                raise WorkflowError("Ya hay un paso en ejecución. Espera a que termine.", status=409)
        target.write_bytes(content)
        command = [sys.executable, "-m", "palet", "adjudicate", "--run", run_id,
                   "--file", str(target), "--initials", initials.upper()]
        start_job(run_id, "adjudicate", command)
    except WorkflowError as e:
        return _error(e)
    return JSONResponse({"status": "started", "step": "adjudicate", "saved_as": target.name})


@router.get("/job")
async def api_job():
    return JSONResponse(job_state())
