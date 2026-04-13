"""
Create Databricks Jobs with periodic triggers for the CV Screening pipeline.

This script creates two jobs using the Databricks Python SDK:
  1. CV Ranking Job        — runs periodically to process new CVs
  2. Response Evaluator Job — runs periodically to process new technical responses

Note: file-arrival triggers are not supported for workspace paths.
These jobs use a cron schedule instead (default: every 15 minutes).

Usage (run from a Databricks notebook or local environment with SDK configured):
    %run ./create_jobs          # from a notebook in the same directory
    python create_jobs.py       # from a local terminal with DATABRICKS_HOST / TOKEN set

Prerequisites:
    pip install databricks-sdk
"""

import sys
import os

# ── Resolve config.py from the same directory as this script ─────────
_script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _script_dir)
import config  # noqa: E402

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.jobs import (
    Task,
    NotebookTask,
    Source,
    CronSchedule,
    PauseStatus,
)

# ── Initialise SDK client ────────────────────────────────────────
w = WorkspaceClient()

# ── Resolve notebook paths dynamically from the current user ─────
current_user = w.current_user.me()
username = current_user.user_name
base_path = f"/Users/{username}/technical_tests"

NOTEBOOK_CV_RANKING = f"{base_path}/tech_scenarios_creator"
NOTEBOOK_RESPONSE_EVALUATOR = f"{base_path}/tech_responses_evaluator"

# ── Schedule settings ─────────────────────────────────────────────
# Quartz cron: seconds minutes hours day-of-month month day-of-week year
# Default: every 15 minutes
CRON_SCHEDULE = "0 */15 * * * ?"     # every 15 minutes
TIMEZONE = "UTC"


def create_cv_ranking_job() -> int:
    """Create the CV Ranking & Technical Test Generation job."""
    print("Creating CV Ranking job...")
    print(f"  Notebook : {NOTEBOOK_CV_RANKING}")
    print(f"  Schedule : {CRON_SCHEDULE} ({TIMEZONE})")

    job = w.jobs.create(
        name="CV Ranking & Technical Test Generation",
        tasks=[
            Task(
                task_key="rank_and_generate_tests",
                description="Parse CVs, rank candidates against job description, generate technical tests for top candidates",
                notebook_task=NotebookTask(
                    notebook_path=NOTEBOOK_CV_RANKING,
                    source=Source.WORKSPACE,
                ),
            )
        ],
        schedule=CronSchedule(
            quartz_cron_expression=CRON_SCHEDULE,
            timezone_id=TIMEZONE,
            pause_status=PauseStatus.UNPAUSED,
        ),
    )

    print(f"  \u2713 Job created (ID: {job.job_id})")
    print(f"  URL: {w.config.host}/#job/{job.job_id}\n")
    return job.job_id


def create_response_evaluator_job() -> int:
    """Create the Technical Response Evaluator job."""
    print("Creating Response Evaluator job...")
    print(f"  Notebook : {NOTEBOOK_RESPONSE_EVALUATOR}")
    print(f"  Schedule : {CRON_SCHEDULE} ({TIMEZONE})")

    job = w.jobs.create(
        name="Technical Response Evaluator",
        tasks=[
            Task(
                task_key="evaluate_responses",
                description="Parse technical response PDFs, evaluate against role description, generate evaluation reports",
                notebook_task=NotebookTask(
                    notebook_path=NOTEBOOK_RESPONSE_EVALUATOR,
                    source=Source.WORKSPACE,
                ),
            )
        ],
        schedule=CronSchedule(
            quartz_cron_expression=CRON_SCHEDULE,
            timezone_id=TIMEZONE,
            pause_status=PauseStatus.UNPAUSED,
        ),
    )

    print(f"  \u2713 Job created (ID: {job.job_id})")
    print(f"  URL: {w.config.host}/#job/{job.job_id}\n")
    return job.job_id


# ── Main ───────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("CV Screening Pipeline \u2014 Job Setup")
    print("=" * 60)
    print(f"User       : {username}")
    print(f"Base path  : {base_path}")
    print(f"Schedule   : {CRON_SCHEDULE} ({TIMEZONE})")
    print("=" * 60 + "\n")

    cv_job_id = create_cv_ranking_job()
    eval_job_id = create_response_evaluator_job()

    print("=" * 60)
    print("Setup complete!")
    print(f"  CV Ranking Job ID        : {cv_job_id}")
    print(f"  Response Evaluator Job ID: {eval_job_id}")
    print("=" * 60)
