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
_ctx = getattr(config, "TECHNICAL_CONTEXT", "") or ""
print(f"  Tech context:  {_ctx if _ctx else '(none)'}")


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
_tech_ctx = getattr(config, "TECHNICAL_CONTEXT", "") or ""
print(f"Minimum match for technical test: {_min_interview}%")
if _tech_ctx:
    print(f"Business context: {_tech_ctx}")

_ctx_ranking = ""
if _tech_ctx:
    _ctx_ranking = f"BUSINESS CONTEXT: This role operates within the {_tech_ctx} domain. Evaluate the candidate''s fit considering this specific business context \u2014 prioritise experience and skills relevant to {_tech_ctx}.\n\n"

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
- candidate_role (string): The candidate''s current or most recent role title extracted from the CV
- candidate_seniority (string): The candidate''s actual seniority level based on their professional experience. One of "Junior", "Mid", "Senior", "Lead", "Principal"
- jd_role (string): The role title as stated in the JOB DESCRIPTION (not the candidate''s role)
- jd_seniority (string): The seniority level REQUIRED by the JOB DESCRIPTION (not the candidate''s level). One of "Junior", "Mid", "Senior", "Lead", "Principal"
- years_of_experience (integer): Estimated total years of professional experience
- key_technologies (array of strings): All technologies mentioned in the CV
- cv_highlights (array of strings): 3-5 most impressive achievements RELEVANT to this job
- gaps (array of strings): Missing skills or requirements from the JOB DESCRIPTION
- discarded (boolean): ALWAYS set to false
- discarded_reason (string or null): ALWAYS set to null

{_ctx_ranking}=== JOB DESCRIPTION ===
',
          rd.full_text,
          '

=== CANDIDATE CV ===
',
          cv.full_text
        ),
        responseFormat => 'STRUCT<result:STRUCT<name:STRING, ranking_percentage:DOUBLE, report_summary:STRING, candidate_role:STRING, candidate_seniority:STRING, jd_role:STRING, jd_seniority:STRING, years_of_experience:INT, key_technologies:ARRAY<STRING>, cv_highlights:ARRAY<STRING>, gaps:ARRAY<STRING>, discarded:BOOLEAN, discarded_reason:STRING>>'
      ),
      'name STRING, ranking_percentage DOUBLE, report_summary STRING, candidate_role STRING, candidate_seniority STRING, jd_role STRING, jd_seniority STRING, years_of_experience INT, key_technologies ARRAY<STRING>, cv_highlights ARRAY<STRING>, gaps ARRAY<STRING>, discarded BOOLEAN, discarded_reason STRING'
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
# Step 4: Generate UNIQUE technical tests per candidate, based on the JOB DESCRIPTION.
#         Topics rotate from utils/topic_pools.py so each candidate receives
#         a different set of 3 technical themes.

from utils.topic_pools import get_topics

_min_pct = config.MIN_MATCH_THRESHOLD
_gen_all = config.GENERATE_TESTS_FOR_ALL_CANDIDATES
_tech_ctx = getattr(config, "TECHNICAL_CONTEXT", "") or ""

if _gen_all:
    _where_clause = ""
    print(f"GENERATE_TESTS_FOR_ALL_CANDIDATES = True \u2192 generating tests for ALL candidates")
else:
    _where_clause = f"WHERE ranking_percentage >= {_min_pct}"
    print(f"Generating tests only for candidates >= {_min_pct}%")

# Get qualifying candidates from the materialized ranking view
_candidates_df = spark.sql(f"""
  SELECT * FROM candidate_rankings
  {_where_clause}
  ORDER BY ranking_percentage DESC
""")
_candidate_rows = _candidates_df.collect()
print(f"\n{len(_candidate_rows)} candidate(s) qualify for technical tests")

# Determine the JD role for topic pool selection
_jd_role = _candidate_rows[0]["jd_role"] if _candidate_rows else None
print(f"JD role detected: {_jd_role}  \u2192  topic pool selected")

_ctx_sql = ""
if _tech_ctx:
    _ctx_sql = f"\nBUSINESS CONTEXT: The role is within the {_tech_ctx} domain. Scenarios MUST be set in this specific business context.\n"

