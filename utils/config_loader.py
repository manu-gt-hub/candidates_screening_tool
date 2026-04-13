"""Configuration loading and validation utilities."""
import os
import sys


def load_config(dbutils):
    """Import and return config.py from the notebook's project directory.

    Adds the project root (parent of the notebook) to sys.path so that
    ``import config`` resolves to the project-level config.py.

    Returns:
        The imported config module.
    """
    nb_path = (
        dbutils.notebook.entry_point
        .getDbutils().notebook().getContext()
        .notebookPath().get()
    )
    project_dir = f"/Workspace{os.path.dirname(nb_path)}"
    if project_dir not in sys.path:
        sys.path.insert(0, project_dir)

    # Force reimport (needed after restartPython)
    if "config" in sys.modules:
        del sys.modules["config"]
    import config  # noqa: E402
    return config


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

_COMMON_ATTRS = [
    ("ROLE_DESCRIPTION_LOCAL_PATH", str),
    ("AI_MODEL", str),
]

_SCENARIOS_CREATOR_ATTRS = _COMMON_ATTRS + [
    ("CVS_PATH", str),
    ("TECHNICAL_TESTS_OUTPUT_PATH", str),
    ("EVALUATION_REPORTS_OUTPUT_PATH", str),
    ("MIN_MATCH_THRESHOLD", (int, float)),
    ("GENERATE_TESTS_FOR_ALL_CANDIDATES", bool),
]

_RESPONSES_EVALUATOR_ATTRS = _COMMON_ATTRS + [
    ("TECHNICAL_RESPONSES_PATH", str),
    ("TECHNICAL_ANSWERS_ANALYSIS_PATH", str),
]


def validate_config(cfg, mode="scenarios"):
    """Validate that *cfg* has the required attributes for *mode*.

    Args:
        cfg:  The imported config module.
        mode: ``"scenarios"`` for tech_scenarios_creator,
              ``"evaluator"`` for tech_responses_evaluator.

    Raises:
        SystemExit if any validation error is found.
    """
    attrs = _SCENARIOS_CREATOR_ATTRS if mode == "scenarios" else _RESPONSES_EVALUATOR_ATTRS
    errors = []

    for attr, expected_type in attrs:
        val = getattr(cfg, attr, None)
        if val is None:
            errors.append(f"Missing required variable: {attr}")
        elif not isinstance(val, expected_type if isinstance(expected_type, tuple) else (expected_type,)):
            errors.append(f"{attr} must be {expected_type}, got {type(val).__name__}")

    # Paths — warn if missing but do not block execution
    path_attrs = ["CVS_PATH", "ROLE_DESCRIPTION_LOCAL_PATH"] if mode == "scenarios" \
        else ["TECHNICAL_RESPONSES_PATH", "ROLE_DESCRIPTION_LOCAL_PATH"]
    warnings = []
    for attr in path_attrs:
        path = getattr(cfg, attr, "")
        if path and not os.path.exists(path):
            warnings.append(f"{attr} path does not exist: {path}")

    # No placeholder values
    for attr in ("AI_MODEL",):
        val = getattr(cfg, attr, "")
        if val and val.startswith("<"):
            errors.append(f"{attr} still has placeholder value: {val}")

    if errors:
        print("\u274c Configuration errors:")
        for e in errors:
            print(f"  - {e}")
        raise SystemExit("Fix config.py before running this notebook.")

    if warnings:
        print("\u26a0\ufe0f  Path warnings (files may not be placed yet):")
        for w in warnings:
            print(f"  - {w}")

    print("\u2713 Configuration validated")
