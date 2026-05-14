# Quick Start — Databricks Mode

> **⚠️** AI-powered pipeline. All outputs **require human review** before any hiring decision.

---

## Prerequisites

- Databricks workspace with **Serverless compute** and **Foundation Model API** access
- `reportlab` is installed automatically via `%pip` in each notebook

---

## 1. Initial Setup

Run the bootstrap notebook or script to create the folder structure:

```
%run ./build_setup
```

This creates all directories under `resources/` and generates `config.py` from `config.py.example`.

Edit `config.py`:

| Variable | What to set |
|---|---|
| `AI_MODEL` | Your Databricks Foundation Model endpoint (e.g. `databricks-claude-opus-4-6`) |
| `ENVIRONMENT` | `"DBX"` or leave as `"AUTO"` (auto-detects Databricks runtime) |
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

Open **`tech_scenarios_creator`** notebook and run all cells top to bottom on **serverless compute**.

The notebook will:
1. Parse all CV PDFs using `ai_parse_document`
2. Rank each candidate against the job description via `ai_query`
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
3. Open **`tech_responses_evaluator`** notebook and run all cells top to bottom on **serverless compute**

**Outputs:**

| What | Where |
|---|---|
| Evaluation report PDFs (one per candidate) | `resources/technical_responses/analysis/` |

Each report includes: match score, hire recommendation, per-scenario feedback, strengths, and weaknesses.
