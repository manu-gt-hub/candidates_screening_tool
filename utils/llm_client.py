"""LLM client — unified interface for Databricks and local (Bedrock-compatible) backends.

  - **DBX**: workspace Foundation Model API via ``openai`` SDK (auto-token from environment).
  - **LOCAL**: AWS Bedrock-compatible endpoint via ``boto3``.
"""
import json
import os

_SYSTEM_PROMPT = (
    "You are an expert assistant. "
    "Always respond with valid JSON only, no markdown fences."
)

# Cached clients (reused across calls)
_local_client_cache = None
_local_client_key = None
_dbx_client_cache = None


def is_databricks():
    """Return True if running inside a Databricks runtime."""
    return "DATABRICKS_RUNTIME_VERSION" in os.environ


def _resolve_environment(config):
    """Return 'DBX' or 'LOCAL' based on config.ENVIRONMENT."""
    env = getattr(config, "ENVIRONMENT", "AUTO").upper()
    if env == "AUTO":
        return "DBX" if is_databricks() else "LOCAL"
    return env


_MAX_RETRIES = 2


def _strip_fences(text):
    """Remove markdown code fences (```json ... ```) if present."""
    if text.startswith("```"):
        lines = text.split("\n")
        end = len(lines) - 1 if lines[-1].strip() == "```" else len(lines)
        text = "\n".join(lines[1:end]).strip()
    return text


def query_llm(prompt, config):
    """Send a prompt to the configured LLM and return the parsed JSON response.

    Retries up to ``_MAX_RETRIES`` times on malformed JSON before raising.

    Args:
        prompt: Full text prompt (must request JSON output).
        config: The config module (needs AI_MODEL and, for local mode, API_KEY).

    Returns:
        dict parsed from the LLM JSON response.
    """
    env = _resolve_environment(config)
    call = _query_databricks if env == "DBX" else _query_local

    last_error = None
    for attempt in range(1, _MAX_RETRIES + 2):
        content = call(prompt, config).strip()
        content = _strip_fences(content)

        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            last_error = exc
            print(
                f"  ⚠ LLM returned invalid JSON (attempt {attempt}/"
                f"{_MAX_RETRIES + 1}): {exc}"
            )
            print(f"    Raw (first 300 chars): {content[:300]}")
            if attempt <= _MAX_RETRIES:
                continue
            raise ValueError(
                f"LLM returned invalid JSON after {_MAX_RETRIES + 1} attempts. "
                f"Last error: {last_error}"
            ) from last_error

        # Unwrap {"result": {…}} envelope that Databricks FMAPI sometimes adds
        if isinstance(parsed, dict) and list(parsed.keys()) == ["result"]:
            parsed = parsed["result"]

        return parsed


def _query_databricks(prompt, config):
    """Send prompt via OpenAI SDK to Databricks Foundation Model API."""
    client, model = _databricks_client(config)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
    )
    return response.choices[0].message.content


def _query_local(prompt, config):
    """Send prompt via boto3 Bedrock converse API."""
    global _local_client_cache, _local_client_key

    api_key = getattr(config, "API_KEY", None) or os.environ.get("API_KEY")
    endpoint = getattr(config, "API_BASE_URL", None) or getattr(config, "ENDPOINT", None)
    model = getattr(config, "LOCAL_AI_MODEL", None) or config.AI_MODEL

    if not api_key:
        raise ValueError("API_KEY must be set in config.py for local mode")
    if not endpoint:
        raise ValueError("API_BASE_URL (or ENDPOINT) must be set in config.py for local mode")

    region = getattr(config, "BEDROCK_REGION", None) or "us-east-1"
    cache_key = (endpoint, region)

    if _local_client_cache is None or _local_client_key != cache_key:
        import boto3
        from botocore.config import Config as BotoConfig
        os.environ["AWS_BEARER_TOKEN_BEDROCK"] = api_key
        _local_client_cache = boto3.client(
            service_name="bedrock-runtime",
            endpoint_url=endpoint,
            region_name=region,
            config=BotoConfig(read_timeout=300, retries={"max_attempts": 2}),
        )
        _local_client_key = cache_key

    response = _local_client_cache.converse(
        modelId=model,
        system=[{"text": _SYSTEM_PROMPT}],
        messages=[{"role": "user", "content": [{"text": prompt}]}],
    )
    return response["output"]["message"]["content"][0]["text"]


# ── Databricks backend ───────────────────────────────────────────

def _databricks_client(config):
    global _dbx_client_cache
    if _dbx_client_cache is None:
        from openai import OpenAI
        token = _get_token()
        host = _get_host()
        _dbx_client_cache = OpenAI(api_key=token, base_url=f"https://{host}/serving-endpoints")
    return _dbx_client_cache, config.AI_MODEL


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

