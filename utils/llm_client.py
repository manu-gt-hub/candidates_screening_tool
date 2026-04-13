"""LLM client — unified interface for Databricks and local (OpenAI-compatible) backends.

Both backends use the ``openai`` Python SDK:
  - **DBX**: workspace Foundation Model API (auto-token from environment).
  - **LOCAL**: any OpenAI-compatible endpoint (OpenAI, Anthropic, Ollama…).
"""
import json
import os


def is_databricks():
    """Return True if running inside a Databricks runtime."""
    return "DATABRICKS_RUNTIME_VERSION" in os.environ


def _resolve_environment(config):
    """Return 'DBX' or 'LOCAL' based on config.ENVIRONMENT."""
    env = getattr(config, "ENVIRONMENT", "AUTO").upper()
    if env == "AUTO":
        return "DBX" if is_databricks() else "LOCAL"
    return env


def query_llm(prompt, config):
    """Send a prompt to the configured LLM and return the parsed JSON response.

    Args:
        prompt: Full text prompt (must request JSON output).
        config: The config module (needs AI_MODEL and, for local mode, API_KEY).

    Returns:
        dict parsed from the LLM JSON response.
    """
    from openai import OpenAI

    env = _resolve_environment(config)

    if env == "DBX":
        client, model = _databricks_client(config)
    else:
        client, model = _local_client(config)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are an expert assistant. "
                    "Always respond with valid JSON only, no markdown fences."
                ),
            },
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
    )

    content = response.choices[0].message.content.strip()

    # Strip markdown code fences if the model wraps them anyway
    if content.startswith("```"):
        lines = content.split("\n")
        end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
        content = "\n".join(lines[1:end]).strip()

    parsed = json.loads(content)

    # Unwrap {"result": {…}} envelope that Databricks FMAPI sometimes adds
    if isinstance(parsed, dict) and list(parsed.keys()) == ["result"]:
        parsed = parsed["result"]

    return parsed


# ── Databricks backend ───────────────────────────────────────────

def _databricks_client(config):
    from openai import OpenAI

    token = _get_token()
    host = _get_host()
    client = OpenAI(api_key=token, base_url=f"https://{host}/serving-endpoints")
    return client, config.AI_MODEL


def _get_token():
    """Retrieve the Databricks API token."""
    token = os.environ.get("DATABRICKS_TOKEN")
    if token:
        return token
    try:
        from dbruntime.databricks_repl_context import get_context
        return get_context().apiToken
    except Exception:
        pass
    raise RuntimeError("Cannot retrieve Databricks API token")


def _get_host():
    """Retrieve the Databricks workspace hostname."""
    host = os.environ.get("DATABRICKS_HOST", "").replace("https://", "").rstrip("/")
    if host:
        return host
    try:
        from pyspark.sql import SparkSession
        spark = SparkSession.getActiveSession()
        if spark:
            return spark.conf.get("spark.databricks.workspaceUrl")
    except Exception:
        pass
    raise RuntimeError("Cannot determine Databricks workspace URL")


# ── Local backend ────────────────────────────────────────────────

def _local_client(config):
    from openai import OpenAI

    api_key = getattr(config, "API_KEY", None) or os.environ.get("OPENAI_API_KEY")
    api_base = getattr(config, "API_BASE_URL", None) or "https://api.openai.com/v1"
    model = getattr(config, "LOCAL_AI_MODEL", None) or config.AI_MODEL

    if not api_key:
        raise ValueError(
            "API_KEY must be set in config.py or OPENAI_API_KEY env var for local mode"
        )

    client = OpenAI(api_key=api_key, base_url=api_base)
    return client, model
