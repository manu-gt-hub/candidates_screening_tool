"""
Create Databricks Jobs with file-arrival triggers for the CV Screening pipeline.

This script creates two jobs using the Databricks Python SDK:
  1. CV Ranking Job        — triggers when a new PDF arrives in the CVs folder
  2. Response Evaluator Job — triggers when a new PDF arrives in the technical responses folder

Usage (run from a Databricks notebook or local environment with SDK configured):
    %run ./create_jobs          # from a notebook in the same directory
    python create_jobs.py       # from a local terminal with DATABRICKS_HOST / TOKEN set

Prerequisites:
    pip install databricks-sdk
"""

import sys
import os

# ── Resolve config.py from the same directory as this script ─────────
# Works both inside Databricks (notebook %run) and locally
_script_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _script_dir)
import config  # noqa: E402

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.jobs import (
    Task,
    NotebookTask,
    Source,
    TriggerSettings,
    FileArrivalTriggerConfiguration,
    PauseStatus,
)

# ── Initialise SDK client ────────────────────────────────────────────
# Authenticates automatically via:
#   - Inside Databricks: notebook context
#   - Locally: DATABRICKS_HOST + DATABRICKS_TOKEN env vars or ~/.databrickscfg
w = WorkspaceClient()

# ── Resolve notebook paths dynamically from the current user ─────────
current_user = w.current_user.me()
username = current_user.user_name
base_path = f"/Users/{username}/technical_tests"

NOTEBOOK_CV_RANKING = f"{base_path}/tech_scenarios_creator"
NOTEBOOK_RESPONSE_EVALUATOR = f"{base_path}/tech_responses_evaluator"

# ── File-arrival trigger settings ────────────────────────────────────
# min_time_between_triggers_seconds : minimum cooldown between consecutive runs
# wait_after_last_change_seconds    : debounce — wait for batch uploads to finish
MIN_TIME_BETWEEN_TRIGGERS = 60   # seconds
WAIT_AFTER_LAST_CHANGE = 30      # seconds


def create_cv_ranking_job() -> int:
    """Create the CV Ranking & Technical Test Generation job."""
    print(f"Creating CV Ranking job...")
    print(f"  Notebook : {NOTEBOOK_CV_RANKING}")
    print(f"  Trigger  : file arrival on {config.CVS_PATH}")

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
        trigger=TriggerSettings(
            file_arrival=FileArrivalTriggerConfiguration(
                url=config.CVS_PATH,
                min_time_between_triggers_seconds=MIN_TIME_BETWEEN_TRIGGERS,
                wait_after_last_change_seconds=WAIT_AFTER_LAST_CHANGE,
            ),
            pause_status=PauseStatus.UNPAUSED,
        ),
    )

    print(f"  ✓ Job created (ID: {job.job_id})")
    print(f"  URL: {w.config.host}/#job/{job.job_id}\n")
    return job.job_id


def create_response_evaluator_job() -> int:
    """Create the Technical Response Evaluator job."""
    print(f"Creating Response Evaluator job...")
    print(f"  Notebook : {NOTEBOOK_RESPONSE_EVALUATOR}")
    print(f"  Trigger  : file arrival on {config.TECHNICAL_RESPONSES_PATH}")

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
        trigger=TriggerSettings(
            file_arrival=FileArrivalTriggerConfiguration(
                url=config.TECHNICAL_RESPONSES_PATH,
                min_time_between_triggers_seconds=MIN_TIME_BETWEEN_TRIGGERS,
                wait_after_last_change_seconds=WAIT_AFTER_LAST_CHANGE,
            ),
            pause_status=PauseStatus.UNPAUSED,
        ),
    )

    print(f"  ✓ Job created (ID: {job.job_id})")
    print(f"  URL: {w.config.host}/#job/{job.job_id}\n")
    return job.job_id


# ── Main ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("CV Screening Pipeline — Job Setup")
    print("=" * 60)
    print(f"User       : {username}")
    print(f"Base path  : {base_path}")
    print(f"CVs watch  : {config.CVS_PATH}")
    print(f"Resp watch : {config.TECHNICAL_RESPONSES_PATH}")
    print("=" * 60 + "\n")

    cv_job_id = create_cv_ranking_job()
    eval_job_id = create_response_evaluator_job()

    print("=" * 60)
    print("Setup complete!")
    print(f"  CV Ranking Job ID        : {cv_job_id}")
    print(f"  Response Evaluator Job ID: {eval_job_id}")
    print("=" * 60)
