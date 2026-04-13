# Databricks notebook source
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
validate_config(config, mode="scenarios")

print(f"  CVs path:      {config.CVS_PATH}")
print(f"  Tests output:  {config.TECHNICAL_TESTS_OUTPUT_PATH}")
print(f"  Reports out:   {config.EVALUATION_REPORTS_OUTPUT_PATH}")
print(f"  AI model:      {config.AI_MODEL}")
print(f"  Min threshold: {config.MIN_MATCH_THRESHOLD}%")
print(f"  Tests for all: {config.GENERATE_TESTS_FOR_ALL_CANDIDATES}")

# COMMAND ----------

# DBTITLE 1,Parse candidate CVs
# ── Parse candidate CVs ──────────────────────────────────────────
from utils.pdf_parser import parse_pdfs_to_view

n_cvs = parse_pdfs_to_view(spark, config.CVS_PATH, view_name="cv_texts")
if n_cvs == 0:
    raise RuntimeError(f"No PDF files found in {config.CVS_PATH}")

# COMMAND ----------

# DBTITLE 1,Load job description
# ── Load job description ─────────────────────────────────────────
from utils.job_description import load_job_description

job_description_text = load_job_description(spark, config)

# COMMAND ----------

# DBTITLE 1,Rank candidates with AI
# Step 2: Rank all candidates against the job description (no one is discarded)
_min_interview = config.MIN_MATCH_THRESHOLD
print(f"Minimum match for technical test: {_min_interview}%")

_ranking_sql = f"""
SELECT
  parsed_result.*,
  source_file
FROM (
  SELECT
    from_json(
      ai_query(
        '{config.AI_MODEL}',
        CONCAT(
          'You are an expert HR analyst and technical recruiter. Evaluate the following CV/resume against the provided JOB DESCRIPTION. The ranking must reflect how well the candidate matches the specific role requirements.

Return ONLY a valid JSON object with exactly these fields:

- name (string): Full name of the candidate
- ranking_percentage (number): Score 0-100 representing how well the candidate matches the JOB DESCRIPTION
- report_summary (string): 2-3 sentences evaluating the candidate FIT for this specific role
- role (string): The role title from the job description
- seniority (string): The candidate''s actual seniority level based on their professional experience. One of "Junior", "Mid", "Senior", "Lead", "Principal"
- jd_seniority (string): The seniority level REQUIRED by the JOB DESCRIPTION (not the candidate''s level). One of "Junior", "Mid", "Senior", "Lead", "Principal"
- years_of_experience (integer): Estimated total years of professional experience
- key_technologies (array of strings): All technologies mentioned in the CV
- cv_highlights (array of strings): 3-5 most impressive achievements RELEVANT to this job
- gaps (array of strings): Missing skills or requirements from the JOB DESCRIPTION
- discarded (boolean): ALWAYS set to false
- discarded_reason (string or null): ALWAYS set to null

=== JOB DESCRIPTION ===
',
          rd.full_text,
          '

=== CANDIDATE CV ===
',
          cv.full_text
        ),
        responseFormat => 'STRUCT<result:STRUCT<name:STRING, ranking_percentage:DOUBLE, report_summary:STRING, role:STRING, seniority:STRING, jd_seniority:STRING, years_of_experience:INT, key_technologies:ARRAY<STRING>, cv_highlights:ARRAY<STRING>, gaps:ARRAY<STRING>, discarded:BOOLEAN, discarded_reason:STRING>>'
      ),
      'name STRING, ranking_percentage DOUBLE, report_summary STRING, role STRING, seniority STRING, jd_seniority STRING, years_of_experience INT, key_technologies ARRAY<STRING>, cv_highlights ARRAY<STRING>, gaps ARRAY<STRING>, discarded BOOLEAN, discarded_reason STRING'
    ) AS parsed_result,
    cv.path AS source_file
  FROM cv_texts cv
  CROSS JOIN role_description rd
)
ORDER BY parsed_result.ranking_percentage DESC
"""

# Materialize once to avoid re-calling AI in downstream cells
_ranking_df = spark.sql(_ranking_sql)
ranking_rows = _ranking_df.collect()
ranking_df = spark.createDataFrame(ranking_rows, _ranking_df.schema)
display(ranking_df)
print(f"\nRanked {len(ranking_rows)} candidate(s)")
ranking_df.createOrReplaceTempView("candidate_rankings")

# COMMAND ----------

# DBTITLE 1,Generate technical tests with AI
# Step 4: Generate technical tests for candidates >= MIN_MATCH_THRESHOLD %

_min_pct = config.MIN_MATCH_THRESHOLD
_gen_all = config.GENERATE_TESTS_FOR_ALL_CANDIDATES

if _gen_all:
    _where_clause = ""
    print(f"GENERATE_TESTS_FOR_ALL_CANDIDATES = True \u2192 generating tests for ALL candidates")
