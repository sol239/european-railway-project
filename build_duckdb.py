from pathlib import Path
from core.railway.analytics.duckdb import connect
from core.railway.storage.minio import latest_manifest

PROJECT_ROOT = Path(__file__).resolve().parent

parquet_tables: list[str] = [
    "dim_station",
    "dim_route",
    "dim_trip",
    "fact_service_date",
    "fact_stop_time",
]


def build_duckdb() -> None:
    manifest = latest_manifest("gold")
    if manifest is None:
        raise ValueError("No Gold run has been published to MinIO")
    with connect(str(PROJECT_ROOT / "railway.duckdb")) as con:
        con.begin()
        for table in parquet_tables:
            parquet_literal = manifest["files"][table]["metadata_location"].replace("'", "''")
            snapshot_id = int(manifest["files"][table]["snapshot_id"])
            con.execute(f"""
                        CREATE OR REPLACE VIEW {table} AS
                        SELECT * FROM iceberg_scan('{parquet_literal}', snapshot_from_id={snapshot_id})
                        """)
        for old_name in (
            "dim_routes", "dim_trips", "fact_stop_times",
            "fact_service_dates", "bridge_service_dates",
        ):
            con.execute(f"DROP VIEW IF EXISTS {old_name}")
        con.commit()


if __name__ == "__main__":
    build_duckdb()