# Generate one test per candidate, each with unique topics from the pool
_test_results = []
for variant_num, row in enumerate(_candidate_rows, start=1):
    topics = get_topics(variant_num, role=_jd_role)
    topic_lines = "\n".join(f"  Scenario {i+1}: {t}" for i, t in enumerate(topics))
    topic_str = ", ".join(topics)

    print(f"  Variant {variant_num}: {row['name']}  \u2192  [{topic_str}]")

    _test_df = spark.sql(f"""
    SELECT from_json(
      ai_query(
        '{config.AI_MODEL}',
        CONCAT(
          'You are a senior technical interviewer creating a screening test.
{_ctx_sql}
Read the following JOB DESCRIPTION carefully. From it, determine the role title and seniority level required. Then create exactly 3 realistic technical scenarios appropriate for that role and seniority.

=== JOB DESCRIPTION ===
', rd.full_text, '

CRITICAL \u2014 Mandatory topic assignment:
Each scenario MUST focus on its assigned topic below. Do NOT swap, merge, or skip topics.
{topic_lines}

Each scenario should:
- Be appropriate for the seniority level described in the JOB DESCRIPTION
- Test skills and responsibilities mentioned in the JOB DESCRIPTION
- Focus specifically on the assigned topic
- Include a concise problem description (1 short paragraph, max 80 words)
- Include a brief concrete example with specific numbers (max 60 words)
- End with one direct, challenging question (1-2 sentences)

IMPORTANT \u2014 Technology-agnostic scenarios:
- Do NOT mention specific vendor products or tools by name (e.g. AWS, Azure, Spark, Kafka, Kubernetes)
- Use generic technology categories instead (e.g. "cloud platform", "stream processing engine", "ETL pipeline", "container orchestration", "distributed compute framework", "message broker", "data warehouse")
- The scenarios must test the candidate reasoning and problem-solving ability, not their knowledge of a specific product

IMPORTANT \u2014 Instructions format:
- Do NOT include any time limit or time window (e.g. "60 minutes", "90 minutes") in the instructions or test title
- The instructions MUST tell the candidate to answer clearly and concisely, applying specific technologies they know if applicable, to solve each scenario
- Focus on practical reasoning and problem-solving approach

IMPORTANT \u2014 Brevity: The entire test with 3 scenarios must fit on 2 printed A4 pages. Be concise and direct. Avoid verbose introductions or unnecessary context.

Return ONLY a valid JSON object with this structure:
{{{{{{
  "test_title": "<Role> Screening Test",
  "instructions": "Instructions for candidates with 2-3 short bullet points",
  "scenarios": [
    {{{{{{
      "number": 1,
      "title": "Scenario title",
      "description": "Concise problem description",
      "example": "Brief example with data",
      "question": "The evaluation question"
    }}}}}}
  ]
}}}}}}'
        ),
        responseFormat => 'STRUCT<result:STRUCT<test_title:STRING, instructions:STRING, scenarios:ARRAY<STRUCT<number:INT, title:STRING, description:STRING, example:STRING, question:STRING>>>>'
      ),
      'test_title STRING, instructions STRING, scenarios ARRAY<STRUCT<number:INT, title:STRING, description:STRING, example:STRING, question:STRING>>'
    ) AS technical_test
    FROM role_description rd
    """)
    _test_results.append((row, _test_df.collect()[0]["technical_test"]))
    print(f"    \u2713 done")

# Combine ranking data + generated tests into a single DataFrame
from pyspark.sql import Row as _Row

_combined_rows = []
for row, test in _test_results:
    d = row.asDict()
    d["technical_test"] = test
    _combined_rows.append(d)

top_candidates_with_tests_df = spark.createDataFrame(
    _combined_rows, _candidates_df.schema.add("technical_test", _test_df.schema["technical_test"].dataType)
)

print(f"\nCandidates with technical tests generated:")
display(top_candidates_with_tests_df)
print(f"\n{len(_combined_rows)} candidate(s) with unique technical tests (topics from pool)")

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
    [r.asDict(recursive=True) for r in ranking_rows], REPORT_PATH, _logo,
    min_threshold=config.MIN_MATCH_THRESHOLD,
    tested_names=_tested_names,
)
print(f"\u2713 Ranking report \u2192 {report}")