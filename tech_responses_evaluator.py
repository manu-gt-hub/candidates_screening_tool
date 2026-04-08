# Databricks notebook source
# DBTITLE 1,Load configuration
# Load shared configuration (dynamically resolved from notebook location)
import sys, os

_nb_path = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
sys.path.insert(0, f"/Workspace{os.path.dirname(_nb_path)}")
import config

print(f"Configuration loaded:")
print(f"  Role description:        {config.ROLE_DESCRIPTION_LOCAL_PATH}")
print(f"  Technical responses:     {config.TECHNICAL_RESPONSES_PATH}")
print(f"  Evaluation reports out:  {config.EVALUATION_REPORTS_OUTPUT_PATH}")
print(f"  AI model:                {config.AI_MODEL}")
print(f"  Job description URL:     {config.JOB_DESCRIPTION_URL or 'Not set (will use local)'}")

# COMMAND ----------

# DBTITLE 1,Parse role description
# Step 1: Load role/job description
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
print(f"\n\u2713 role_description view created")

# COMMAND ----------

# DBTITLE 1,Parse all technical response PDFs
# Step 2: Parse all technical response PDFs and extract text
spark.sql(f"""
CREATE OR REPLACE TEMPORARY VIEW response_texts AS
WITH parsed_responses AS (
  SELECT
    path,
    ai_parse_document(
      content,
      map('version', '2.0')
    ) AS parsed
  FROM read_files(
    '{config.TECHNICAL_RESPONSES_PATH}',
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
FROM parsed_responses
WHERE try_cast(parsed:error_status AS STRING) IS NULL
""")
print(f"\u2713 response_texts view created from: {config.TECHNICAL_RESPONSES_PATH}")

# COMMAND ----------

# DBTITLE 1,Evaluate technical responses with AI
# Step 3: Evaluate each technical response against the role description

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
          'You are an expert technical evaluator for Mercedes-Benz. You must evaluate a candidate technical test response against the role description provided.

Evaluate the quality, depth, and correctness of their answers to each scenario. Consider:
- Technical accuracy and understanding of the problem
- Practicality and feasibility of proposed solutions
- Alignment with the role requirements (technologies, seniority level, responsibilities)
- Problem-solving approach and critical thinking
- Communication clarity

Return ONLY a valid JSON object with these fields:
- candidate_name (string): Name of the candidate (infer from the document or filename)
- match_percentage (number): Overall match score 0-100 for the role
- suitability_assessment (string): 3-4 sentences on overall suitability for the role
- highlights (array of strings): 3-5 standout positive aspects of the responses
- strengths (array of strings): 4-6 technical and soft skill strengths demonstrated
- weaknesses (array of strings): 3-5 areas of concern or weakness identified
- scenario_evaluations (array of objects): Per-scenario evaluation, each with:
  - scenario_number (integer)
  - scenario_title (string)
  - score (number): 0-100
  - feedback (string): 2-3 sentences of specific feedback
- overall_recommendation (string): One of "Strong Hire", "Hire", "Lean Hire", "Lean No Hire", "No Hire"
- improvement_areas (array of strings): 3-4 specific suggestions for the candidate

=== ROLE DESCRIPTION ===
',
          rd.full_text,
          '

=== CANDIDATE TECHNICAL RESPONSE ===
',
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

# DBTITLE 1,Install PDF library
# MAGIC %pip install reportlab --quiet

# COMMAND ----------

# DBTITLE 1,Generate PDF evaluation reports
# Step 4: Generate PDF evaluation reports per candidate
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib.colors import HexColor, Color
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether
)
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_JUSTIFY, TA_CENTER
from reportlab.lib import colors
import os

OUTPUT_PATH = config.EVALUATION_REPORTS_OUTPUT_PATH
os.makedirs(OUTPUT_PATH, exist_ok=True)

# ── Styles ──────────────────────────────────────────────────
base = getSampleStyleSheet()

