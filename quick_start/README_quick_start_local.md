# Quick Start — Local Mode

> **⚠️** AI-powered pipeline. All outputs **require human review** before any hiring decision.

---

## Prerequisites

- Python 3.9+
- An API key for an AWS Bedrock-compatible provider

Install dependencies:

```bash
pip install boto3 pdfplumber reportlab
```

---

## 1. Initial Setup

Run the bootstrap script to create the folder structure:

```bash
python build_setup.py
```

This creates all directories under `resources/` and generates `config.py` from `config.py.example`.

Edit `config.py`:

| Variable | What to set |
|---|---|
| `API_KEY` | Your Bedrock-compatible API key |
| `API_BASE_URL` | Endpoint URL for the LLM provider |
| `LOCAL_AI_MODEL` | Model name (e.g. `claude-opus-4.6`) |
| `ENVIRONMENT` | `"LOCAL"` or leave as `"AUTO"` |
| `MIN_MATCH_THRESHOLD` | Minimum match % for technical test generation (default: `70`) |
| `GENERATE_TESTS_FOR_ALL_CANDIDATES` | `True` to generate tests for all candidates regardless of score |
| `TECHNICAL_CONTEXT` | Optional business domain (e.g. `"e-commerce logistics"`) for domain-specific prompts |

---

## 2. Prepare Input Data

| What | Where |
|---|---|
| Job description (plain text) | `resources/job_description/job_description.txt` |
| Candidate CV PDFs | `resources/cvs_landing/` |
| Company logo PNG *(optional)* | `resources/images/` |

---

## 3. Run CV Ranking & Technical Test Generation

```bash
python run_local.py scenarios
```

This will:
1. Parse all CV PDFs using `pdfplumber`
2. Rank each candidate against the job description via LLM
3. Generate 3 unique technical scenarios per qualifying candidate
4. Output PDF reports

**Outputs:**

| What | Where |
|---|---|
| Technical test PDFs (one per candidate) | `resources/technical_tests/` |
| Candidate ranking report PDF | `resources/report_analysis/` |

---

## 4. Evaluate Candidate Responses

1. Send the generated test PDFs to candidates
2. Collect their response PDFs into `resources/technical_responses/landing/`
3. Run:

```bash
python run_local.py evaluate
```

**Outputs:**

| What | Where |
|---|---|
| Evaluation report PDFs (one per candidate) | `resources/technical_responses/analysis/` |

Each report includes: match score, hire recommendation, per-scenario feedback, strengths, and weaknesses.

---

## Run Both Stages at Once

```bash
python run_local.py all
```
