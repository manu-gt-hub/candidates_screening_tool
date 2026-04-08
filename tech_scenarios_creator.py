# Databricks notebook source
# DBTITLE 1,Load configuration
# Load shared configuration (dynamically resolved from notebook location)
import sys, os

_nb_path = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
sys.path.insert(0, f"/Workspace{os.path.dirname(_nb_path)}")
import config

print(f"Configuration loaded:")
print(f"  CVs path:              {config.CVS_PATH}")
print(f"  Role description:      {config.ROLE_DESCRIPTION_LOCAL_PATH}")
print(f"  Technical tests out:   {config.TECHNICAL_TESTS_OUTPUT_PATH}")
print(f"  Logo:                  {config.LOGO_PATH}")
print(f"  AI model:              {config.AI_MODEL}")
print(f"  TOP_X:                 {config.TOP_X}")
print(f"  Job description URL:   {config.JOB_DESCRIPTION_URL or 'Not set (will use local)'}")

# COMMAND ----------

# DBTITLE 1,Parse all CVs from Volume
# Step 1: Parse all CVs (PDFs) and extract full text
spark.sql(f"""
CREATE OR REPLACE TEMPORARY VIEW cv_texts AS
WITH parsed_documents AS (
  SELECT
    path,
    ai_parse_document(
      content,
      map('version', '2.0')
    ) AS parsed
  FROM read_files(
    '{config.CVS_PATH}',
    format => 'binaryFile'
  )
)
SELECT
  path,
  concat_ws('\\n\\n',
    transform(
      try_cast(parsed:document:elements AS ARRAY<VARIANT>),
      element -> try_cast(element:content AS STRING)
    )
  ) AS full_text
FROM parsed_documents
WHERE try_cast(parsed:error_status AS STRING) IS NULL
""")
print(f"\u2713 cv_texts view created from: {config.CVS_PATH}")

# COMMAND ----------

# DBTITLE 1,Load role description
# Step 1b: Load role/job description
# Try fetching from Confluence first; fall back to local file if unavailable
import requests
from bs4 import BeautifulSoup

job_description_text = None

# --- Attempt 1: Confluence URL (only if env var is set) ---
if config.JOB_DESCRIPTION_URL:
    try:
        print(f"Fetching job description from: {config.JOB_DESCRIPTION_URL}")
        resp = requests.get(config.JOB_DESCRIPTION_URL, timeout=15, verify=False)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        content_div = (
            soup.find("div", {"id": "main-content"})
            or soup.find("div", {"class": "wiki-content"})
            or soup.find("article")
            or soup.find("div", {"role": "main"})
        )
        if content_div:
            job_description_text = content_div.get_text(separator="\n", strip=True)
        else:
            job_description_text = soup.get_text(separator="\n", strip=True)

        if len(job_description_text.strip()) < 50:
            raise ValueError("Confluence page content too short, likely not parsed correctly")
        print(f"\u2713 Loaded from Confluence ({len(job_description_text)} chars)")

    except Exception as e:
        print(f"\u2717 Confluence unavailable: {e}")
        job_description_text = None
else:
    print("JOB_DESCRIPTION_URL not set, skipping Confluence fetch")

# --- Attempt 2: Local file fallback ---
if not job_description_text:
    try:
        print(f"Falling back to local file: {config.ROLE_DESCRIPTION_LOCAL_PATH}")
        rows = spark.read.text(config.ROLE_DESCRIPTION_LOCAL_PATH).collect()
        job_description_text = "\n".join([r.value for r in rows])
        print(f"\u2713 Loaded from local file ({len(job_description_text)} chars)")
    except Exception as e:
        raise RuntimeError(f"Could not load job description from any source: {e}")

# --- Create temp view for SQL cells ---
from pyspark.sql import Row
spark.createDataFrame([Row(full_text=job_description_text)]).createOrReplaceTempView("role_description")
print(f"\n\u2713 role_description view created \u2014 preview:\n{job_description_text[:300]}...")

# COMMAND ----------

