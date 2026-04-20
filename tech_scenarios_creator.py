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
# Prompt text comes from utils/prompts.py — single source of truth for both modes.
from utils.prompts import build_ranking_prompt_parts, sql_esc

_min_interview = config.MIN_MATCH_THRESHOLD
_tech_ctx = getattr(config, "TECHNICAL_CONTEXT", "") or ""
print(f"Minimum match for technical test: {_min_interview}%")
if _tech_ctx:
    print(f"Business context: {_tech_ctx}")

_rk_prefix, _rk_sep, _ = build_ranking_prompt_parts(tech_context=_tech_ctx or None)
_model_sql = sql_esc(config.AI_MODEL)

_ranking_sql = f"""
SELECT
  parsed_result.*,
  source_file
FROM (
  SELECT
    from_json(
      ai_query(
        '{_model_sql}',
        CONCAT(
          '{sql_esc(_rk_prefix)}',
          rd.full_text,
          '{sql_esc(_rk_sep)}',
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
#         Prompt text comes from utils/prompts.py — single source of truth.

from utils.topic_pools import get_topics
from utils.prompts import build_test_prompt_parts

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

# Generate one test per candidate, each with unique topics from the pool
_test_results = []
for variant_num, row in enumerate(_candidate_rows, start=1):
    topics = get_topics(variant_num, role=_jd_role)
    topic_str = ", ".join(topics)

    print(f"  Variant {variant_num}: {row['name']}  \u2192  [{topic_str}]")

    _tp_prefix, _tp_suffix = build_test_prompt_parts(
        topics=topics, tech_context=_tech_ctx or None
    )

    _test_df = spark.sql(f"""
    SELECT from_json(
      ai_query(
        '{_model_sql}',
        CONCAT(
          '{sql_esc(_tp_prefix)}',
          rd.full_text,
          '{sql_esc(_tp_suffix)}'
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
_combined_rows = []
for row, test in _test_results:
    d = row.asDict()
    d["technical_test"] = test
    _combined_rows.append(d)

if _combined_rows:
    top_candidates_with_tests_df = spark.createDataFrame(
        _combined_rows, _candidates_df.schema.add("technical_test", _test_df.schema["technical_test"].dataType)
    )
else:
    top_candidates_with_tests_df = spark.createDataFrame([], _candidates_df.schema)

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
