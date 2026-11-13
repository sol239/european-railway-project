import asyncio
from datetime import datetime
from pathlib import Path
from typing import cast

import pandas as pd
from airflow.sdk import dag, task  # type: ignore

from core.config.settings import settings
from core.railway.ingestion.gtfs import (
    convert_to_csv,
    download_gtfs_archive,
    extract_gtfs_archive,
)
from core.railway.pipelines.storage import (
    run_directory,
    write_temporary,
)
from core.railway.storage.iceberg import (
    check_lake_state,
    publish_layer,
    read_table,
    table_name,
)
from core.railway.storage.minio import (
    latest_manifest,
    upload_gtfs_archive,
)
from core.railway.storage.recovery import ensure_lake_state
from core.railway.transformation import (
    build_dim_route,
    build_dim_station,
    build_dim_trip,
    build_fact_service_date,
    build_fact_stop_time,
    clean_source,
)


def read_source(path: Path) -> pd.DataFrame:
    """Read one source CSV into a DataFrame, preserving string values."""
    return pd.read_csv(path, dtype="string")


def read_existing_dimension(name: str) -> pd.DataFrame | None:
    """Read mappings from the latest complete Gold manifest in MinIO."""
    manifest = latest_manifest("gold")
    if manifest is None:
        check_lake_state()
        return None
    return read_table(manifest["files"][name]["reference"])


@dag(
    dag_id="railway_pipeline",
    start_date=datetime(2026, 1, 24),
    schedule="@daily",
    catchup=False,
    max_active_runs=1,
    tags=["railway", "etl"],
)
def railway_pipeline():

    @task
    def ingest(pipeline_run_id: str) -> list[str]:
        """Download, extract, and convert the GTFS feed to CSV files."""
        ensure_lake_state()
        raw_dir = run_directory(settings.tmp_dir, pipeline_run_id) / "raw"
        staging_dir = run_directory(settings.tmp_dir, pipeline_run_id) / "staging"
        archive_path = asyncio.run(download_gtfs_archive(raw_dir / "data-gtfs.zip"))
        upload_gtfs_archive(archive_path, pipeline_run_id)
        extracted_files = extract_gtfs_archive(archive_path, staging_dir)
        csv_files: list[Path] = convert_to_csv(files=extracted_files)
        return [str(object=path) for path in csv_files]

    @task
    def source_data_quality(csv_files: list[str], pipeline_run_id: str) -> list[str]:
        """Validate all source rules before releasing files to transformations."""
        from importlib import import_module

        # The existing data-quality directory requires a dynamic import.
        source_quality = import_module("core.railway.data-quality.source")
        source_quality.validate_source(
            run_directory(settings.tmp_dir, pipeline_run_id) / "raw" / "data-gtfs.zip",
            run_directory(settings.tmp_dir, pipeline_run_id) / "staging",
        )
        return csv_files

    @task
    def transform_source_table(
        csv_files: list[str], pipeline_run_id: str, name: str
    ) -> str | None:
        """Stage one cleaned source table; optional calendars may be absent."""
        sources = {Path(file).stem: Path(file) for file in csv_files}
        if name not in sources and name in ("calendar", "calendar_dates"):
            return None
        frame = clean_source(name, read_source(sources[name]))
        path: Path = (
            run_directory(settings.tmp_dir, pipeline_run_id)
            / "silver"
            / f"{name}.parquet"
        )
        return write_temporary(frame, path)

    @task
    def publish_silver_minio(
        files: list[str | None], pipeline_run_id: str
    ) -> list[str]:
        return publish_layer(
            [file for file in files if file is not None], "silver", pipeline_run_id
        )

    @task
    def transform_dim_route(silver_files: list[str], pipeline_run_id: str) -> str:
        sources = {table_name(file): file for file in silver_files}
        frame = build_dim_route(
            routes_df=read_table(sources["routes"]),
            agency_df=read_table(sources["agency"]),
            existing_dim=read_existing_dimension("dim_route"),
        )
        return write_temporary(
            frame,
            run_directory(settings.tmp_dir, pipeline_run_id)
            / "gold"
            / "dim_route.parquet",
        )

    @task
    def transform_dim_station(silver_files: list[str], pipeline_run_id: str) -> str:
        sources = {table_name(file): file for file in silver_files}
        frame = build_dim_station(
            stops_df=read_table(sources["stops"]),
            existing_dim=read_existing_dimension("dim_station"),
        )
        return write_temporary(
            frame,
            run_directory(settings.tmp_dir, pipeline_run_id)
            / "gold"
            / "dim_station.parquet",
        )

    @task
    def transform_dim_trip(silver_files: list[str], pipeline_run_id: str) -> str:
        sources = {table_name(file): file for file in silver_files}
        frame = build_dim_trip(
            trips_df=read_table(sources["trips"]),
            existing_dim=read_existing_dimension("dim_trip"),
        )
        return write_temporary(
            frame,
            run_directory(settings.tmp_dir, pipeline_run_id)
            / "gold"
            / "dim_trip.parquet",
        )

    @task
    def transform_fact_service_date(
        silver_files: list[str], pipeline_run_id: str
    ) -> str:
        sources = {table_name(file): file for file in silver_files}
        frame = build_fact_service_date(
            calendar_dates_df=(
                read_table(sources["calendar_dates"])
                if "calendar_dates" in sources
                else None
            ),
            calendar_df=(
                read_table(sources["calendar"]) if "calendar" in sources else None
            ),
        )
        return write_temporary(
            frame,
            run_directory(settings.tmp_dir, pipeline_run_id)
            / "gold"
            / "fact_service_date.parquet",
        )

    @task
    def transform_fact_stop_time(
        silver_files: list[str],
        pipeline_run_id: str,
        dim_route: str,
        dim_station: str,
        dim_trip: str,
    ) -> str:
        sources = {table_name(file): file for file in silver_files}
        frame = build_fact_stop_time(
            stop_times_df=read_table(sources["stop_times"]),
            trips_df=read_table(sources["trips"]),
            stops_df=read_table(sources["stops"]),
            dim_trip=pd.read_parquet(dim_trip),
            dim_route=pd.read_parquet(dim_route),
            dim_station=pd.read_parquet(dim_station),
        )
        return write_temporary(
            frame,
            run_directory(settings.tmp_dir, pipeline_run_id)
            / "gold"
            / "fact_stop_time.parquet",
        )

    @task
    def publish_gold_minio(files: list[str], pipeline_run_id: str) -> list[str]:
        return publish_layer(files, "gold", pipeline_run_id)

    pipeline_run_id = "{{ run_id }}"
    csv_files = cast(list[str], ingest(pipeline_run_id))
    validated_files = cast(list[str], source_data_quality(csv_files, pipeline_run_id))
    from core.railway.transformation.silver import SOURCE_TABLES

    silver_files = [
        transform_source_table.override(task_id=f"transform_{name}")(
            validated_files, pipeline_run_id, name
        )
        for name in SOURCE_TABLES
    ]
    processed_files = cast(
        list[str], publish_silver_minio(silver_files, pipeline_run_id)
    )
    dim_route = transform_dim_route(processed_files, pipeline_run_id)
    dim_station = transform_dim_station(processed_files, pipeline_run_id)
    dim_trip = transform_dim_trip(processed_files, pipeline_run_id)
    service_dates = transform_fact_service_date(processed_files, pipeline_run_id)
    stop_times = transform_fact_stop_time(
        processed_files, pipeline_run_id, dim_route, dim_station, dim_trip
    )
    publish_gold_minio(
        [dim_route, dim_station, dim_trip, service_dates, stop_times], pipeline_run_id
    )
