# CV Screening & Technical Evaluation Pipeline

Automated pipeline for screening candidate CVs, generating tailored technical tests, and evaluating candidate responses — powered by Databricks SQL AI functions.

> **⚠️ Disclaimer**: This pipeline uses AI models to parse, evaluate, and generate content. AI outputs may contain errors, inaccuracies, or biases. All rankings, evaluations, technical tests, and reports **require human review** before being used in any hiring decision. This tool is designed to assist — not replace — human judgement in the recruitment process.

## Overview

The pipeline consists of two independent notebooks, a shared configuration file, and a job orchestration script:

```
technical_tests/
├── config.py.example        # Configuration template (commit this)
├── config.py                # Local configuration with real values (gitignored)
├── create_jobs.py           # Script to create Databricks Jobs with file-arrival triggers
├── .gitignore               # Excludes config.py and Python cache
├── README.md                # This file
├── tech_scenarios_creator   # Notebook 1: CV ranking + technical test generation
└── tech_responses_evaluator # Notebook 2: Technical response evaluation
```

## Setup

### 1. Configuration

```bash
# Copy the template and fill in your values
cp config.py.example config.py
```

Edit `config.py` with your environment-specific values:

| Variable | Description |
|---|---|
| `VOLUME_BASE` | Base path to the Unity Catalog Volume containing all data folders |
| `CVS_PATH` | Folder with candidate CV PDFs |
| `ROLE_DESCRIPTION_LOCAL_PATH` | Path to the job description text file |
| `TECHNICAL_RESPONSES_PATH` | Folder with candidate technical response PDFs |
| `LOGO_PATH` | Company logo PNG for PDF headers |
| `TECHNICAL_TESTS_OUTPUT_PATH` | Output folder for generated technical test PDFs |
| `EVALUATION_REPORTS_OUTPUT_PATH` | Output folder for generated evaluation report PDFs |
| `AI_MODEL` | Databricks Foundation Model API endpoint (e.g. `databricks-claude-sonnet-4`) |
| `TOP_X` | Number of top candidates for test generation (`0` = all candidates) |
| `JOB_DESCRIPTION_URL` | *(optional)* Set env var `JOB_DESCRIPTION_URL` to fetch the job description from a remote URL (e.g. Confluence). Falls back to local file if unset. |

### 2. Volume structure

The pipeline expects the following folder layout inside your Unity Catalog Volume:

```
<volume_base>/
├── cvs/                    # Input: candidate CV PDFs
├── role_description/
│   └── job_description.txt # Input: job/role description
├── logo/
│   └── mercedes_logo.png   # Input: company logo for PDF headers
├── technical_tests/        # Output: generated technical test PDFs
├── technical_responses/    # Input: candidate response PDFs
└── evaluation_reports/     # Output: generated evaluation report PDFs
```

### 3. Compute

Both notebooks run on **Databricks Serverless** compute (auto-selected). They require:
- Access to the configured Unity Catalog Volume
- Access to the Databricks Foundation Model API (`ai_query`)
- The `reportlab` Python package (installed automatically via `%pip`)

### 4. Job orchestration (file-arrival triggers)

`create_jobs.py` creates two Databricks Jobs that run the notebooks automatically when new files arrive:

| Job | Notebook | Monitors |
|---|---|---|
| **CV Ranking & Technical Test Generation** | `tech_scenarios_creator` | `CVS_PATH` — triggers on new CV PDFs |
| **Technical Response Evaluator** | `tech_responses_evaluator` | `TECHNICAL_RESPONSES_PATH` — triggers on new response PDFs |

To create the jobs, run the script once from a notebook cell in the same folder:

```python
%run ./create_jobs
```

Or from a terminal with `DATABRICKS_HOST` and `DATABRICKS_TOKEN` configured:

```bash
python create_jobs.py
```

The script resolves all paths dynamically from `config.py` and the current user context — no hardcoded values. Both jobs are created in **UNPAUSED** state and start monitoring immediately.

**Trigger settings** (configurable in `create_jobs.py`):

| Constant | Default | Description |
|---|---|---|
| `MIN_TIME_BETWEEN_TRIGGERS` | 60s | Minimum cooldown between consecutive runs |
| `WAIT_AFTER_LAST_CHANGE` | 30s | Debounce window — waits after the last file change before triggering (batches multiple uploads) |

---

## Notebook 1: `tech_scenarios_creator`