# DBTITLE 1,Generate candidate ranking with AI analysis
# Step 2: Analyze each CV against the job description and generate candidate ranking
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

CRITICAL \u2014 Mandatory requirements check:
Identify the MANDATORY skills and experience from the job description (e.g. for a Data Engineer: Spark, SQL, Python/Java/Scala, cloud platforms, ETL experience). If the candidate is missing ANY mandatory requirement, set discarded = true and explain why in discarded_reason. Only non-negotiable core skills should trigger a discard \u2014 desirable/nice-to-have skills should NOT.

Return ONLY a valid JSON object with exactly these fields:

- name (string): Full name of the candidate
- ranking_percentage (number): Score 0-100 representing how well the candidate matches the JOB DESCRIPTION
- report_summary (string): 2-3 sentences evaluating the candidate FIT for this specific role
- role (string): The role title from the job description
- seniority (string): One of "Junior", "Mid", "Senior", "Lead", "Principal"
- years_of_experience (integer): Estimated total years of professional experience
- key_technologies (array of strings): All technologies mentioned in the CV
- cv_highlights (array of strings): 3-5 most impressive achievements RELEVANT to this job
- gaps (array of strings): Missing skills or requirements from the JOB DESCRIPTION
- discarded (boolean): true if the candidate fails to meet one or more MANDATORY requirements, false otherwise
- discarded_reason (string or null): If discarded is true, a clear explanation of which mandatory requirements are missing. If discarded is false, null

=== JOB DESCRIPTION ===
',
          rd.full_text,
          '

