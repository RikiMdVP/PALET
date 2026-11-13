"""Journal lists as an eligibility filter (e.g. journals indexed in SCIE or SSCI).

A record passes when one of its ISSNs is in a list of the protocol or, failing
that, when the title of its journal is. Matching is done in code, before any
model call. The lists are spreadsheets with the columns ``Journal title``,
``ISSN`` and ``eISSN`` (the format of the Web of Science master journal list).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from palet.errors import PaletConfigError
from palet.models import Record, strip_accents

_ISSN = re.compile(r"^\d{7}[\dX]$")
_NOT_ALNUM = re.compile(r"[^a-z0-9]+")


def normalize_issn(value) -> str | None:
    """'1234-567x' -> '1234567X'; None when it is not an ISSN."""
    text = re.sub(r"[^0-9Xx]", "", str(value or "")).upper()
    return text if _ISSN.match(text) else None


def split_issns(value) -> list[str]:
    """Every ISSN found in a cell such as '00343404; 1360-0591'."""
    found = []
    for part in re.split(r"[;,|\s]+", str(value or "")):
        issn = normalize_issn(part)
        if issn and issn not in found:
            found.append(issn)
    return found


def normalize_journal_title(title) -> str:
    text = strip_accents(str(title or "")).lower().replace("&", " and ")
    text = _NOT_ALNUM.sub(" ", text).strip()
    return text[4:] if text.startswith("the ") else text


@dataclass
class JournalIndex:
    issns: set = field(default_factory=set)
    titles: set = field(default_factory=set)
    files: list = field(default_factory=list)       # [{"id", "file", "journals"}]

    def check(self, record: Record) -> tuple[bool, str]:
        """(in a list?, how it was established)."""
        issns = [i for i in (normalize_issn(x) for x in record.issn) if i]
        if any(issn in self.issns for issn in issns):
            return True, "issn"
        title = normalize_journal_title(record.source_title)
        if title and title in self.titles:
            return True, "title"
        if issns:
            return False, "issn not in the lists"
        if title:
            return False, "journal title not in the lists (record has no ISSN)"
        return False, "record has no journal data"


def load_journal_lists(lists: list[dict], root: Path) -> JournalIndex:
    """Read the spreadsheets named in the protocol (``[{"id": ..., "file": ...}]``)."""
    import openpyxl

    index = JournalIndex()
    for entry in lists:
        path = Path(entry["file"])
        path = path if path.is_absolute() else root / path
        if not path.is_file():
            raise PaletConfigError(f"Journal list not found: {path}")
        workbook = openpyxl.load_workbook(path, read_only=True)
        rows = workbook.active.iter_rows(values_only=True)
        header = [str(cell or "").strip().lower() for cell in next(rows, [])]
        missing = [name for name in ("journal title", "issn", "eissn") if name not in header]
        if missing:
            raise PaletConfigError(f"Journal list {path.name}: missing columns {missing}")
        col = {name: header.index(name) for name in ("journal title", "issn", "eissn")}
        journals = 0
        for row in rows:
            title = normalize_journal_title(row[col["journal title"]])
            if not title:
                continue
            journals += 1
            index.titles.add(title)
            for name in ("issn", "eissn"):
                issn = normalize_issn(row[col[name]])
                if issn:
                    index.issns.add(issn)
        workbook.close()
        index.files.append({"id": entry["id"], "file": str(entry["file"]), "journals": journals})
    return index


_cache: dict = {}


def index_for(protocol, root: Path) -> JournalIndex | None:
    """Index of the journal lists of a protocol (None when it has none). Read once per process."""
    lists = [{"id": j.id, "file": j.file} for j in protocol.journal_lists]
    if not lists:
        return None
    key = (str(root), tuple((j["id"], j["file"]) for j in lists))
    if key not in _cache:
        _cache[key] = load_journal_lists(lists, root)
    return _cache[key]
