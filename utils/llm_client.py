"""LLM client — unified interface for Databricks and local (Bedrock-compatible) backends.

  - **DBX**: workspace Foundation Model API via ``openai`` SDK (auto-token from environment).
  - **LOCAL**: AWS Bedrock-compatible endpoint via ``boto3``.
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
    env = _resolve_environment(config)

    if env == "DBX":
        content = _query_databricks(prompt, config)
    else:
        content = _query_local(prompt, config)

    content = content.strip()

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


def _query_databricks(prompt, config):
    """Send prompt via OpenAI SDK to Databricks Foundation Model API."""
    from openai import OpenAI

    client, model = _databricks_client(config)
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
    return response.choices[0].message.content


def _query_local(prompt, config):
    """Send prompt via boto3 Bedrock converse API."""
    import boto3

    api_key = getattr(config, "API_KEY", None)
    endpoint = getattr(config, "API_BASE_URL", None) or getattr(config, "ENDPOINT", None)
    model = getattr(config, "LOCAL_AI_MODEL", None) or config.AI_MODEL

    if not api_key:
        raise ValueError(
            "API_KEY must be set in config.py for local mode"
        )
    if not endpoint:
        raise ValueError(
            "API_BASE_URL (or ENDPOINT) must be set in config.py for local mode"
        )

    os.environ["AWS_BEARER_TOKEN_BEDROCK"] = api_key

    client = boto3.client(
        service_name="bedrock-runtime",
        endpoint_url=endpoint,
        region_name="nexus",
    )

    system_prompt = (
        "You are an expert assistant. "
        "Always respond with valid JSON only, no markdown fences."
    )

    response = client.converse(
        modelId=model,
        system=[{"text": system_prompt}],
        messages=[{"role": "user", "content": [{"text": prompt}]}],
    )
    return response["output"]["message"]["content"][0]["text"]


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


