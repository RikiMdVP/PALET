# PALET — Prompt-based Automated Literature Extraction Tool

> An AI-powered pipeline for systematic literature reviews following PRISMA-ScR guidelines.

[![Python](https://img.shields.io/badge/Python-3.12%2B-blue?logo=python)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.128-009688?logo=fastapi)](https://fastapi.tiangolo.com/)
[![Anthropic](https://img.shields.io/badge/Powered%20by-Claude%20(Anthropic)-blueviolet)](https://www.anthropic.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![ISABEL Project](https://img.shields.io/badge/EU%20Horizon-Grant%20101177687-003399)](https://cordis.europa.eu/)

---

## Overview

**PALET** is an AI-powered research tool designed to automate the systematic literature review process. It integrates Large Language Models (via the Anthropic API) with academic database search engines (OpenAlex, PubMed) to assist researchers in conducting rigorous, reproducible bibliographic reviews aligned with the [PRISMA-ScR](https://www.equator-network.org/reporting-guidelines/prisma-scr/) reporting standard.

PALET was developed as part of the **[ISABEL Project](https://cordis.europa.eu/)** (Grant Agreement No. 101177687), funded by the European Union's Horizon research and innovation programme, focused on employment creation and destruction related to green and digital transitions in the EU.

---

## Key Features

- **ARQ** — Automated Research Query: extracts research questions, keywords, inclusion/exclusion criteria, and search filters from a structured seed prompt.
- **QSP** — Query Structuring Process: generates optimised Boolean search strings for multiple academic databases.
- **SE** — Search Execution: queries OpenAlex and PubMed, retrieves bibliographic metadata, deduplicates results, and exports to structured CSV.
- **MAP** — Matching and Assignment Process: semantically assigns retrieved papers to research questions using Claude (`temperature=0` for reproducibility).
- **PRISMA Validator** — generates PRISMA-ScR flow diagram and compliance checklist.
- **Synthesis Module** — produces narrative synthesis per research question and detects literature gaps.
- **Report Generator** — compiles all outputs into a structured LaTeX/PDF report.
- **Web GUI** — single-page FastAPI application with real-time pipeline execution, run history, and dark mode.

---

## Pipeline Architecture

```
Seed Prompt (structured)
        │
        ▼
   ┌─────────┐
   │   ARQ   │  → Research Questions + Keywords + Filters
   └────┬────┘
        │
        ▼
   ┌─────────┐
   │   QSP   │  → Boolean Search Strings (per database)
   └────┬────┘
        │
        ▼
   ┌─────────┐
   │    SE   │  → CSV with deduplicated bibliographic metadata
   └────┬────┘
        │
        ▼
   ┌─────────┐
   │   MAP   │  → Papers assigned to Research Questions
   └────┬────┘
        │
        ▼
   ┌──────────────────┐
   │ PRISMA Validator │  → Flow diagram + Checklist
   └────────┬─────────┘
            │
            ▼
   ┌──────────────────┐
   │ Synthesis Module │  → Narrative synthesis + Gap analysis
   └────────┬─────────┘
            │
            ▼
   ┌──────────────────┐
   │ Report Generator │  → PDF report (LaTeX)
   └──────────────────┘
```

---

## Requirements

- Python 3.12+
- [MacTeX](https://www.tug.org/mactex/) (for PDF report generation via LaTeX)
- An [Anthropic API key](https://www.anthropic.com/)
- Optional: NCBI API key (for higher PubMed rate limits)

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/palet.git
cd palet
```

### 2. Create a virtual environment

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

> **Apple Silicon note:** If you encounter NumPy import errors, ensure you are using Homebrew's Python 3.12 (`/opt/homebrew/bin/python3.12`) to avoid arm64/x86_64 architecture conflicts.

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and fill in your API keys:

```env
ANTHROPIC_API_KEY=your_anthropic_api_key_here
NCBI_API_KEY=your_ncbi_api_key_here   # optional but recommended
```

---

## Usage

### Web Interface (recommended)

```bash
source .venv/bin/activate
uvicorn app:app --reload
```

Then open your browser at [http://localhost:8000](http://localhost:8000).

From the GUI you can:
- Create a new review from a seed prompt
- Monitor pipeline execution in real time
- Browse run history and download reports

### Command Line

```bash
python palet.py --seed-prompt prompts/seed_isabel.txt --output results/
```

### Seed Prompt Format

For best results, your seed prompt should include:

1. **Research topic** — a clear description of the subject area
2. **Research questions** — ideally 5–10 specific RQs
3. **Target population/context**
4. **Time frame** (e.g., 2010–2025)
5. **Geographic scope**
6. **Language filters**
7. **Document types** (journal articles, reports, etc.)

See [`prompts/seed_isabel.txt`](prompts/seed_isabel.txt) for a complete example.

---

## Project Structure

```
palet/
├── app.py                  # FastAPI web application
├── palet.py                # Main pipeline orchestrator
├── prisma_validator.py     # PRISMA-ScR flow diagram & checklist
├── scripts/
│   ├── arq_module.py       # ARQ: Research question extraction
│   ├── qsp_module.py       # QSP: Boolean query generation
│   ├── se_module.py        # SE: Database search & deduplication
│   ├── map_module_v2.py    # MAP: Semantic paper assignment
│   ├── synthesis_module.py # Narrative synthesis & gap detection
│   └── report_generator_v2.py  # LaTeX/PDF report generation
├── prompts/
│   ├── arq_system_v3.txt   # ARQ system prompt
│   ├── qsp_system_v2.txt   # QSP system prompt
│   ├── map_system_v2.txt   # MAP system prompt
│   ├── synthesis_system.txt
│   └── seed_isabel.txt     # Example seed prompt (ISABEL project)
├── templates/
│   └── index.html          # Web GUI template
├── static/                 # CSS and JS assets
├── data/                   # Input data (gitignored)
├── results/                # Generated outputs (gitignored)
├── outputs/                # Pipeline outputs (gitignored)
├── logs/                   # Execution logs (gitignored)
├── .env.example            # Environment variables template
└── requirements.txt
```

---

## Academic Databases Supported

| Database | Access | Notes |
|----------|--------|-------|
| [OpenAlex](https://openalex.org/) | Free, no key required | Citation stats available |
| [PubMed](https://pubmed.ncbi.nlm.nih.gov/) | Free, NCBI key recommended | No citation counts |
| Scopus | Pending institutional access | Integration planned |

---

## PRISMA-ScR Compliance

PALET is designed to support systematic reviews following the **PRISMA for Scoping Reviews (PRISMA-ScR)** checklist. The pipeline:

- Separates excluded papers into `not_relevant` vs `no_abstract` categories (PRISMA items 17–18)
- Generates a PRISMA flow diagram automatically from deduplication and filtering statistics
- Produces a compliance checklist that can be included in publications

---

## Configuration Notes

- **Reproducibility:** MAP module uses `temperature=0` to ensure consistent paper assignments across runs.
- **Deduplication:** DOI-based normalisation removes cross-database duplicates; `cited_by_count` is set to `None` for PubMed entries to avoid contaminating citation statistics.
- **LaTeX:** Reports are generated with MacTeX. Cyrillic author names from OpenAlex may produce Unicode warnings (fix in progress: `\usepackage{newunicodechar}` + transliteration).

---

## Authors

- **Ricardo Martínez de Vega Perancho** — REGIOlab, University of Oviedo
- **Fernando Rubiera Morollón** — REGIOlab, University of Oviedo

---

## Funding

This project has received funding from the **European Union's Horizon research and innovation programme** under grant agreement No **101177687** (ISABEL Project).

<p>
  <img src="https://upload.wikimedia.org/wikipedia/commons/thumb/b/b7/Flag_of_Europe.svg/320px-Flag_of_Europe.svg.png" alt="EU Flag" width="80"/>
</p>

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

## Contributing

This is a research tool under active development. If you find a bug or have a suggestion, please open an [issue](https://github.com/YOUR_USERNAME/palet/issues).
