#!/usr/bin/env python3
"""
build_setup.py — Bootstrap the project folder structure and configuration.

Creates:
  1. All required subdirectories under resources/
  2. A fresh config.py from config.py.example (if config.py does not already exist)

Usage (from the technical_tests/ directory):
  python build_setup.py

Or from a Databricks notebook:
  %run ./build_setup
"""
import os
import shutil

# ── Resolve paths relative to this script ────────────────────────────
try:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
except NameError:
    # __file__ is not defined when executed via %run in a Databricks notebook
    _nb_path = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
    SCRIPT_DIR = f"/Workspace{os.path.dirname(_nb_path)}"
RESOURCES_DIR = os.path.join(SCRIPT_DIR, "resources")

# ── Required folder structure ────────────────────────────────────────
REQUIRED_DIRS = [
    os.path.join(RESOURCES_DIR, "cvs_landing"),
    os.path.join(RESOURCES_DIR, "job_description"),
    os.path.join(RESOURCES_DIR, "images"),
    os.path.join(RESOURCES_DIR, "technical_responses", "landing"),
    os.path.join(RESOURCES_DIR, "technical_responses", "analysis"),
    os.path.join(RESOURCES_DIR, "technical_tests"),
    os.path.join(RESOURCES_DIR, "report_analysis"),
]


def create_folder_structure():
    """Create all required directories (idempotent)."""
    print("── Creating folder structure ──")
    for d in REQUIRED_DIRS:
        os.makedirs(d, exist_ok=True)
        rel = os.path.relpath(d, SCRIPT_DIR)
        print(f"  \u2713 {rel}/")
    print()


def create_config():
    """Copy config.py.example \u2192 config.py if config.py does not exist."""
    config_path = os.path.join(SCRIPT_DIR, "config.py")
    example_path = os.path.join(SCRIPT_DIR, "config.py.example")

    print("── Setting up config.py ──")

    if os.path.exists(config_path):
        print(f"  \u2298 config.py already exists \u2014 skipping (delete it manually to regenerate)")
        return

    if not os.path.exists(example_path):
        print(f"  \u2717 config.py.example not found at {example_path}")
        print(f"    Cannot generate config.py without the template.")
        return

    shutil.copy2(example_path, config_path)
    print(f"  \u2713 config.py created from config.py.example")
    print()
    print("  The default config is ready to run. Customise these if needed:")
    print("     - AI_MODEL                          \u2192 your Databricks model endpoint")
    print("     - MIN_MATCH_THRESHOLD               \u2192 minimum match % for recommendations")
    print("     - GENERATE_TESTS_FOR_ALL_CANDIDATES  \u2192 True to test every candidate")
    print()


def print_checklist():
    """Print a checklist of what the user needs to provide."""
    print("── Setup checklist ──")
    checks = [
        ("config.py",                                   "Edit with your company name, AI model, and parameters"),
        ("resources/cvs_landing/",                      "Place candidate CV PDFs here"),
        ("resources/job_description/job_description.txt", "Write/paste the job description"),
        ("resources/images/logo.png",                   "Place your company logo PNG here"),
        ("resources/technical_responses/landing/",      "Place candidate response PDFs here (for evaluator notebook)"),
    ]
    for path, desc in checks:
        full = os.path.join(SCRIPT_DIR, path)
        exists = os.path.exists(full)
        icon = "\u2713" if exists else "\u25cb"
        print(f"  {icon} {path:<52} {desc}")
    print()


# ── Main ─────────────────────────────────────────────────────────────
if __name__ == "__main__" or "dbutils" in dir():
    print("=" * 60)
    print("  Technical Tests Pipeline \u2014 Project Setup")
    print("=" * 60)
    print()
    create_folder_structure()
    create_config()
    print_checklist()
    print("Setup complete. Run the notebooks when all items are \u2713.")
