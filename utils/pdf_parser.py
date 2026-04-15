"""PDF parsing utilities using Databricks ai_parse_document."""
import os

from pyspark.sql.types import StructType, StructField, StringType, BinaryType

_BINARY_SCHEMA = StructType([
    StructField("path", StringType()),
    StructField("content", BinaryType()),
])

_PARSE_SQL = """
CREATE OR REPLACE TEMPORARY VIEW {view_name} AS
WITH parsed AS (
  SELECT path, ai_parse_document(content, map('version', '2.0')) AS parsed
  FROM {binary_view}
),
extracted AS (
  SELECT path,
    concat_ws('\\n\\n',
      transform(
        try_cast(parsed:document:elements AS ARRAY<VARIANT>),
        element -> try_cast(element:content AS STRING)
      )
    ) AS full_text
  FROM parsed
  WHERE try_cast(parsed:error_status AS STRING) IS NULL
)
SELECT * FROM extracted
WHERE full_text IS NOT NULL AND TRIM(full_text) != ''
"""


def parse_pdfs_to_view(spark, pdf_dir, view_name="parsed_texts"):
    """Read all PDFs from *pdf_dir*, parse them with ``ai_parse_document``,
    and register the results as a Spark temporary view.

    Args:
        spark:     Active SparkSession.
        pdf_dir:   Directory containing PDF files.
        view_name: Name of the temporary view to create (default: ``parsed_texts``).

    Returns:
        Number of PDF files found.
    """
    files_data = []
    for fname in sorted(os.listdir(pdf_dir)):
        if fname.lower().endswith(".pdf"):
            filepath = os.path.join(pdf_dir, fname)
            with open(filepath, "rb") as f:
                files_data.append((filepath, bytearray(f.read())))

    binary_view = f"_binary_{view_name}"
    spark.createDataFrame(files_data, _BINARY_SCHEMA).createOrReplaceTempView(binary_view)
    spark.sql(_PARSE_SQL.format(view_name=view_name, binary_view=binary_view))

    print(f"\u2713 {len(files_data)} PDF(s) parsed \u2192 view '{view_name}'")
    return len(files_data)
