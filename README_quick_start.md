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

---

## 2. Choose Your Execution Mode

The pipeline supports two execution modes, controlled by `ENVIRONMENT` in `config.py`:

| Value | Mode | How to run |
|---|---|---|
| `"AUTO"` (default) | Auto-detect: Databricks if runtime present, otherwise local | — |
| `"DBX"` | Force **Databricks** | Run notebooks on serverless compute |
| `"LOCAL"` | Force **Local** | `python run_local.py scenarios` |

**Databricks mode** uses Spark SQL + `ai_query` (Foundation Model API).  
**Local mode** uses AWS Bedrock-compatible API via `boto3` — set `API_KEY`, `API_BASE_URL`, and `LOCAL_AI_MODEL` in `config.py`.

---

## 3. Generate Technical Tests

1. Place the **job description** in `resources/job_description/job_description.txt`
2. Place the **company logo** (PNG) in `resources/images/` *(optional)*
3. Drop candidate **CV PDFs** into `resources/cvs_landing/`

**Databricks:**
```
Run notebook tech_scenarios_creator (all cells, top to bottom, serverless mode)
```

**Local:**
```bash
pip install boto3 pdfplumber reportlab
python run_local.py scenarios
```

**Outputs:**

| What | Where |
|---|---|
| Individual technical test PDFs | `resources/technical_tests/` |
| Candidate ranking report PDF | `resources/report_analysis/` |

The ranking report includes all candidates colour-coded by match score.  
Technical tests are only generated for candidates above the configured threshold (default: 70%).

---

## 4. Evaluate Candidate Responses

1. Send the generated test PDFs to candidates
2. Once they respond, drop their **response PDFs** into `resources/technical_responses/landing/`

**Databricks:**
```
Run notebook tech_responses_evaluator (all cells, top to bottom, serverless mode)
```

**Local:**
```bash
python run_local.py evaluate
```

**Outputs:**

| What | Where |
|---|---|
| Per-candidate evaluation report PDFs | `resources/technical_responses/analysis/` |

Each report includes a match score, hire recommendation, per-scenario feedback, strengths, and weaknesses.

---

## Folder Structure (reference)

```
candidates_manager_dbx/
├── config.py.example                    # Configuration template
├── config.py                            # Local config (gitignored)
├── build_setup.py                       # Bootstrap script
├── run_local.py                         # Local runner (no Spark needed)
├── README.md / README_quick_start.md
├── tech_scenarios_creator               # Notebook 1: CV ranking + test generation
├── tech_responses_evaluator             # Notebook 2: Response evaluation
├── utils/
│   ├── config_loader.py                 #   Config import + validation (Databricks)
│   ├── llm_client.py                    #   LLM abstraction (DBX + LOCAL)
│   ├── prompts.py                       #   Prompt templates
│   ├── pipeline.py                      #   Core pipeline logic (for local mode)
│   ├── pdf_parser.py                    #   PDF parsing
│   ├── job_description.py               #   Job description loader
│   └── pdf_reports.py                   #   PDF generation (reportlab)
└── resources/                           # All input/output data (gitignored)
    ├── cvs_landing/                     ← Input: candidate CVs (PDF)
    ├── job_description/                 ← Input: job_description.txt
    ├── images/                          ← Input: company logo (PNG)
    ├── technical_tests/                 → Output: technical test PDFs
    ├── report_analysis/                 → Output: ranking report PDF
    └── technical_responses/
        ├── landing/                     ← Input: candidate response PDFs
        └── analysis/                    → Output: evaluation report PDFs
```

---

## Requirements

**Databricks mode:**
* Databricks Serverless compute with Foundation Model API access
* `reportlab` (installed automatically via `%pip` in each notebook)

**Local mode:**
* Python 3.9+
* `pip install boto3 pdfplumber reportlab`
* An API key for a Bedrock-compatible provider (set `API_KEY` in `config.py`)