S = {}
S['company'] = ParagraphStyle('Co', parent=base['Normal'], fontSize=14, fontName='Helvetica-Bold', alignment=TA_RIGHT, spaceAfter=6)
S['title'] = ParagraphStyle('Ti', parent=base['Heading1'], fontSize=18, fontName='Helvetica-Bold', spaceAfter=4, textColor=HexColor('#000000'))
S['subtitle'] = ParagraphStyle('Su', parent=base['Normal'], fontSize=12, fontName='Helvetica-Bold', textColor=HexColor('#333333'), spaceAfter=12)
S['section'] = ParagraphStyle('Se', parent=base['Heading2'], fontSize=13, fontName='Helvetica-Bold', spaceBefore=14, spaceAfter=6, textColor=HexColor('#1a1a1a'))
S['body'] = ParagraphStyle('Bo', parent=base['Normal'], fontSize=10, fontName='Helvetica', alignment=TA_JUSTIFY, spaceAfter=6, leading=14)
S['bullet'] = ParagraphStyle('Bu', parent=base['Normal'], fontSize=10, fontName='Helvetica', leftIndent=18, spaceAfter=4, leading=13, bulletIndent=6)
S['score_high'] = ParagraphStyle('Sh', parent=base['Normal'], fontSize=28, fontName='Helvetica-Bold', alignment=TA_CENTER, textColor=HexColor('#2E7D32'))
S['score_mid'] = ParagraphStyle('Sm', parent=base['Normal'], fontSize=28, fontName='Helvetica-Bold', alignment=TA_CENTER, textColor=HexColor('#F57F17'))
S['score_low'] = ParagraphStyle('Sl', parent=base['Normal'], fontSize=28, fontName='Helvetica-Bold', alignment=TA_CENTER, textColor=HexColor('#C62828'))
S['rec_pos'] = ParagraphStyle('Rp', parent=base['Normal'], fontSize=14, fontName='Helvetica-Bold', alignment=TA_CENTER, textColor=HexColor('#2E7D32'), spaceBefore=4)
S['rec_neg'] = ParagraphStyle('Rn', parent=base['Normal'], fontSize=14, fontName='Helvetica-Bold', alignment=TA_CENTER, textColor=HexColor('#C62828'), spaceBefore=4)
S['rec_neu'] = ParagraphStyle('Rne', parent=base['Normal'], fontSize=14, fontName='Helvetica-Bold', alignment=TA_CENTER, textColor=HexColor('#F57F17'), spaceBefore=4)
S['scenario_title'] = ParagraphStyle('St', parent=base['Heading3'], fontSize=11, fontName='Helvetica-Bold', spaceBefore=10, spaceAfter=4, textColor=HexColor('#1a1a1a'))
S['feedback'] = ParagraphStyle('Fb', parent=base['Normal'], fontSize=10, fontName='Helvetica-Oblique', spaceAfter=6, leading=13, textColor=HexColor('#444444'))

def score_style(score):
    if score >= 70: return S['score_high']
    elif score >= 50: return S['score_mid']
    else: return S['score_low']

def rec_style(rec):
    if rec in ('Strong Hire', 'Hire'): return S['rec_pos']
    elif rec in ('No Hire', 'Lean No Hire'): return S['rec_neg']
    else: return S['rec_neu']

