"""Prompt templates for the candidate evaluation pipeline.

Each function returns a fully-formed prompt string ready to send to any LLM.
"""


def build_ranking_prompt(cv_text, jd_text):
    """Build the prompt to rank a single CV against a job description."""
    return (
        "You are an expert HR analyst and technical recruiter. "
        "Evaluate the following CV/resume against the provided JOB DESCRIPTION. "
        "The ranking must reflect how well the candidate matches the specific role requirements.\n\n"
        "Return ONLY a valid JSON object with exactly these fields:\n\n"
        "- name (string): Full name of the candidate\n"
        "- ranking_percentage (number): Score 0-100 representing how well the candidate matches the JOB DESCRIPTION\n"
        "- report_summary (string): 2-3 sentences evaluating the candidate FIT for this specific role\n"
        "- role (string): The role title from the job description\n"
        '- seniority (string): The candidate\'s actual seniority level based on their professional experience. One of "Junior", "Mid", "Senior", "Lead", "Principal"\n'
        '- jd_seniority (string): The seniority level REQUIRED by the JOB DESCRIPTION (not the candidate\'s level). One of "Junior", "Mid", "Senior", "Lead", "Principal"\n'
        "- years_of_experience (integer): Estimated total years of professional experience\n"
        "- key_technologies (array of strings): All technologies mentioned in the CV\n"
        "- cv_highlights (array of strings): 3-5 most impressive achievements RELEVANT to this job\n"
        "- gaps (array of strings): Missing skills or requirements from the JOB DESCRIPTION\n"
        "- discarded (boolean): ALWAYS set to false\n"
        "- discarded_reason (string or null): ALWAYS set to null\n\n"
        f"=== JOB DESCRIPTION ===\n{jd_text}\n\n"
        f"=== CANDIDATE CV ===\n{cv_text}"
    )


def build_test_prompt(role, jd_seniority, jd_text):
    """Build the prompt to generate 3 technical scenarios."""
    return (
        f"You are a senior technical interviewer creating a screening test "
        f"for a {role} position at {jd_seniority} level.\n\n"
        f"The job description requires:\n{jd_text}\n\n"
        f"Create exactly 3 realistic technical scenarios to evaluate this candidate. "
        f"Each scenario should:\n"
        f"- Be appropriate for the seniority level required by the JOB DESCRIPTION ({jd_seniority})\n"
        "- Test skills relevant to the JOB DESCRIPTION requirements\n"
        "- Include a detailed problem description (3-4 paragraphs)\n"
        "- Include a concrete example with specific data/numbers\n"
        "- End with a challenging question\n\n"
        "IMPORTANT \u2014 Technology-agnostic scenarios:\n"
        "- Do NOT mention specific vendor products or tools by name "
        "(e.g. AWS, Azure, Spark, Kafka, Kubernetes)\n"
        "- Use generic technology categories instead "
        '(e.g. \"cloud platform\", \"stream processing engine\", \"ETL pipeline\", '
        '\"container orchestration\", \"distributed compute framework\", '
        '\"message broker\", \"data warehouse\")\n'
        "- The scenarios must test the candidate reasoning and problem-solving ability, "
        "not their knowledge of a specific product\n\n"
        "IMPORTANT \u2014 Instructions format:\n"
        '- Do NOT include any time limit or time window (e.g. \"60 minutes\", '
        '\"90 minutes\") in the instructions or test title\n'
        "- The instructions MUST tell the candidate to answer clearly and concisely, "
        "applying specific technologies they know if applicable, to solve each scenario\n"
        "- Focus on practical reasoning and problem-solving approach\n\n"
        "Return ONLY a valid JSON object with this structure:\n"
        "{\n"
        '  \"test_title\": \"<Role> Screening Test\",\n'
        '  \"instructions\": \"Instructions for candidates with 3-4 bullet points\",\n'
        '  \"scenarios\": [\n'
        "    {\n"
        '      \"number\": 1,\n'
        '      \"title\": \"Scenario title\",\n'
        '      \"description\": \"Detailed problem description\",\n'
        '      \"example\": \"Concrete example with data\",\n'
        '      \"question\": \"The evaluation question\"\n'
        "    }\n"
        "  ]\n"
        "}"
    )


def build_evaluation_prompt(response_text, jd_text):
    """Build the prompt to evaluate a candidate's technical response."""
    return (
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
        '- overall_recommendation (string): One of \"Strong Hire\", \"Hire\", '
        '\"Lean Hire\", \"Lean No Hire\", \"No Hire\"\n'
        "- improvement_areas (array of strings): 3-4 specific suggestions for the candidate\n\n"
        f"=== ROLE DESCRIPTION ===\n{jd_text}\n\n"
        f"=== CANDIDATE TECHNICAL RESPONSE ===\n{response_text}"
    )
