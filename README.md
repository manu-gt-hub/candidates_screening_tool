# CV Screening & Technical Evaluation Pipeline

Automated pipeline for screening candidate CVs, generating tailored technical tests, and evaluating candidate responses — powered by Databricks SQL AI functions.

> **⚠️ Disclaimer**: This pipeline uses AI models to parse, evaluate, and generate content. AI outputs may contain errors, inaccuracies, or biases. All rankings, evaluations, technical tests, and reports **require human review** before being used in any hiring decision. This tool is designed to assist — not replace — human judgement in the recruitment process.

---

## Overview

The pipeline consists of two notebooks, a shared utility package (`utils/`), a configuration file, a bootstrap script, and a job orchestration script:

```
technical_tests/
├── config.py.example                  # Configuration template (commit this)
├── config.py                          # Local config with real values (gitignored)
├── build_setup.py                     # Bootstrap script: creates folders + config.py
├── create_jobs.py                     # Script to create scheduled Databricks Jobs
├── .gitignore
├── README.md
├── tech_scenarios_creator              # Notebook 1: CV ranking + test generation
├── tech_responses_evaluator            # Notebook 2: Technical response evaluation
├── utils/                             # Shared utility modules
│   ├── __init__.py
│   ├── config_loader.py               #   Config import + validation
│   ├── pdf_parser.py                  #   PDF parsing with ai_parse_document
│   ├── job_description.py             #   Job description loading (local file)
│   └── pdf_reports.py                 #   PDF generation (tests, ranking, evaluations)
└── resources/                          # All input/output data (gitignored)
    ├── cvs_landing/                   # ↓ Input: candidate CV PDFs
    ├── job_description/               # ↓ Input
    │   └── job_description.txt
    ├── images/                        # ↓ Input
    │   └── <company_logo>.png
    ├── technical_tests/               # ↑ Output: one-page technical test PDFs
    ├── report_analysis/               # ↑ Output: candidate ranking report PDF
    └── technical_responses/            # Candidate technical responses
        ├── landing/                   # ↓ Input: candidate response PDFs
        └── analysis/                  # ↑ Output: evaluation report PDFs
```

---

## Setup

### 1. Create the required folder structure

The easiest way is to run the bootstrap script:

```bash
python build_setup.py
```

This creates all required directories under `resources/` and generates `config.py` from `config.py.example` if it doesn't exist yet. The script is idempotent — safe to run multiple times.

Alternatively, create the folders manually:

```bash
mkdir -p resources/cvs_landing
mkdir -p resources/job_description
mkdir -p resources/images
mkdir -p resources/technical_tests
mkdir -p resources/report_analysis
mkdir -p resources/technical_responses/landing
mkdir -p resources/technical_responses/analysis
```

Then populate the input folders:

| Folder | What to place here |
|---|---|
| `resources/cvs_landing/` | Candidate CV files in **PDF** format |
| `resources/job_description/job_description.txt` | Plain-text description of the role to hire for |
| `resources/images/` | Company logo in **PNG** format (referenced by `LOGO_PATH` in config) |
| `resources/technical_responses/landing/` | Candidate technical response PDFs (for notebook 2) |

Output folders (`technical_tests/`, `report_analysis/`, `technical_responses/analysis/`) are created automatically if missing.

### 2. Configuration

```bash
cp config.py.example config.py   # or run build_setup.py (does this automatically)
```

Edit `config.py`:

| Variable | Description |
|---|---|
| `RESOURCES_BASE` | Auto-resolved from `config.py` location — points to `resources/` |
| `CVS_PATH` | Folder with candidate CV PDFs |
| `ROLE_DESCRIPTION_LOCAL_PATH` | Path to the job description `.txt` file |
| `TECHNICAL_RESPONSES_PATH` | Folder with candidate technical response PDFs (`technical_responses/landing/`) |
| `LOGO_PATH` | Company logo PNG for PDF headers |
| `TECHNICAL_TESTS_OUTPUT_PATH` | Output folder for generated technical test PDFs |
| `EVALUATION_REPORTS_OUTPUT_PATH` | Output folder for the candidate ranking report PDF |
| `TECHNICAL_ANSWERS_ANALYSIS_PATH` | Output folder for evaluation report PDFs (`technical_responses/analysis/`) |
| `AI_MODEL` | Databricks Foundation Model API endpoint (e.g. `databricks-claude-opus-4-6`) |
| `MIN_MATCH_THRESHOLD` | Minimum match % to generate a technical test (default: `70`). Ignored when `GENERATE_TESTS_FOR_ALL_CANDIDATES` is `True` |
| `GENERATE_TESTS_FOR_ALL_CANDIDATES` | When `True`, generate technical tests for all candidates regardless of score (default: `False`) |

All paths are resolved **relative to `config.py`** using `os.path`, so the project works for any user without hardcoded paths.

### 3. Compute requirements

Both notebooks require **Databricks Serverless** compute with:
- Access to the Foundation Model API (`ai_query`, `ai_parse_document`)
- The `reportlab` Python package (installed automatically via `%pip`)

### 4. Job orchestration (optional)

`create_jobs.py` creates two periodic Databricks Jobs:

| Job | Notebook | Description |
|---|---|---|
| **CV Ranking & Technical Test Generation** | `tech_scenarios_creator` | Processes CVs in `cvs_landing/` |
| **Technical Response Evaluator** | `tech_responses_evaluator` | Processes responses in `technical_responses/landing/` |

```python
%run ./create_jobs
```

