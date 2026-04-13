"""Core pipeline logic — works in both Databricks and local mode.

This module provides high-level functions that combine PDF parsing,
LLM calls, and data transformation.  It is the engine behind
``run_local.py`` and can also be imported from Databricks notebooks.
"""
import os

from utils.llm_client import query_llm
from utils.prompts import (
    build_ranking_prompt,
    build_test_prompt,
    build_evaluation_prompt,
)


# ── PDF parsing (local mode — pdfplumber) ────────────────────────────

def parse_pdfs(pdf_dir):
    """Extract text from all PDFs in *pdf_dir* using pdfplumber.

    Returns:
        list[dict]: ``[{"path": "/full/path.pdf", "full_text": "..."}]``
    """
    try:
        import pdfplumber
    except ImportError:
        raise ImportError(
            "Install pdfplumber for local PDF parsing:  pip install pdfplumber"
        )

    results = []
    for fname in sorted(os.listdir(pdf_dir)):
        if fname.lower().endswith(".pdf"):
            fpath = os.path.join(pdf_dir, fname)
            with pdfplumber.open(fpath) as pdf:
                text = "\n\n".join(
                    page.extract_text() or "" for page in pdf.pages
                )
            results.append({"path": fpath, "full_text": text})

    print(f"\u2713 {len(results)} PDF(s) parsed from {pdf_dir}")
    return results


# ── Job description ──────────────────────────────────────────────

def load_job_description(config):
    """Load job description from the configured text file.

    Returns:
        str: The job description text.
    """
    path = config.ROLE_DESCRIPTION_LOCAL_PATH
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    print(f"\u2713 Job description loaded ({len(text)} chars)")
    return text


# ── Ranking ───────────────────────────────────────────────────────

def rank_candidates(cv_documents, jd_text, config):
    """Rank each CV against the job description.

    Args:
        cv_documents: list of ``{"path": ..., "full_text": ...}``
        jd_text:      Job description string.
        config:       Config module.

    Returns:
        list[dict] sorted by ranking_percentage descending.
    """
    results = []
    for doc in cv_documents:
        prompt = build_ranking_prompt(doc["full_text"], jd_text)
        ranking = query_llm(prompt, config)
        ranking["source_file"] = doc["path"]
        results.append(ranking)
        pct = ranking.get("ranking_percentage", 0)
        print(f"  {ranking.get('name', '?')}: {pct:.0f}%")

    results.sort(key=lambda r: r.get("ranking_percentage", 0), reverse=True)
    print(f"\u2713 Ranked {len(results)} candidate(s)")
    return results


# ── Technical test generation ────────────────────────────────────

def generate_tests(ranked_candidates, jd_text, config):
    """Generate technical tests for candidates above the threshold.

    Returns:
        list[dict] — only the candidates that received tests (with
        ``technical_test`` key added to each dict).
    """
    min_pct = config.MIN_MATCH_THRESHOLD
    gen_all = config.GENERATE_TESTS_FOR_ALL_CANDIDATES

    qualifying = [
        c for c in ranked_candidates
        if gen_all or c.get("ranking_percentage", 0) >= min_pct
    ]

    print(
        f"Generating tests for {len(qualifying)}/"
        f"{len(ranked_candidates)} candidate(s)"
    )

    for c in qualifying:
        role = c.get("role", "Technical")
        jd_seniority = c.get("jd_seniority", "Senior")
        prompt = build_test_prompt(role, jd_seniority, jd_text)
        test = query_llm(prompt, config)
        c["technical_test"] = test
        print(
            f"  \u2713 {c.get('name', '?')}: "
            f"{test.get('test_title', 'Test generated')}"
        )

    return qualifying


# ── Response evaluation ──────────────────────────────────────────

def evaluate_responses(response_documents, jd_text, config):
    """Evaluate candidate technical responses.

    Returns:
        list[dict] sorted by match_percentage descending.
    """
    results = []
    for doc in response_documents:
        prompt = build_evaluation_prompt(doc["full_text"], jd_text)
        evaluation = query_llm(prompt, config)
        evaluation["response_file"] = doc["path"]
        results.append(evaluation)
        name = evaluation.get("candidate_name", "?")
        pct = evaluation.get("match_percentage", 0)
        rec = evaluation.get("overall_recommendation", "?")
        print(f"  {name}: {pct:.0f}% \u2014 {rec}")

    results.sort(key=lambda r: r.get("match_percentage", 0), reverse=True)
    print(f"\u2713 Evaluated {len(results)} candidate(s)")
    return results
