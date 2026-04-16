"""Prompt templates for the candidate evaluation pipeline.

Each ``build_*_prompt`` function returns a fully-formed prompt string ready to
send to any LLM (used by ``pipeline.py`` in local mode).

Each ``build_*_prompt_parts`` function returns a tuple of prompt fragments
split at the data-injection points so that Databricks notebooks can embed
them inside ``CONCAT(...)`` SQL expressions together with Spark column
references.  This keeps prompt text in **one place** for both modes.
"""


# ── Ranking prompt ────────────────────────────────────────────────────

def _ranking_ctx_block(tech_context):
    """Return the optional business-context paragraph for ranking."""
    if not tech_context:
        return ""
    return (
        f"BUSINESS CONTEXT: This role operates within the {tech_context} domain. "
        f"Evaluate the candidate's fit considering this specific business context "
        f"\u2014 prioritise experience and skills relevant to {tech_context}.\n\n"
    )


_RANKING_PREAMBLE = (
    "You are an expert HR analyst and technical recruiter. "
    "Evaluate the following CV/resume against the provided JOB DESCRIPTION. "
    "The ranking must reflect how well the candidate matches the specific role requirements.\n\n"
    "Return ONLY a valid JSON object with exactly these fields:\n\n"
    "- name (string): Full name of the candidate\n"
    "- ranking_percentage (number): Score 0-100 representing how well the candidate matches the JOB DESCRIPTION\n"
    "- report_summary (string): 2-3 sentences evaluating the candidate FIT for this specific role\n"
    "- candidate_role (string): The candidate's current or most recent role title extracted from the CV\n"
    '- candidate_seniority (string): The candidate\'s actual seniority level based on their professional experience. One of "Junior", "Mid", "Senior", "Lead", "Principal"\n'
    "- jd_role (string): The role title as stated in the JOB DESCRIPTION (not the candidate's role)\n"
    '- jd_seniority (string): The seniority level REQUIRED by the JOB DESCRIPTION (not the candidate\'s level). One of "Junior", "Mid", "Senior", "Lead", "Principal"\n'
    "- years_of_experience (integer): Estimated total years of professional experience\n"
    "- key_technologies (array of strings): All technologies mentioned in the CV\n"
    "- cv_highlights (array of strings): 3-5 most impressive achievements RELEVANT to this job\n"
    "- gaps (array of strings): Missing skills or requirements from the JOB DESCRIPTION\n"
    "- discarded (boolean): ALWAYS set to false\n"
    "- discarded_reason (string or null): ALWAYS set to null\n\n"
)

_RANKING_JD_HEADER = "=== JOB DESCRIPTION ===\n"
_RANKING_CV_HEADER = "\n\n=== CANDIDATE CV ===\n"


def build_ranking_prompt_parts(tech_context=None):
    """Return ``(prefix, jd_cv_separator, suffix)`` for the ranking prompt.

    Usage in Databricks SQL::

        prefix, sep, suffix = build_ranking_prompt_parts(tech_context)
        CONCAT('{prefix}', rd.full_text, '{sep}', cv.full_text, '{suffix}')

    The local ``build_ranking_prompt`` composes the same parts with actual text.
    """
    ctx = _ranking_ctx_block(tech_context)
    prefix = _RANKING_PREAMBLE + ctx + _RANKING_JD_HEADER
    separator = _RANKING_CV_HEADER
    suffix = ""
    return prefix, separator, suffix


def build_ranking_prompt(cv_text, jd_text, tech_context=None):
    """Build the prompt to rank a single CV against a job description.

    Args:
        cv_text:      Full text extracted from the candidate's CV.
        jd_text:      Full job description text.
        tech_context: Optional business domain (e.g. "e-commerce logistics").
                      When set, the ranking considers domain-specific fit.
    """
    prefix, separator, suffix = build_ranking_prompt_parts(tech_context)
    return f"{prefix}{jd_text}{separator}{cv_text}{suffix}"


# ── Test generation prompt ────────────────────────────────────────────

def _test_ctx_block(tech_context):
    """Return the optional business-context paragraph for test generation."""
    if not tech_context:
        return ""
    return (
        f"\nBUSINESS CONTEXT: The role is within the {tech_context} domain. "
        f"Scenarios MUST be set in this specific business context.\n"
    )


def _test_topic_block(topics):
    """Return the mandatory-topic-assignment block, or empty string."""
    if not topics:
        return ""
    numbered = "\n".join(f"  Scenario {i+1}: {t}" for i, t in enumerate(topics))
    return (
        "\nCRITICAL \u2014 Mandatory topic assignment:\n"
        "Each scenario MUST focus on its assigned topic below. "
        "Do NOT swap, merge, or skip topics.\n"
        f"{numbered}\n"
    )


_TEST_INTRO = (
    "You are a senior technical interviewer creating a screening test.\n"
)

_TEST_JD_INTRO = (
    "\nRead the following JOB DESCRIPTION carefully. From it, determine the "
    "role title and seniority level required. Then create exactly 3 realistic "
    "technical scenarios appropriate for that role and seniority.\n\n"
    "=== JOB DESCRIPTION ===\n"
)

