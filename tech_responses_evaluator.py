# Databricks notebook source
# DBTITLE 1,Install reportlab
# MAGIC %pip install reportlab --quiet

# COMMAND ----------

# DBTITLE 1,Setup & Configuration
# ── Setup & Configuration ────────────────────────────────────────
import sys, os

# Ensure project dir is in sys.path and clear stale module caches
_nb_path = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
_project_dir = f"/Workspace{os.path.dirname(_nb_path)}"
if _project_dir not in sys.path:
    sys.path.insert(0, _project_dir)
for _m in [m for m in sys.modules if m == "config" or m.startswith("utils")]:
    del sys.modules[_m]

from utils.config_loader import load_config, validate_config

config = load_config(dbutils)
validate_config(config, mode="evaluator")

print(f"  Responses path:  {config.TECHNICAL_RESPONSES_PATH}")
print(f"  Analysis output: {config.TECHNICAL_ANSWERS_ANALYSIS_PATH}")
print(f"  AI model:        {config.AI_MODEL}")

# COMMAND ----------

# DBTITLE 1,Parse candidate response PDFs
# ── Parse candidate response PDFs ────────────────────────────────
from utils.pdf_parser import parse_pdfs_to_view

n_responses = parse_pdfs_to_view(spark, config.TECHNICAL_RESPONSES_PATH, view_name="response_texts")
if n_responses == 0:
    raise RuntimeError(f"No PDF files found in {config.TECHNICAL_RESPONSES_PATH}")

# COMMAND ----------

# DBTITLE 1,Load job description
# ── Load job description ─────────────────────────────────────────
from utils.job_description import load_job_description

job_description_text = load_job_description(spark, config)

# COMMAND ----------

# DBTITLE 1,Evaluate responses with AI
# Step 3: Evaluate each technical response against the role description
# Prompt text comes from utils/prompts.py — single source of truth for both modes.
from utils.prompts import build_evaluation_prompt_parts, sql_esc

_ev_prefix, _ev_sep, _ev_suffix = build_evaluation_prompt_parts()

evaluations_df = spark.sql(f"""
SELECT
  evaluation.*,
  path AS response_file
FROM (
  SELECT
    from_json(
      ai_query(
        '{config.AI_MODEL}',
        CONCAT(
          '{sql_esc(_ev_prefix)}',
          rd.full_text,
          '{sql_esc(_ev_sep)}',
          r.full_text
        ),
        responseFormat => 'STRUCT<result:STRUCT<candidate_name:STRING, match_percentage:DOUBLE, suitability_assessment:STRING, highlights:ARRAY<STRING>, strengths:ARRAY<STRING>, weaknesses:ARRAY<STRING>, scenario_evaluations:ARRAY<STRUCT<scenario_number:INT, scenario_title:STRING, score:DOUBLE, feedback:STRING>>, overall_recommendation:STRING, improvement_areas:ARRAY<STRING>>>'
      ),
      'candidate_name STRING, match_percentage DOUBLE, suitability_assessment STRING, highlights ARRAY<STRING>, strengths ARRAY<STRING>, weaknesses ARRAY<STRING>, scenario_evaluations ARRAY<STRUCT<scenario_number:INT, scenario_title:STRING, score:DOUBLE, feedback:STRING>>, overall_recommendation STRING, improvement_areas ARRAY<STRING>'
    ) AS evaluation,
    r.path
  FROM response_texts r
  CROSS JOIN role_description rd
) results
ORDER BY evaluation.match_percentage DESC
""")

# Materialize results once to avoid re-running AI in cell 5
evaluation_rows = evaluations_df.collect()

# Display results from materialized data
display(spark.createDataFrame(evaluation_rows, evaluations_df.schema))

print(f"\nEvaluated {len(evaluation_rows)} candidate(s):")
for row in evaluation_rows:
    print(f"  {row['candidate_name']}: {row['match_percentage']:.0f}% - {row['overall_recommendation']}")

# COMMAND ----------

# DBTITLE 1,Generate evaluation PDF reports
# ── Generate evaluation PDF reports ──────────────────────────────
# Re-import config and utils after pip install
import sys, os
_nb_path = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
_project_dir = f"/Workspace{os.path.dirname(_nb_path)}"
if _project_dir not in sys.path:
    sys.path.insert(0, _project_dir)
for _m in [m for m in sys.modules if m == "config" or m.startswith("utils")]:
    del sys.modules[_m]
import config

from utils.pdf_reports import build_evaluation_report_pdf

OUTPUT_PATH = config.TECHNICAL_ANSWERS_ANALYSIS_PATH
os.makedirs(OUTPUT_PATH, exist_ok=True)

generated = []
for row in evaluation_rows:
    ev = row.asDict()
    ev.pop("response_file", None)
    try:
        pdf = build_evaluation_report_pdf(ev, OUTPUT_PATH)
        generated.append({
            "candidate": ev.get("candidate_name"),
            "match": ev.get("match_percentage"),
            "recommendation": ev.get("overall_recommendation"),
            "pdf": pdf,
        })
        print(f"\u2713 {pdf}")
    except Exception as e:
        print(f"\u2717 {ev.get('candidate_name', '?')}: {e}")
        import traceback; traceback.print_exc()

print(f"\n{'='*60}")
print(f"Generated {len(generated)} evaluation report(s) \u2192 {OUTPUT_PATH}")