else:
    _where_clause = f"WHERE ranking.ranking_percentage >= {_min_pct}"
    print(f"Generating tests only for candidates >= {_min_pct}%")

top_candidates_with_tests_df = spark.sql(f"""
SELECT
  ranking.*,
  from_json(
    ai_query(
      '{config.AI_MODEL}',
      CONCAT(
        'You are a senior technical interviewer creating a screening test for a ', ranking.role, ' position at ', ranking.jd_seniority, ' level.

The job description requires:
', rd.full_text, '

Create exactly 3 realistic technical scenarios to evaluate this candidate. Each scenario should:
- Be appropriate for the seniority level required by the JOB DESCRIPTION (', ranking.jd_seniority, ')
- Test skills relevant to the JOB DESCRIPTION requirements
- Include a detailed problem description (3-4 paragraphs)
- Include a concrete example with specific data/numbers
- End with a challenging question

IMPORTANT \u2014 Technology-agnostic scenarios:
- Do NOT mention specific vendor products or tools by name (e.g. AWS, Azure, Spark, Kafka, Kubernetes)
- Use generic technology categories instead (e.g. "cloud platform", "stream processing engine", "ETL pipeline", "container orchestration", "distributed compute framework", "message broker", "data warehouse")
- The scenarios must test the candidate reasoning and problem-solving ability, not their knowledge of a specific product

IMPORTANT \u2014 Instructions format:
- Do NOT include any time limit or time window (e.g. "60 minutes", "90 minutes") in the instructions or test title
- The instructions MUST tell the candidate to answer clearly and concisely, applying specific technologies they know if applicable, to solve each scenario
- Focus on practical reasoning and problem-solving approach

Return ONLY a valid JSON object with this structure:
{{{{
  "test_title": "<Role> Screening Test",
  "instructions": "Instructions for candidates with 3-4 bullet points",
  "scenarios": [
    {{{{
      "number": 1,
      "title": "Scenario title",
      "description": "Detailed problem description",
      "example": "Concrete example with data",
      "question": "The evaluation question"
    }}}}
  ]
}}}}'
      ),
      responseFormat => 'STRUCT<result:STRUCT<test_title:STRING, instructions:STRING, scenarios:ARRAY<STRUCT<number:INT, title:STRING, description:STRING, example:STRING, question:STRING>>>>'
    ),
    'test_title STRING, instructions STRING, scenarios ARRAY<STRUCT<number:INT, title:STRING, description:STRING, example:STRING, question:STRING>>'
  ) AS technical_test
FROM candidate_rankings ranking
CROSS JOIN role_description rd
{_where_clause}
ORDER BY ranking.ranking_percentage DESC
""")

print(f"Candidates with technical tests generated:")
display(top_candidates_with_tests_df)
print(f"\n{top_candidates_with_tests_df.count()} candidate(s) qualify for technical tests")

# COMMAND ----------

# DBTITLE 1,Generate PDF reports
# ── Generate PDF reports ─────────────────────────────────────────
# Re-import config and utils after pip install
import sys, os
_nb_path = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
_project_dir = f"/Workspace{os.path.dirname(_nb_path)}"
if _project_dir not in sys.path:
    sys.path.insert(0, _project_dir)
for _m in [m for m in sys.modules if m == "config" or m.startswith("utils")]:
    del sys.modules[_m]
import config

from utils.pdf_reports import build_technical_test_pdf, build_ranking_report_pdf

OUTPUT_PATH = config.TECHNICAL_TESTS_OUTPUT_PATH
os.makedirs(OUTPUT_PATH, exist_ok=True)

_logo = getattr(config, "LOGO_PATH", None)

# ── Technical test PDFs ──────────────────────────────────────────
generated = []
candidates = top_candidates_with_tests_df.collect()

for row in candidates:
    cd = row.asDict()
    if cd.get("technical_test") and hasattr(cd["technical_test"], "asDict"):
        cd["technical_test"] = cd["technical_test"].asDict()
    try:
        pdf = build_technical_test_pdf(cd, OUTPUT_PATH, _logo)
        generated.append(cd["name"])
        print(f"\u2713 {pdf}")
    except Exception as e:
        print(f"\u2717 {cd.get('name', '?')}: {e}")
        import traceback; traceback.print_exc()

print(f"\n{'='*60}")
print(f"Generated {len(generated)} technical test PDF(s) \u2192 {OUTPUT_PATH}")

# ── Ranking report PDF ───────────────────────────────────────────
REPORT_PATH = config.EVALUATION_REPORTS_OUTPUT_PATH
os.makedirs(REPORT_PATH, exist_ok=True)

# Names of candidates who got technical tests (for the badge in the report)
_tested_names = set(generated)

report = build_ranking_report_pdf(
    ranking_rows, REPORT_PATH, _logo,
    min_threshold=config.MIN_MATCH_THRESHOLD,
    tested_names=_tested_names,
)
print(f"\u2713 Ranking report \u2192 {report}")