_TEST_BODY = (
    "\nEach scenario should:\n"
    "- Be appropriate for the seniority level described in the JOB DESCRIPTION\n"
    "- Test skills and responsibilities mentioned in the JOB DESCRIPTION\n"
    "- Focus specifically on the assigned topic\n"
    "- Include a concise problem description (1 short paragraph, max 80 words)\n"
    "- Include a brief concrete example with specific numbers (max 60 words)\n"
    "- End with one direct, challenging question (1-2 sentences)\n\n"
    "IMPORTANT \u2014 Technology-agnostic scenarios:\n"
    "- Do NOT mention specific vendor products or tools by name "
    "(e.g. AWS, Azure, Spark, Kafka, Kubernetes)\n"
    "- Use generic technology categories instead "
    '(e.g. "cloud platform", "stream processing engine", "ETL pipeline", '
    '"container orchestration", "distributed compute framework", '
    '"message broker", "data warehouse")\n'
    "- The scenarios must test the candidate reasoning and problem-solving ability, "
    "not their knowledge of a specific product\n\n"
    "IMPORTANT \u2014 Instructions format:\n"
    '- Do NOT include any time limit or time window (e.g. "60 minutes", '
    '"90 minutes") in the instructions or test title\n'
    "- The instructions MUST tell the candidate to answer clearly and concisely, "
    "applying specific technologies they know if applicable, to solve each scenario\n"
    "- Focus on practical reasoning and problem-solving approach\n\n"
    "IMPORTANT \u2014 Brevity: The entire test with 3 scenarios must fit on 2 printed "
    "A4 pages. Be concise and direct. Avoid verbose introductions or unnecessary context.\n\n"
    "Return ONLY a valid JSON object with this structure:\n"
    "{\n"
    '  "test_title": "<Role> Screening Test",\n'
    '  "instructions": "Instructions for candidates with 2-3 short bullet points",\n'
    '  "scenarios": [\n'
    "    {\n"
    '      "number": 1,\n'
    '      "title": "Scenario title",\n'
    '      "description": "Concise problem description",\n'
    '      "example": "Brief example with data",\n'
    '      "question": "The evaluation question"\n'
    "    }\n"
    "  ]\n"
    "}"
)


def build_test_prompt_parts(topics=None, tech_context=None):
    """Return ``(prefix, suffix)`` for the test-generation prompt.

    Usage in Databricks SQL::

        prefix, suffix = build_test_prompt_parts(topics, tech_context)
        CONCAT('{prefix}', rd.full_text, '{suffix}')
    """
    ctx = _test_ctx_block(tech_context)
    topic_block = _test_topic_block(topics)
    prefix = _TEST_INTRO + ctx + _TEST_JD_INTRO
    suffix = topic_block + _TEST_BODY
    return prefix, suffix


def build_test_prompt(jd_text, topics=None, tech_context=None):
    """Build the prompt to generate 3 technical scenarios from the JD.

    Args:
        jd_text:      Full job description text.
        topics:       Optional list of 3 topic strings (from ``topic_pools.get_topics``).
                      When provided, each scenario MUST cover one topic.
        tech_context: Optional business context string.
    """
    prefix, suffix = build_test_prompt_parts(topics, tech_context)
    return f"{prefix}{jd_text}{suffix}"


# ── Evaluation prompt ─────────────────────────────────────────────────

_EVAL_PREAMBLE = (
    "You are an expert technical evaluator. You must evaluate a candidate "
    "technical test response against the role description provided.\n\n"
    "Evaluate the quality, depth, and correctness of their answers to each scenario. Consider:\n"
    "- Technical accuracy and understanding of the problem\n"
    "- Practicality and feasibility of proposed solutions\n"
    "- Alignment with the role requirements (technologies, seniority level, responsibilities)\n"
    "- Problem-solving approach and critical thinking\n"
    "- Communication clarity\n\n"
    "Return ONLY a valid JSON object with these fields:\n"
    "- candidate_name (string): Name of the candidate (infer from the document or filename)\n"
    "- match_percentage (number): Overall match score 0-100 for the role\n"
    "- suitability_assessment (string): 3-4 sentences on overall suitability for the role\n"
    "- highlights (array of strings): 3-5 standout positive aspects of the responses\n"
    "- strengths (array of strings): 4-6 technical and soft skill strengths demonstrated\n"
    "- weaknesses (array of strings): 3-5 areas of concern or weakness identified\n"
    "- scenario_evaluations (array of objects): Per-scenario evaluation, each with:\n"
    "  - scenario_number (integer)\n"
    "  - scenario_title (string)\n"
    "  - score (number): 0-100\n"
    "  - feedback (string): 2-3 sentences of specific feedback\n"
    '- overall_recommendation (string): One of "Strong Hire", "Hire", '
    '"Lean Hire", "Lean No Hire", "No Hire"\n'
    "- improvement_areas (array of strings): 3-4 specific suggestions for the candidate\n\n"
    "=== ROLE DESCRIPTION ===\n"
)

_EVAL_RESPONSE_HEADER = "\n\n=== CANDIDATE TECHNICAL RESPONSE ===\n"


def build_evaluation_prompt_parts():
    """Return ``(prefix, separator, suffix)`` for the evaluation prompt.

    Usage in Databricks SQL::

        prefix, sep, suffix = build_evaluation_prompt_parts()
        CONCAT('{prefix}', rd.full_text, '{sep}', r.full_text, '{suffix}')
    """
    return _EVAL_PREAMBLE, _EVAL_RESPONSE_HEADER, ""


def build_evaluation_prompt(response_text, jd_text):
    """Build the prompt to evaluate a candidate's technical response."""
    prefix, separator, suffix = build_evaluation_prompt_parts()
    return f"{prefix}{jd_text}{separator}{response_text}{suffix}"