def build_evaluation_pdf(ev, output_path):
    name = ev.get('candidate_name', 'Unknown')
    safe = "".join(c for c in name if c.isalnum() or c in (' ', '-', '_')).strip()
    fpath = f"{output_path}/Evaluation_Report_{safe}.pdf"

    doc = SimpleDocTemplate(fpath, pagesize=A4,
                            rightMargin=2*cm, leftMargin=2*cm,
                            topMargin=2*cm, bottomMargin=2*cm)
    story = []

    # Header
    story.append(Paragraph("Mercedes-Benz", S['company']))
    story.append(Spacer(1, 0.3*cm))
    story.append(Paragraph("Technical Response Evaluation Report", S['title']))
    story.append(Paragraph(f"Candidate: {name}", S['subtitle']))
    story.append(HRFlowable(width="100%", thickness=1, color=HexColor('#cccccc')))
    story.append(Spacer(1, 0.4*cm))

    # ── Match score card ───────────────────────────────────
    match_pct = ev.get('match_percentage', 0) or 0
    recommendation = ev.get('overall_recommendation', 'N/A') or 'N/A'

    score_para = Paragraph(f"{match_pct:.0f}%", score_style(match_pct))
    label_para = Paragraph("Role Match", ParagraphStyle('lbl', parent=base['Normal'], alignment=TA_CENTER, fontSize=9, textColor=HexColor('#666666')))
    rec_para = Paragraph(recommendation, rec_style(recommendation))

    card = Table(
        [[score_para, rec_para],
         [label_para, Paragraph("Recommendation", ParagraphStyle('lbl2', parent=base['Normal'], alignment=TA_CENTER, fontSize=9, textColor=HexColor('#666666')))]],
        colWidths=[doc.width/2]*2, rowHeights=[45, 18]
    )
    card.setStyle(TableStyle([
        ('BOX', (0,0), (-1,-1), 1, HexColor('#dddddd')),
        ('LINEAFTER', (0,0), (0,-1), 0.5, HexColor('#dddddd')),
        ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ('BACKGROUND', (0,0), (-1,-1), HexColor('#f9f9f9')),
        ('TOPPADDING', (0,0), (-1,0), 8),
    ]))
    story.append(card)
    story.append(Spacer(1, 0.5*cm))

    # ── Suitability assessment ─────────────────────────────
    story.append(Paragraph("Suitability Assessment", S['section']))
    story.append(Paragraph(ev.get('suitability_assessment', ''), S['body']))

    # ── Highlights ─────────────────────────────────────────
    highlights = ev.get('highlights', []) or []
    if highlights:
        story.append(Paragraph("Key Highlights", S['section']))
        for h in highlights:
            story.append(Paragraph(f"\u2022 {h}", S['bullet']))

    # ── Scenario evaluations ───────────────────────────────
    scenarios = ev.get('scenario_evaluations', []) or []
    if scenarios:
        story.append(Paragraph("Scenario-by-Scenario Evaluation", S['section']))
        for sc in scenarios:
            if hasattr(sc, 'asDict'):
                sc = sc.asDict()
            num = sc.get('scenario_number', '?')
            title = sc.get('scenario_title', '')
            sc_score = sc.get('score', 0) or 0
            fb = sc.get('feedback', '')

            color_hex = '#2E7D32' if sc_score >= 70 else '#F57F17' if sc_score >= 50 else '#C62828'
            story.append(Paragraph(
                f"Scenario {num} \u2014 {title}  "
                f"<font color='{color_hex}'><b>[{sc_score:.0f}/100]</b></font>",
                S['scenario_title']
            ))
            story.append(Paragraph(fb, S['feedback']))

    # ── Strengths ──────────────────────────────────────────
    strengths = ev.get('strengths', []) or []
    if strengths:
        story.append(Paragraph("Strengths", S['section']))
        for s in strengths:
            story.append(Paragraph(f"\u2713 {s}", S['bullet']))

    # ── Weaknesses ─────────────────────────────────────────
    weaknesses = ev.get('weaknesses', []) or []
    if weaknesses:
        story.append(Paragraph("Weaknesses", S['section']))
        for w in weaknesses:
            story.append(Paragraph(f"\u2717 {w}", S['bullet']))

    # ── Improvement areas ──────────────────────────────────
    improvements = ev.get('improvement_areas', []) or []
    if improvements:
        story.append(Paragraph("Areas for Improvement", S['section']))
        for imp in improvements:
            story.append(Paragraph(f"\u2192 {imp}", S['bullet']))

    doc.build(story)
    return fpath

# ── Process all evaluations (using pre-collected rows from cell 3) ──
generated = []

for row in evaluation_rows:
    ev = row.asDict()
    response_file = ev.pop('response_file', '')
    try:
        pdf = build_evaluation_pdf(ev, OUTPUT_PATH)
        generated.append({
            'candidate': ev.get('candidate_name'),
            'match': ev.get('match_percentage'),
            'recommendation': ev.get('overall_recommendation'),
            'pdf': pdf
        })
        print(f"\u2713 Generated: {pdf}")
    except Exception as e:
        print(f"\u2717 Error for {ev.get('candidate_name', '?')}: {e}")
        import traceback; traceback.print_exc()

print(f"\n{'='*60}")
print(f"Generated {len(generated)} evaluation report(s)")
print(f"Output: {OUTPUT_PATH}")