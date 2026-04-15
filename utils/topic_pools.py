"""Technical topic pools for scenario generation.

Each role has a pool of topics. When generating technical tests,
``get_topics(variant, role)`` selects 3 topics per candidate by
rotating through the pool so that no two candidates share the
same combination.

To add a new role, just add a key to ``TOPIC_POOLS``.
"""

TOPIC_POOLS: dict[str, list[str]] = {
    "data_engineer": [
        "Data quality & validation",
        "Pipeline construction & orchestration",
        "Data architecture & modeling",
        "Data skew & partitioning strategies",
        "Performance optimization & tuning",
        "Out-of-memory & resource management",
        "Schema evolution & migrations",
        "Real-time vs batch processing",
        "Data governance & lineage",
        "Testing & observability in data pipelines",
    ],
    "data_scientist": [
        "Experiment design & A/B testing",
        "Feature engineering & selection",
        "Model training & evaluation",
        "Model deployment & monitoring",
        "Statistical analysis & inference",
        "Data quality & preprocessing",
        "Time series & forecasting",
        "NLP & unstructured data",
        "Recommender systems",
        "Explainability & bias detection",
    ],
}

# Fallback pool when the role doesn't match any key
DEFAULT_POOL: list[str] = [
    "System design & architecture",
    "Data quality & validation",
    "Performance optimization",
    "Scalability & resource management",
    "Testing & observability",
    "Pipeline construction & orchestration",
    "Real-time vs batch processing",
    "Schema evolution & data modeling",
    "Governance, security & compliance",
    "Monitoring, alerting & incident response",
]

SCENARIOS_PER_TEST = 3


def _resolve_pool(role: str | None) -> list[str]:
    """Return the topic pool for a given role (case-insensitive, fuzzy)."""
    if not role:
        return DEFAULT_POOL
    role_lower = role.lower().replace("-", " ").replace("_", " ")
    role_words = role_lower.split()
    partial_match = None
    for key, pool in TOPIC_POOLS.items():
        key_norm = key.replace("_", " ")
        key_words = set(key_norm.split())
        # Exact match: all key words present or key phrase is a substring
        if key_words.issubset(role_words) or key_norm in role_lower:
            return pool
        # Partial match: any meaningful key word in the role (first hit wins)
        if partial_match is None:
            for word in key_words:
                if word in role_lower and word not in ("data",):
                    partial_match = pool
                    break
    return partial_match or DEFAULT_POOL


def get_topics(
    variant_number: int,
    role: str | None = None,
    n: int = SCENARIOS_PER_TEST,
) -> list[str]:
    """Return *n* topics for *variant_number* (1-based), rotating through the pool.

    Each variant gets a different slice.  With 10 topics and n=3 the first
    10 variants are guaranteed fully unique combinations; after that they
    cycle but with an offset so overlap is minimised.

    >>> get_topics(1, "data_engineer")
    ['Data quality & validation', 'Pipeline construction & orchestration', 'Data architecture & modeling']
    >>> get_topics(2, "data_engineer")
    ['Data skew & partitioning strategies', 'Performance optimization & tuning', 'Out-of-memory & resource management']
    """
    pool = _resolve_pool(role)
    size = len(pool)
    start = ((variant_number - 1) * n) % size
    indices = [(start + i) % size for i in range(n)]
    return [pool[i] for i in indices]


def get_topics_str(
    variant_number: int,
    role: str | None = None,
    n: int = SCENARIOS_PER_TEST,
) -> str:
    """Return topics formatted as a numbered string for prompt embedding.

    Example::

        1. Data quality & validation
        2. Pipeline construction & orchestration
        3. Data architecture & modeling
    """
    topics = get_topics(variant_number, role, n)
    return "\n".join(f"{i+1}. {t}" for i, t in enumerate(topics))


def list_roles() -> list[str]:
    """Return available role keys."""
    return list(TOPIC_POOLS.keys())