> **Note**: File-arrival triggers are not supported for workspace paths. These jobs use a cron schedule instead (default: every 15 minutes, configurable via `CRON_SCHEDULE` and `TIMEZONE` in the script).

---

## Notebook 1: `tech_scenarios_creator`

**Purpose**: Parse candidate CVs, rank them against a job description, generate a ranking summary report, and produce one-page technical tests as PDFs.

### Pipeline flow

```
[CV PDFs] → Python read → ai_parse_document → [Extracted text]
                                                     ↓
[Job description] ───────────────────→ ai_query → [Ranking + evaluation]
                                                     ↓
                                     ┌──────────────────┴──────────────────┐
                                     ↓                                    ↓
                          Filter: >= MIN_MATCH_THRESHOLD       All candidates
                          (or all if GENERATE_ALL=True)              ↓
                                     ↓                      Ranking Report PDF
                                ai_query → [3 scenarios]
                                     ↓
                              One-page PDF tests
```

### Cells (execution order)

| # | Cell | Description |
|---|---|---|
| 1 | **Setup & Configuration** | Imports config via `utils.config_loader`, validates all required variables and paths |
| 2 | **Parse candidate CVs** | Uses `utils.pdf_parser` to read and parse all PDFs into a Spark temp view |
| 3 | **Load job description** | Uses `utils.job_description` to load from local file |
| 4 | **Rank candidates with AI** | Evaluates each CV via `ai_query`, assigns match percentage and metadata |
| 5 | **Generate technical tests with AI** | For eligible candidates (see filtering below), generates 3 scenarios via `ai_query` |
| 6 | **Install reportlab** | `%pip install reportlab` |
| 7 | **Generate PDF reports** | Uses `utils.pdf_reports` to create technical test PDFs + ranking report in one cell |

### Candidate filtering for technical tests

| Parameter | Value | Behaviour |
|---|---|---|
| `GENERATE_TESTS_FOR_ALL_CANDIDATES` | `False` (default) | Only candidates with match score **≥ `MIN_MATCH_THRESHOLD`** receive a technical test |
| `GENERATE_TESTS_FOR_ALL_CANDIDATES` | `True` | All candidates receive a technical test, regardless of score |
| `MIN_MATCH_THRESHOLD` | `70` (default) | Minimum match % to qualify for test generation. Also sets the green tier boundary in the ranking report |

---

## Notebook 2: `tech_responses_evaluator`

**Purpose**: Parse candidate technical responses, evaluate them against the job description, and generate professional PDF evaluation reports.

### Pipeline flow

```
[Response PDFs] → Python read → ai_parse_document → [Extracted text]
  (technical_responses/landing/)                          ↓
[Job description] ───────────────────────────→ ai_query → [Evaluation per candidate]
                                                          ↓
                                                     reportlab → [PDF evaluation reports]
                                                              (technical_responses/analysis/)
```

### Cells (execution order)

| # | Cell | Description |
|---|---|---|
| 1 | **Setup & Configuration** | Imports config via `utils.config_loader`, validates all required variables and paths |
| 2 | **Parse candidate response PDFs** | Uses `utils.pdf_parser` to read and parse response PDFs into a Spark temp view |
| 3 | **Load job description** | Uses `utils.job_description` to load from local file |
| 4 | **Evaluate responses with AI** | Evaluates each response via `ai_query` with structured JSON output |
| 5 | **Install reportlab** | `%pip install reportlab` |
| 6 | **Generate evaluation PDF reports** | Uses `utils.pdf_reports` to create colour-coded evaluation reports per candidate |

---

## AI Functions Used

| Function | Purpose |
|---|---|
| `ai_parse_document` | Extracts structured text from PDF files (version 2.0) |
| `ai_query` | Sends prompts to the configured LLM with structured JSON response format |

---

## Output PDFs

### Technical tests (Notebook 1 → `resources/technical_tests/`)
- **One page per candidate** (compact layout with automatic content truncation)
- Company logo in header (6 cm)
- Test title, instructions, 3 technical scenarios
- Each scenario: description, concrete example (amber), evaluation question (wine red)
- Colour palette: navy title, teal scenario headings, slate instructions, dark grey body
- Tailored to the candidate's seniority level and technologies

### Candidate ranking report (Notebook 1 → `resources/report_analysis/`)
- Single PDF: `Candidate_Ranking_Report_<date>.pdf`
- All candidates sorted by match score (descending), with score, seniority, experience, summary, and key technologies
- Colour-coded scores (green ≥ `MIN_MATCH_THRESHOLD`, amber ≥ 50%, red < 50%)

### Evaluation reports (Notebook 2 → `resources/technical_responses/analysis/`)
- One PDF per candidate: `Evaluation_Report_<Name>_<date>.pdf`
- Colour-coded match score card with recommendation (Strong Hire / Hire / Lean Hire / Lean No Hire / No Hire)
- Suitability assessment and key highlights
- Per-scenario scores with feedback
- Strengths, weaknesses, and improvement areas

---

## Security Notes

- `config.py` is excluded from version control via `.gitignore`
- `resources/` is excluded from version control via `.gitignore` — it contains candidate data (CVs, responses), company assets (logo), and generated reports
- No API keys, usernames, or sensitive paths in notebooks, scripts, or this README
- All paths are resolved dynamically relative to the project directory
- `create_jobs.py` resolves the current user at runtime via the Databricks SDK
- **Important**: Clear notebook cell outputs before committing — they may contain internal paths or candidate names
