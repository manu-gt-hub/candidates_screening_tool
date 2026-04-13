# CV Screening & Technical Evaluation — Quick Guide

> **⚠️** AI-powered pipeline. All outputs **require human review** before any hiring decision.

---

## 1. Initial Setup

Run the bootstrap script to create the folder structure and `config.py`:

```bash
python build_setup.py
```

This creates all directories under `resources/` and copies `config.py.example` → `config.py`.  
Adjust `config.py` if needed (AI model, thresholds, logo path).  

#### *All noteboks must be executed in serverless mode  
  

---

## 2. Generate Technical Tests

1. Place the **job description** in `resources/job_description/job_description.txt`
2. Place the **company logo** (PNG) in `resources/images/`
3. Drop candidate **CV PDFs** into `resources/cvs_landing/`
4. Run the notebook **`tech_scenarios_creator`** (all cells, top to bottom)

**Outputs:**

| What | Where |
|---|---|
| Individual technical test PDFs | `resources/technical_tests/` |
| Candidate ranking report PDF | `resources/report_analysis/` |

The ranking report includes all candidates colour-coded by match score.  
Technical tests are only generated for candidates above the configured threshold (default: 70%).

---

## 3. Evaluate Candidate Responses

1. Send the generated test PDFs to candidates
2. Once they respond, drop their **response PDFs** into `resources/technical_responses/landing/`
3. Run the notebook **`tech_responses_evaluator`** (all cells, top to bottom)

**Outputs:**

| What | Where |
|---|---|
| Per-candidate evaluation report PDFs | `resources/technical_responses/analysis/` |

Each report includes a match score, hire recommendation, per-scenario feedback, strengths, and weaknesses.

---

## Folder Structure (reference)

```
resources/
├── cvs_landing/                    ← Input: candidate CVs (PDF)
├── job_description/                ← Input: job_description.txt
├── images/                         ← Input: company logo (PNG)
├── technical_tests/                → Output: technical test PDFs
├── report_analysis/                → Output: ranking report PDF
└── technical_responses/
    ├── landing/                    ← Input: candidate response PDFs
    └── analysis/                   → Output: evaluation report PDFs
```

---

## Requirements

* **Databricks Serverless** compute with Foundation Model API access
* `reportlab` (installed automatically via `%pip` in each notebook)
