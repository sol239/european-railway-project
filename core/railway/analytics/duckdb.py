"""DuckDB connections that query Gold Parquet directly in MinIO."""

import os
from urllib.parse import urlsplit

import duckdb


def configure_minio(connection: duckdb.DuckDBPyConnection) -> None:
    """Configure an in-memory secret; credentials are not persisted in the DB."""
    endpoint = urlsplit(os.getenv("S3_ENDPOINT", "http://localhost:7004"))
    if endpoint.scheme not in ("http", "https") or not endpoint.netloc:
        raise ValueError("S3_ENDPOINT must be an HTTP(S) URL")
    def literal(value: str) -> str:
        return "'" + value.replace("'", "''") + "'"
    connection.execute("INSTALL httpfs")
    connection.execute("LOAD httpfs")
    connection.execute("INSTALL iceberg")
    connection.execute("LOAD iceberg")
    connection.execute(f"""
        CREATE OR REPLACE SECRET railway_minio (
            TYPE S3,
            KEY_ID {literal(os.environ['MINIO_ROOT_USER'])},
            SECRET {literal(os.environ['MINIO_ROOT_PASSWORD'])},
            REGION 'us-east-1',
            ENDPOINT {literal(endpoint.netloc)},
            URL_STYLE 'path',
            USE_SSL {'true' if endpoint.scheme == 'https' else 'false'}
        )
    """)


def connect(database: str = "railway.duckdb") -> duckdb.DuckDBPyConnection:
    connection = duckdb.connect(database, config={"storage_compatibility_version": "v1.2.0"})
    try:
        configure_minio(connection)
    except Exception:
        connection.close()
        raise
    return connection
