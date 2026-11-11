"""Run directories and manifests.

Every execution of PALET 2.0 writes all its artefacts under
``runs/<run_id>/`` together with a ``manifest.json`` that records what is
needed to reproduce it: code version, models, settings, protocol and prompt
hashes, searches, steps and model usage.
"""

import hashlib
import json
import platform
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Type, TypeVar

from pydantic import BaseModel

import palet
from palet import config, llm
from palet.errors import PaletError

ROOT = Path(__file__).resolve().parent.parent
RUNS_DIR = ROOT / "runs"

ModelT = TypeVar("ModelT", bound=BaseModel)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256_file(path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _git(*args) -> str | None:
    try:
        result = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout.strip() if result.returncode == 0 else None


class Run:
    """One run directory with its manifest."""

    def __init__(self, path):
        self.path = Path(path)
        self.manifest_path = self.path / "manifest.json"

    # ── creation ────────────────────────────────────────────────────────────
    @classmethod
    def create(cls, label: str, base_dir=None, run_id: str | None = None) -> "Run":
        base_dir = Path(base_dir) if base_dir else RUNS_DIR
        slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-") or "run"
        run_id = run_id or f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{slug}"
        path = base_dir / run_id
        if path.exists():
            raise PaletError(f"Run directory already exists: {path}")
        path.mkdir(parents=True)

        run = cls(path)
        status = _git("status", "--porcelain")
        settings = config.load_config()
        run._save({
            "run_id": run_id,
            "label": label,
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "palet_version": palet.__version__,
            "git_commit": _git("rev-parse", "HEAD"),
            "git_dirty": bool(status) if status is not None else None,
            "python": platform.python_version(),
            "settings": {
                "models": dict(settings["models"]),
                "model_options": dict(settings.get("model_options", {})),
                "limits": dict(settings["limits"]),
                "search": dict(settings["search"]),
            },
            "protocol": None,
            "prompts": {},
            "searches": [],
            "steps": [],
            "llm_usage": {},
        })
        return run

    @classmethod
    def open(cls, path) -> "Run":
        run = cls(path)
        if not run.manifest_path.is_file():
            raise PaletError(f"Not a PALET run directory (no manifest.json): {path}")
        return run

    # ── manifest ────────────────────────────────────────────────────────────
    @property
    def manifest(self) -> dict:
        return json.loads(self.manifest_path.read_text(encoding="utf-8"))

    def _save(self, manifest: dict) -> None:
        manifest["updated_at"] = utc_now()
        self.manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
        )

    def update(self, **fields) -> None:
        manifest = self.manifest
        manifest.update(fields)
        self._save(manifest)

    def record_protocol(self, protocol_path, protocol) -> None:
        self.update(protocol={
            "path": str(protocol_path),
            "sha256": sha256_file(protocol_path),
            "version": protocol.version,
            "status": protocol.status,
            "approved_by": protocol.approved_by,
            "approved_at": str(protocol.approved_at) if protocol.approved_at else None,
        })

    def record_prompt(self, name: str, text: str) -> None:
        manifest = self.manifest
        manifest["prompts"][name] = sha256_text(text)
        self._save(manifest)

    def record_search(self, search: dict) -> None:
        manifest = self.manifest
        manifest["searches"].append(search)
        self._save(manifest)

    def log_step(self, step: str, **info) -> None:
        """Append a step with its counts and store the model usage so far."""
        manifest = self.manifest
        manifest["steps"].append({"step": step, "at": utc_now(), **info})
        self._save(manifest)

    def record_llm_usage(self, step: str) -> None:
        """Store calls, tokens and cost of ``step`` (the ledger since the last reset)."""
        manifest = self.manifest
        manifest["llm_usage"][step] = llm.usage_summary()
        self._save(manifest)

    # ── artefacts ───────────────────────────────────────────────────────────
    def file(self, name: str) -> Path:
        path = self.path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def write_models(self, name: str, items: Iterable[BaseModel]) -> Path:
        """Write pydantic objects as JSON Lines (one per line, stable key order)."""
        path = self.file(name)
        with open(path, "w", encoding="utf-8") as f:
            for item in items:
                f.write(json.dumps(item.model_dump(mode="json"), ensure_ascii=False, sort_keys=True) + "\n")
        return path

    def read_models(self, name: str, model_cls: Type[ModelT]) -> list[ModelT]:
        path = self.path / name
        if not path.is_file():
            raise PaletError(f"Missing artefact in run {self.path.name}: {name}")
        with open(path, encoding="utf-8") as f:
            return [model_cls.model_validate_json(line) for line in f if line.strip()]

    def write_json(self, name: str, data) -> Path:
        path = self.file(name)
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return path
