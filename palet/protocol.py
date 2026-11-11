"""Review protocol: research questions and eligibility criteria fixed by humans.

The protocol is a YAML file written and approved by the authors. PALET reads
it, validates it and never rewrites research questions or criteria.
"""

import re
from datetime import date, datetime
from pathlib import Path
from typing import Literal, Optional, Union

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from palet.errors import PaletConfigError

Dimension = Literal["population", "concept", "context", "study_type", "language", "period"]


class Criterion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: Literal["include", "exclude"]
    dimension: Dimension
    rule: str = Field(min_length=10)
    reason_code: Optional[str] = None      # code recorded when a record fails this criterion
    examples_in: list[str] = Field(default_factory=list)
    examples_out: list[str] = Field(default_factory=list)


class Source(BaseModel):
    """Where records come from. Extra keys (query strings, dates…) are kept."""

    model_config = ConfigDict(extra="allow")

    id: str
    type: Literal["scopus", "openalex", "pubmed", "wos", "manual_import"]
    applies_to_rqs: list[str] = Field(default_factory=list)


class Protocol(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int
    status: Literal["draft", "approved"] = "draft"
    title: str
    approved_by: Optional[Union[str, list[str]]] = None
    approved_at: Optional[Union[date, datetime]] = None
    research_questions: dict[str, str]
    research_questions_original: dict[str, str] = Field(default_factory=dict)
    assignment_mode: Literal["single", "multi"] = "multi"
    criteria: list[Criterion]
    year_from: Optional[int] = None
    year_to: Optional[int] = None
    languages: list[str] = Field(default_factory=lambda: ["en"])
    document_types: list[str] = Field(default_factory=lambda: ["article", "review"])
    sources: list[Source] = Field(default_factory=list)
    known_items: list[str] = Field(default_factory=list)

    @field_validator("research_questions")
    @classmethod
    def _check_rqs(cls, rqs):
        if not rqs:
            raise ValueError("at least one research question is required")
        for key, text in rqs.items():
            if not re.fullmatch(r"RQ\d+", key):
                raise ValueError(f"research question keys must look like RQ1, RQ2… (got '{key}')")
            if not text or not text.strip():
                raise ValueError(f"{key} is empty")
        return rqs

    @model_validator(mode="after")
    def _check_consistency(self):
        ids = [criterion.id for criterion in self.criteria]
        duplicated = sorted({i for i in ids if ids.count(i) > 1})
        if duplicated:
            raise ValueError(f"duplicated criterion ids: {duplicated}")
        if not any(c.kind == "include" for c in self.criteria):
            raise ValueError("at least one inclusion criterion is required")
        if self.year_from and self.year_to and self.year_from > self.year_to:
            raise ValueError("year_from is later than year_to")
        unknown = sorted(set(self.research_questions_original) - set(self.research_questions))
        if unknown:
            raise ValueError(f"research_questions_original refers to unknown questions: {unknown}")
        if self.status == "approved" and not (self.approved_by and self.approved_at):
            raise ValueError("an approved protocol needs approved_by and approved_at")
        return self

    @property
    def inclusion_criteria(self) -> list[Criterion]:
        return [c for c in self.criteria if c.kind == "include"]

    @property
    def exclusion_criteria(self) -> list[Criterion]:
        return [c for c in self.criteria if c.kind == "exclude"]

    def source(self, source_id: str) -> Source:
        for source in self.sources:
            if source.id == source_id:
                return source
        raise PaletConfigError(f"No source '{source_id}' in the protocol")


def load_protocol(path) -> Protocol:
    """Read and validate a protocol file."""
    path = Path(path)
    if not path.is_file():
        raise PaletConfigError(f"Protocol file not found: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise PaletConfigError(f"Protocol is not valid YAML: {path} ({e})") from e
    if not isinstance(data, dict):
        raise PaletConfigError(f"Protocol must be a YAML mapping: {path}")
    try:
        return Protocol.model_validate(data)
    except ValidationError as e:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in err['loc']) or 'protocol'}: {err['msg']}" for err in e.errors()
        )
        raise PaletConfigError(f"Invalid protocol {path.name}: {problems}") from e


def require_approved(protocol: Protocol) -> None:
    """Screening may only run against a protocol approved by humans."""
    if protocol.status != "approved":
        raise PaletConfigError(
            "The protocol is still a draft. Set status: approved, approved_by and "
            "approved_at in the protocol file once the authors have approved it."
        )