**Purpose**: Parse candidate CVs, rank them against a job description, and generate personalised technical tests as PDFs.

### Pipeline flow

```
[CV PDFs] → ai_parse_document → [Full text]
                                      ↓
[Job description] ──────────────→ ai_query → [Ranking + evaluation per candidate]
                                      ↓
                              Filter: non-discarded + TOP_X
                                      ↓
                                 ai_query → [3 technical scenarios per candidate]
                                      ↓
                                 reportlab → [PDF technical tests]
```

### Cells (execution order)

| # | Cell | Description |
|---|---|---|
| 1 | **Load configuration** | Dynamically imports `config.py` from the notebook's directory |
| 2 | **Parse all CVs** | Uses `ai_parse_document` to extract text from all PDFs in the CVs folder |
| 3 | **Load role description** | Fetches job description from URL (if configured) or local file |
| 4 | **AI ranking** | Evaluates each CV against the job description. Outputs: name, ranking percentage, report summary, role, seniority, years of experience, key technologies, highlights, gaps, discarded flag, discard reason |
| 5 | **Configure TOP_X** | Reads `TOP_X` from config (`0` = all candidates) |
| 6 | **Generate technical tests** | For the top X non-discarded candidates, generates 3 tailored technical scenarios per candidate via AI |
| 7 | **Install reportlab** | Installs the PDF generation library |
| 8 | **Generate PDFs** | Creates professional PDF technical tests with company logo |

### Discarded candidates

Candidates missing **mandatory** skills for the role (e.g., Spark, SQL, Python/Java/Scala for a Data Engineer) are automatically flagged as `discarded = true` with a reason. They appear in the ranking (cell 4) but are excluded from technical test generation (cell 6).

### TOP_X behaviour

| Value | Behaviour |
|---|---|
| `TOP_X = 0` | Generate technical tests for **all** non-discarded candidates |
| `TOP_X = N` | Generate technical tests for the **top N** candidates (by ranking score) |

---

## Notebook 2: `tech_responses_evaluator`

**Purpose**: Parse candidate technical responses, evaluate them against the job description, and generate professional PDF evaluation reports.

### Pipeline flow

```
[Response PDFs] → ai_parse_document → [Full text]
                                            ↓
[Job description] ────────────────────→ ai_query → [Evaluation per candidate]
                                            ↓
                                       reportlab → [PDF evaluation reports]
```

### Cells (execution order)

| # | Cell | Description |
|---|---|---|
| 1 | **Load configuration** | Dynamically imports `config.py` from the notebook's directory |
| 2 | **Load role description** | Fetches job description (same URL/local fallback logic) |
| 3 | **Parse response PDFs** | Extracts text from all PDFs in the technical responses folder |
| 4 | **AI evaluation** | Evaluates each response. Outputs: candidate name, match percentage, suitability assessment, highlights, strengths, weaknesses, per-scenario scores and feedback, overall recommendation, improvement areas |
| 5 | **Install reportlab** | Installs the PDF generation library |
| 6 | **Generate PDF reports** | Creates colour-coded evaluation reports (green ≥70%, amber 50-69%, red <50%) with recommendation (Strong Hire / Hire / Lean Hire / Lean No Hire / No Hire) |

---

## AI Functions Used

| Function | Purpose |
|---|---|
| `ai_parse_document` | Extracts structured text from PDF files (version 2.0) |
| `ai_query` | Sends prompts to the configured LLM with structured JSON response format |

---

## Output PDFs

### Technical tests (Notebook 1)
- Company logo in header (top-right, 4cm)
- Test title, instructions, 3 technical scenarios
- Each scenario: description, concrete example, evaluation question
- Tailored to the candidate's seniority level and technologies

### Evaluation reports (Notebook 2)
- Colour-coded match score card
- Suitability assessment and key highlights
- Per-scenario scores with feedback
- Strengths, weaknesses, and improvement areas
- Overall recommendation

---

## Security Notes

- `config.py` contains environment-specific paths and is excluded from version control via `.gitignore`
- The `JOB_DESCRIPTION_URL` is read from an environment variable, never hardcoded
- No API keys, usernames, or sensitive paths are stored in the notebooks, scripts, or this README
- `create_jobs.py` resolves the current user and notebook paths at runtime via the Databricks SDK
- To set up a new environment, copy `config.py.example` → `config.py` and fill in your values
