#!/usr/bin/env python3
"""Local runner for the candidate evaluation pipeline.

Usage:
    python run_local.py scenarios   # Rank CVs + generate technical tests
    python run_local.py evaluate    # Evaluate candidate responses
    python run_local.py all         # Run both

Prerequisites (pip install):
    openai pdfplumber reportlab
"""
import sys
import os
import argparse

# Ensure project root is in sys.path
_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_DIR not in sys.path:
    sys.path.insert(0, _PROJECT_DIR)

import config  # noqa: E402
from utils.pipeline import (  # noqa: E402
    parse_pdfs,
    load_job_description,
    rank_candidates,
    generate_tests,
    evaluate_responses,
)
from utils.pdf_reports import (  # noqa: E402
    build_technical_test_pdf,
    build_ranking_report_pdf,
    build_evaluation_report_pdf,
)


def run_scenarios():
    """Run CV ranking and technical test generation."""
    print("=" * 60)
    print("  CV Ranking & Technical Test Generation (Local Mode)")
    print("=" * 60)

    cv_docs = parse_pdfs(config.CVS_PATH)
    if not cv_docs:
        print(f"\u2717 No PDFs found in {config.CVS_PATH}")
        return

    jd_text = load_job_description(config)

    print(f"\nRanking {len(cv_docs)} candidate(s)...")
    rankings = rank_candidates(cv_docs, jd_text, config)

    print(
        f"\nGenerating technical tests "
        f"(threshold: {config.MIN_MATCH_THRESHOLD}%)..."
    )
    tested = generate_tests(rankings, jd_text, config)

    # ── Generate PDFs ────────────────────────────────────────────────
    output_path = config.TECHNICAL_TESTS_OUTPUT_PATH
    os.makedirs(output_path, exist_ok=True)
    logo = getattr(config, "LOGO_PATH", None)

    generated_names = []
    for c in tested:
        try:
            pdf = build_technical_test_pdf(c, output_path, logo)
            generated_names.append(c["name"])
            print(f"\u2713 {pdf}")
        except Exception as e:
            print(f"\u2717 {c.get('name', '?')}: {e}")

    report_path = config.EVALUATION_REPORTS_OUTPUT_PATH
    os.makedirs(report_path, exist_ok=True)
    report = build_ranking_report_pdf(
        rankings,
        report_path,
        logo,
        min_threshold=config.MIN_MATCH_THRESHOLD,
        tested_names=set(generated_names),
    )
    print(f"\u2713 Ranking report \u2192 {report}")


def run_evaluate():
    """Run technical response evaluation."""
    print("=" * 60)
    print("  Technical Response Evaluation (Local Mode)")
    print("=" * 60)

    response_docs = parse_pdfs(config.TECHNICAL_RESPONSES_PATH)
    if not response_docs:
        print(f"\u2717 No PDFs found in {config.TECHNICAL_RESPONSES_PATH}")
        return

    jd_text = load_job_description(config)

    print(f"\nEvaluating {len(response_docs)} response(s)...")
    evaluations = evaluate_responses(response_docs, jd_text, config)

    output_path = config.TECHNICAL_ANSWERS_ANALYSIS_PATH
    os.makedirs(output_path, exist_ok=True)

    for ev in evaluations:
        ev.pop("response_file", None)
        try:
            pdf = build_evaluation_report_pdf(ev, output_path)
            print(f"\u2713 {pdf}")
        except Exception as e:
            print(f"\u2717 {ev.get('candidate_name', '?')}: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Candidate Manager \u2014 Local Runner",
        epilog="Example:  python run_local.py scenarios",
    )
    parser.add_argument(
        "command",
        choices=["scenarios", "evaluate", "all"],
        help=(
            "scenarios = rank CVs + generate tests | "
            "evaluate = score responses | all = both"
        ),
    )
    args = parser.parse_args()

    if args.command in ("scenarios", "all"):
        run_scenarios()
    if args.command in ("evaluate", "all"):
        if args.command == "all":
            print("\n")
        run_evaluate()

    print("\n\u2713 Done.")


if __name__ == "__main__":
    main()
