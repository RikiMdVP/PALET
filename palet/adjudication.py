"""Human adjudication of the records the screeners did not settle (WP5).

Pending records are exported to an Excel workbook with everything a person
needs to decide (title, abstract, each screener's judgements and quotes).
The filled workbook is read back and the human decisions become final.
"""

from datetime import datetime, timezone
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

from palet.errors import PaletError
from palet.models import Record
from palet.screening import NO_ABSTRACT, REASON_PRECEDENCE, FinalDecision, ScreeningDecision

HUMAN_COLUMNS = ["human_decision", "human_reason_code", "human_notes"]
COLUMNS = ["record_id", "title", "year", "source", "abstract", "pending_reason",
           "screener_A", "detail_A", "screener_B", "detail_B", *HUMAN_COLUMNS]
WIDTHS = {"record_id": 24, "title": 45, "year": 7, "source": 24, "abstract": 90, "pending_reason": 24,
          "screener_A": 20, "detail_A": 60, "screener_B": 20, "detail_B": 60,
          "human_decision": 16, "human_reason_code": 22, "human_notes": 40}
DECISION_CHOICES = ["include", "exclude"]
REASON_CHOICES = [*REASON_PRECEDENCE, NO_ABSTRACT, "OTHER"]


def _detail(decision: ScreeningDecision | None) -> str:
    if decision is None:
        return ""
    lines = [decision.notes] if decision.notes else []
    for j in decision.judgements:
        quote = f' — "{j.evidence_quote}"' if j.evidence_quote else ""
        flag = "" if (j.quote_verified or not j.evidence_quote) else " [QUOTE NOT FOUND IN RECORD]"
        lines.append(f"{j.criterion_id}: {j.met}{quote}{flag} ({j.rationale})")
    return "\n".join(lines)


def export_pending(path, records: list[Record], decisions: list[ScreeningDecision],
                   finals: list[FinalDecision]) -> int:
    """Write the workbook for the pending records. Returns how many there are."""
    by_id = {record.record_id: record for record in records}
    per_record: dict[str, list[ScreeningDecision]] = {}
    for decision in decisions:
        per_record.setdefault(decision.record_id, []).append(decision)

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "adjudication"
    sheet.append(COLUMNS)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
        cell.fill = PatternFill("solid", fgColor="DDDDDD")
    human_fill = PatternFill("solid", fgColor="FFF2CC")

    pending = [final for final in finals if final.decision == "pending"]
    for final in pending:
        record = by_id[final.record_id]
        models = [d for d in per_record.get(final.record_id, []) if d.screener != "metadata"]
        a = models[0] if len(models) > 0 else None
        b = models[1] if len(models) > 1 else None
        label = lambda d: f"{d.decision}" + (f" ({d.reason_code})" if d.reason_code else "") if d else ""  # noqa: E731
        sheet.append([
            record.record_id, record.title, record.year, record.source_title,
            record.abstract or "(no abstract)",
            final.pending_reason or final.reason_code or "",
            label(a), _detail(a), label(b), _detail(b), "", "", "",
        ])

    for index, column in enumerate(COLUMNS, start=1):
        letter = sheet.cell(row=1, column=index).column_letter
        sheet.column_dimensions[letter].width = WIDTHS[column]
        for row in range(2, sheet.max_row + 1):
            cell = sheet.cell(row=row, column=index)
            cell.alignment = Alignment(wrap_text=True, vertical="top")
            if column in HUMAN_COLUMNS:
                cell.fill = human_fill
    sheet.freeze_panes = "C2"

    if pending:
        last = sheet.max_row
        decision_col = sheet.cell(row=1, column=COLUMNS.index("human_decision") + 1).column_letter
        reason_col = sheet.cell(row=1, column=COLUMNS.index("human_reason_code") + 1).column_letter
        for column, choices in ((decision_col, DECISION_CHOICES), (reason_col, REASON_CHOICES)):
            validation = DataValidation(type="list", formula1='"' + ",".join(choices) + '"', allow_blank=True)
            sheet.add_data_validation(validation)
            validation.add(f"{column}2:{column}{last}")

    guide = workbook.create_sheet("instructions")
    for line in [
        "Fill the three yellow columns for every row. Do not change the other columns.",
        "human_decision: include or exclude, applying the eligibility criteria of the protocol.",
        "human_reason_code: required when you exclude. " + ", ".join(REASON_CHOICES),
        "human_notes: optional.",
        "Rows left blank stay pending.",
        "detail_A / detail_B show each screener's judgement per criterion and the passage it quoted.",
    ]:
        guide.append([line])
    guide.column_dimensions["A"].width = 120

    workbook.save(path)
    return len(pending)


def import_decisions(path, finals: list[FinalDecision], initials: str) -> tuple[list[FinalDecision], list[ScreeningDecision], dict]:
    """Apply a filled workbook. Returns (updated finals, human decisions, report)."""
    path = Path(path)
    if not path.is_file():
        raise PaletError(f"Adjudication workbook not found: {path}")
    initials = initials.strip().upper()
    if not initials:
        raise PaletError("Initials of the person who adjudicated are required")

    sheet = load_workbook(path, data_only=True)["adjudication"]
    header = [cell.value for cell in sheet[1]]
    missing = [c for c in ("record_id", *HUMAN_COLUMNS) if c not in header]
    if missing:
        raise PaletError(f"Not an adjudication workbook: missing columns {missing}")
    col = {name: header.index(name) for name in header if name}

    by_id = {final.record_id: final for final in finals}
    human, problems, blank = [], [], 0
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    for number, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
        record_id = row[col["record_id"]]
        if not record_id:
            continue
        record_id = str(record_id).strip()
        decision = (str(row[col["human_decision"]] or "")).strip().lower()
        reason = (str(row[col["human_reason_code"]] or "")).strip().upper() or None
        notes = str(row[col["human_notes"]] or "").strip()

        if record_id not in by_id:
            problems.append(f"row {number}: unknown record_id {record_id}")
            continue
        if not decision:
            blank += 1
            continue
        if decision not in DECISION_CHOICES:
            problems.append(f"row {number}: human_decision must be include or exclude, not '{decision}'")
            continue
        if decision == "exclude" and reason not in REASON_CHOICES:
            problems.append(f"row {number}: an exclusion needs a valid human_reason_code")
            continue
        if by_id[record_id].decision != "pending" and not by_id[record_id].decided_by.startswith("human:"):
            problems.append(f"row {number}: record {record_id} was not pending")
            continue

        human.append(ScreeningDecision(record_id=record_id, screener=f"human:{initials}", decision=decision,
                                       reason_code=reason if decision == "exclude" else None,
                                       notes=notes, decided_at=now))

    if problems:
        raise PaletError("The workbook has problems; nothing was imported:\n  " + "\n  ".join(problems))

    for decision in human:
        previous = by_id[decision.record_id]
        by_id[decision.record_id] = previous.model_copy(update={
            "decision": decision.decision, "reason_code": decision.reason_code,
            "decided_by": decision.screener, "pending_reason": None,
            "screener_decisions": {**previous.screener_decisions, decision.screener: decision.decision},
        })

    updated = [by_id[final.record_id] for final in finals]
    report = {"adjudicated": len(human), "left_blank": blank,
              "still_pending": sum(f.decision == "pending" for f in updated)}
    return updated, human, report