=== CANDIDATE CV ===
',
          cv.full_text
        ),
        responseFormat => 'STRUCT<result:STRUCT<name:STRING, ranking_percentage:DOUBLE, report_summary:STRING, role:STRING, seniority:STRING, years_of_experience:INT, key_technologies:ARRAY<STRING>, cv_highlights:ARRAY<STRING>, gaps:ARRAY<STRING>, discarded:BOOLEAN, discarded_reason:STRING>>'
      ),
      'name STRING, ranking_percentage DOUBLE, report_summary STRING, role STRING, seniority STRING, years_of_experience INT, key_technologies ARRAY<STRING>, cv_highlights ARRAY<STRING>, gaps ARRAY<STRING>, discarded BOOLEAN, discarded_reason STRING'
    ) AS parsed_result,
    cv.path AS source_file
  FROM cv_texts cv
  CROSS JOIN role_description rd
)
ORDER BY parsed_result.discarded ASC, parsed_result.ranking_percentage DESC
"""

display(spark.sql(_ranking_sql))

# COMMAND ----------

# DBTITLE 1,Configure TOP X candidates parameter
# Configuration loaded from config.py
TOP_X = config.TOP_X

if TOP_X == 0:
    print("TOP_X = 0 → will generate technical tests for ALL non-discarded candidates")
else:
    print(f"Will generate technical tests for TOP {TOP_X} non-discarded candidates")

# COMMAND ----------

# DBTITLE 1,Get TOP X candidates for test generation
# Step 4: Generate technical tests for top X candidates (excluding discarded)
# TOP_X = 0 means all candidates; TOP_X > 0 limits to that number

_limit_clause = f"LIMIT {TOP_X}" if TOP_X > 0 else ""

top_candidates_with_tests_df_non_filtered = spark.sql(f"""
SELECT
  ranking.*,
  from_json(
    ai_query(
      '{config.AI_MODEL}',
      CONCAT(
        'You are a senior technical interviewer at Mercedes-Benz creating a screening test for a ', ranking.role, ' position at ', ranking.seniority, ' level.

The job description requires:
', job_desc, '

Create exactly 3 realistic technical scenarios to evaluate this candidate. Each scenario should:
- Be appropriate for their seniority level (', ranking.seniority, ')
- Test skills relevant to the JOB DESCRIPTION requirements
- Include a detailed problem description (3-4 paragraphs)
- Include a concrete example with specific data/numbers
- End with a challenging question

Candidate technologies: ', array_join(ranking.key_technologies, ', '), '

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
FROM (
  SELECT
    from_json(
      ai_query(
        '{config.AI_MODEL}',
        CONCAT(
          'Evaluate this CV against the JOB DESCRIPTION. Return JSON with: name, ranking_percentage (0-100 match for this role), report_summary, role, seniority (Junior/Mid/Senior/Lead/Principal), years_of_experience, key_technologies (array), cv_highlights (array), gaps (array vs job description), discarded (boolean: true if missing MANDATORY skills like Spark/SQL/Python for a Data Engineer), discarded_reason (string or null).\n\n=== JOB DESCRIPTION ===\n',
          rd.full_text,
          '\n\n=== CANDIDATE CV ===\n',
          cv.full_text
        ),
        responseFormat => 'STRUCT<result:STRUCT<name:STRING, ranking_percentage:DOUBLE, report_summary:STRING, role:STRING, seniority:STRING, years_of_experience:INT, key_technologies:ARRAY<STRING>, cv_highlights:ARRAY<STRING>, gaps:ARRAY<STRING>, discarded:BOOLEAN, discarded_reason:STRING>>'
      ),
      'name STRING, ranking_percentage DOUBLE, report_summary STRING, role STRING, seniority STRING, years_of_experience INT, key_technologies ARRAY<STRING>, cv_highlights ARRAY<STRING>, gaps ARRAY<STRING>, discarded BOOLEAN, discarded_reason STRING'
    ) AS ranking,
    rd.full_text AS job_desc,
    cv.path AS source_file
  FROM cv_texts cv
  CROSS JOIN role_description rd
) all_ranked
ORDER BY ranking.ranking_percentage DESC
{_limit_clause}
""")

_label = f"Top {TOP_X}" if TOP_X > 0 else "All"
print(f"{_label} candidates with technical tests:")
display(top_candidates_with_tests_df_non_filtered)

top_candidates_with_tests_df = top_candidates_with_tests_df_non_filtered.filter("discarded = false")

# COMMAND ----------

# DBTITLE 1,Install PDF generation library
# MAGIC %pip install reportlab --quiet

# COMMAND ----------

# DBTITLE 1,Generate PDF technical tests for each candidate
# Step 5: Generate PDF technical tests for each top candidate
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.lib.colors import HexColor
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_JUSTIFY
import os

OUTPUT_PATH = config.TECHNICAL_TESTS_OUTPUT_PATH
LOGO_PATH = config.LOGO_PATH
os.makedirs(OUTPUT_PATH, exist_ok=True)

# Custom styles
styles = getSampleStyleSheet()

title_style = ParagraphStyle(
    'MainTitle', parent=styles['Heading1'],
    fontSize=18, fontName='Helvetica-Bold', spaceAfter=12, textColor=HexColor('#000000')
)
instructions_style = ParagraphStyle(
    'InstructionsStyle', parent=styles['Normal'],
    fontSize=10, fontName='Helvetica-Oblique', spaceAfter=16, leading=14
)
scenario_title_style = ParagraphStyle(
    'ScenarioTitleStyle', parent=styles['Heading2'],
    fontSize=12, fontName='Helvetica-Bold', spaceBefore=16, spaceAfter=8, textColor=HexColor('#1a1a1a')
)
body_style = ParagraphStyle(
    'BodyStyle', parent=styles['Normal'],
    fontSize=10, fontName='Helvetica', alignment=TA_JUSTIFY, spaceAfter=8, leading=14
)
example_style = ParagraphStyle(
    'ExampleStyle', parent=styles['Normal'],
    fontSize=10, fontName='Helvetica-Oblique', textColor=HexColor('#D4A017'), spaceAfter=8, leading=14
)
question_style = ParagraphStyle(
    'QuestionStyle', parent=styles['Normal'],
    fontSize=10, fontName='Helvetica-Bold', spaceAfter=16, leading=14
)

def create_technical_test_pdf(candidate_data, output_path):
    """Generate a professional PDF technical test for a candidate."""
    name = candidate_data['name']
    role = candidate_data['role']
    seniority = candidate_data['seniority']
    test_data = candidate_data['technical_test']

    safe_name = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).strip()
    filename = f"{output_path}/Technical_Test_{safe_name}.pdf"

    doc = SimpleDocTemplate(
        filename, pagesize=A4,
        rightMargin=2*cm, leftMargin=2*cm, topMargin=2*cm, bottomMargin=2*cm
    )
    usable_width = doc.width
    story = []

    # --- Header: logo only, top-right ---
    logo_img = Image(LOGO_PATH, width=4*cm, height=4*cm, kind='proportional')
    header_table = Table(
        [[logo_img]],
        colWidths=[usable_width]
    )
    header_table.setStyle(TableStyle([
        ('ALIGN', (0, 0), (0, 0), 'RIGHT'),
        ('VALIGN', (0, 0), (0, 0), 'TOP'),
        ('LEFTPADDING', (0, 0), (-1, -1), 0),
        ('RIGHTPADDING', (0, 0), (-1, -1), 0),
        ('TOPPADDING', (0, 0), (-1, -1), 0),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 0),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 0.5*cm))

    # --- Title ---
    test_title = test_data.get('test_title', f"{role} Screening Test") if test_data else f"{role} Screening Test"
    story.append(Paragraph(test_title, title_style))

    # --- Instructions ---
    instructions = test_data.get('instructions', '') if test_data else ''
    if instructions:
        story.append(Paragraph(f"<b>Instructions for candidates:</b> {instructions}", instructions_style))
    else:
        story.append(Paragraph(
            "<b>Instructions for candidates:</b> - Answer each scenario with concise bullet points (max ~10 lines per scenario). "
            "- Use simple, practical language. Focus on actionable reasoning. "
            "- Advanced terminology is not required; explaining ideas clearly is more important.",
            instructions_style
        ))
    story.append(Spacer(1, 0.3*cm))

    # --- Scenarios ---
    scenarios = test_data.get('scenarios', []) if test_data else []
    for i, scenario in enumerate(scenarios, 1):
        if hasattr(scenario, 'asDict'):
            scenario = scenario.asDict()
        scenario_num = scenario.get('number', i)
        scenario_title = scenario.get('title', f'Technical Scenario {i}')
        story.append(Paragraph(f"Scenario {scenario_num} \u2014 {scenario_title}", scenario_title_style))
        description = scenario.get('description', '')
        if description:
            story.append(Paragraph(description, body_style))
        example = scenario.get('example', '')
        if example:
            story.append(Paragraph(f"<b>Example:</b> {example}", example_style))
        question = scenario.get('question', '')
        if question:
            story.append(Paragraph(f"<b>Question:</b> {question}", question_style))
        story.append(Spacer(1, 0.3*cm))

    doc.build(story)
    return filename

# --- Process each top candidate ---
candidates = top_candidates_with_tests_df.collect()
generated_files = []

for row in candidates:
    candidate_data = row.asDict()
    if candidate_data.get('technical_test'):
        test_struct = candidate_data['technical_test']
        if hasattr(test_struct, 'asDict'):
            candidate_data['technical_test'] = test_struct.asDict()
    try:
        pdf_path = create_technical_test_pdf(candidate_data, OUTPUT_PATH)
        generated_files.append({
            'candidate': candidate_data['name'],
            'role': candidate_data['role'],
            'seniority': candidate_data['seniority'],
            'ranking': candidate_data['ranking_percentage'],
            'pdf_path': pdf_path
        })
        print(f"\u2713 Generated: {pdf_path}")
    except Exception as e:
        print(f"\u2717 Error generating PDF for {candidate_data.get('name', 'Unknown')}: {e}")
        import traceback
        traceback.print_exc()

print(f"\n{'='*60}")
print(f"Successfully generated {len(generated_files)} technical test PDFs")
print(f"Output directory: {OUTPUT_PATH}")