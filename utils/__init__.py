"""Shared utilities for the CV Screening & Technical Evaluation pipeline.

Spark-dependent modules (config_loader, pdf_parser, job_description) are
imported lazily to avoid ImportError when running in local mode without
PySpark installed.
"""

try:
    from pyspark.sql import SparkSession as _  # noqa: F401 — guard: PySpark available?
    from utils.config_loader import load_config, validate_config
    from utils.pdf_parser import parse_pdfs_to_view
    from utils.job_description import load_job_description
except ImportError:
    # PySpark not installed — Databricks-only modules are unavailable (expected in local mode)
    pass
