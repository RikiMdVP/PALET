# Changelog

All notable changes to PALET are recorded here, one entry per work package
of the PALET 2.0 refactor (see `docs/PALET_auditoria_plan_mejora.tex`).

## Protocol assistant — 2026-11-15

### Added
- A review can start from a context and research questions again (`+ nueva revisión` in the dashboard, or `python -m palet draft-protocol`). The assistant model (a) reviews the wording of each question and suggests a sharper one with its reasons, and (b) once the authors have fixed the questions, drafts eligibility criteria and one search per question. The result is a protocol file with `status: draft`; nothing is screened until the authors approve it (`approve-protocol`, or the protocol panel of the dashboard). Original wordings are kept in `research_questions_original`.
- Searches and the protocol can be approved from the dashboard (who approves is recorded; searches need a second press).
- PALET the robot redrawn at 24x24 with more detail; it takes a notepad and a pencil while the assistant writes.

### Fixed
- The PRISMA counts dropped exclusion reasons whose code was defined by the protocol and not known to PALET.

## Dashboard 2.0 and selection for the synthesis — 2026-11-14

### Added
- `/workflow` redesigned as a terminal with buttons: a diagram of the eight steps of a review (protocol, search, duplicates, journals, screening, human decision, charting, report) that shows what is done, what comes next and, while a step runs, where the process is; a panel per step; live output of each command.
- PALET, a pixel-art robot that comments on each step, asks before anything that costs money and reports errors.
- From the dashboard: start a review from a protocol of `config/`, count and download the approved searches, re-read sources, check journals. Approving a search stays in the terminal.
- `synthesis_selection: core_only` in the protocol: only studies core to a research question are synthesised; the PRISMA flow shows that step. New report files `evidence_by_rq.md` and `selected_studies.csv`.

## Protocol v2: journal filter and decision rule — 2026-11-13

### Added
- Journal lists as an eligibility criterion (`journal_lists` in the protocol, dimension `journal`): records are checked by ISSN (journal title when there is no ISSN) before any model call; reason `NOT_IN_JOURNAL_LIST`. Records now carry `issn`.
- Decision rule `agreement_or_exclude` (`decision_rule` in the protocol): include on agreement; the authors decide "one includes, the other is unsure"; other doubts and disagreements are excluded (`NO_AGREEMENT`), as are records without abstract.
- Commands `set-protocol` (move a run to a new protocol version), `reparse` (rebuild records from the raw data of the run) and `journals` (which records are in the lists; writes `journal_check.csv`).
- `config/protocol_isabel_chapter_v2.yaml` with proposed searches for RQ1, RQ2, RQ3, RQ6 and RQ7.

### Changed
- The protocol path of a run is stored relative to the repository.

## Dashboard for the 2.0 workflow and one-or-two screeners — 2026-11-12

### Added
- `/workflow` page in the dashboard (link "Revisión 2.0"): status of a run, deduplication, screening with a model selector per screener, upload of the adjudication workbook, charting and report, with downloads. Each button runs the corresponding `python -m palet` command in a separate process. Steps that cost money need their estimate and an explicit confirmation, also enforced by the server. API under `/api/v2/`.
- Screening accepts one or two screeners (`palet.toml` or `screen --screeners MODEL[,MODEL]`). With one, decisions are recorded as `single_screener` and the PRISMA diagram and the methods appendix say so.

### Fixed
- Two screeners on the same model shared cached replies, so the second pass copied the first and agreement was a spurious 100%. Each pass now has its own cache scope.

## WP7 (charting), WP9 (reporting) and WP10 (citation check) — 2026-11-12

### Added
- `python -m palet assign`: charts each included record against the research questions of the protocol (core / partial / none). An assignment only counts when its supporting quote is found verbatim in the record; the rest are flagged for review.
- `python -m palet report`: PRISMA flow diagram (PDF + PNG, 600 dpi), counts as JSON, PRISMA-ScR checklist (22 items), methods appendix, list of excluded records with reasons, table and figures of included studies by research question and by year, evidence table. Every number is computed from the files of the run. Pending records are shown apart and the diagram is marked as provisional.
- `python -m palet check-citations`: compares the in-text citations of a manuscript (.docx or text) with its reference list: cited but not listed, listed but not cited, author mismatches, spelling variants, missing a/b suffixes, references abbreviated with "et al.".
- `python -m palet approve-search`: records the authors' approval of one search string in the protocol file (who and when), leaving the rest of the file untouched.

## WP0 — Hygiene and safety net (2026-11-11)

Branch `refactor/palet-2`, starting from tag `v1.0-pre-audit`.

### Fixed
- `escape_latex` escaped its own output (`R&D` became `R\textbackslash{}&D`); it now works in a single pass.
- PRISMA `included` counted a paper once per research question; it now counts unique papers (also in the GUI summary).
- The report, the CLI and MAP read a non-existent `unmatched` key, so unmatched papers always showed as zero.
- A failed MAP analysis was counted as "not relevant". Results now carry a `status`; failures go to a separate `errors` list and are shown apart in PRISMA, the report, the CLI and the GUI.
- A failed synthesis or gap analysis was printed in the report as if it were content; the report now says it could not be generated.
- Search failures (HTTP or network) looked like "no results" or silently truncated the corpus; they now raise `SearchError`. Error messages never include the request URL, which carries the API key.
- OpenAlex pagination stopped after the first page (page size 200 against an API maximum of 100).
- `/api/download` served any file on disk; it now serves only `results/`, `runs/` and `prompts/seed_*.txt`.
- BibTeX export crashed on records without authors or title and wrote `nan` for empty fields.
- The GUI treated the gap analysis as a list; detected gaps are now counted and listed.

### Changed
- Base model is now `claude-opus-5-5` for every phase (was `claude-sonnet-4-6`). Sampling parameters are no longer sent to it and output-token ceilings were raised to leave room for thinking.
- All model calls go through `palet.llm.complete()`.
- Model IDs, prices, token limits and the OpenAlex page size live in `palet.toml` (loaded by `palet/config.py`); none is hardcoded.
- Library code raises exceptions (`palet.errors`) instead of calling `sys.exit`; the Anthropic client is created on first use.
- OpenAlex requests send `OPENALEX_API_KEY`; the contact e-mail is read from `.env` and no longer hardcoded.
- Obsolete modules, prompts and smoke scripts moved to `legacy/`; `synthesis_system.txt` renamed to `synthesis_system_v1.txt`.

### Added
- `palet/` package: `config`, `errors`, `llm`.
- Model catalogue in `palet.toml`, `GET /api/models`, a model selector in the dashboard and `--model` on the command line.
- `tests/` with 190 tests (plus 5 strict `xfail` tests documenting known weaknesses for WP2 and WP4), `pyproject.toml` with pytest and ruff configuration, and a GitHub Actions workflow.
- `.env.example` brought up to date.

### Acceptance
Full pipeline run on 2026-11-11 with `prompts/seed_isabel.txt`, `--max-results 10`, model `claude-opus-5-5`: completed without errors, 37-page PDF. Details in `docs/sesiones/2026-11-11_wp0_fable52.md`.
