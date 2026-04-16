"""Job description loading utilities (Databricks mode — requires PySpark)."""


def load_job_description(spark, config):
    """Load the job description from a local file and register it
    as a Spark temporary view called ``role_description``.

    Args:
        spark:  Active SparkSession.
        config: The imported config module.

    Returns:
        The job description as a plain-text string.
    """
    path = config.ROLE_DESCRIPTION_LOCAL_PATH
    print(f"Loading job description from: {path}")
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    print(f"\u2713 Loaded ({len(text)} chars)")

    from pyspark.sql import Row
    spark.createDataFrame([Row(full_text=text)]).createOrReplaceTempView("role_description")
    print("\u2713 role_description view created")
    return text
