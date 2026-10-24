import asyncio
from datetime import datetime
from pathlib import Path
from typing import cast

import pandas as pd

from airflow.sdk import dag, task  # type: ignore
from core.config.settings import settings
from core.railway.ingestion.gtfs import (
    ARCHIVE_DOWNLOAD_PATH,
    convert_to_csv,
    download_gtfs_archive,
    extract_gtfs_archive,
)
from core.railway.transformation import (
    build_dim_routes,
    build_dim_station,
    build_dim_trips,
    build_fact_stop_times,
)


def read_source(path: Path) -> pd.DataFrame:
    """Read one source CSV into a DataFrame, preserving string values."""
    return pd.read_csv(path, dtype="string")


def write_intermediate(frame: pd.DataFrame, name: str) -> str:
    """Store a transformed DataFrame for downstream tasks."""
    settings.processed_dir.mkdir(parents=True, exist_ok=True)
    path = settings.processed_dir / f"{name}.csv"
    frame.to_csv(path, index=False)
    return str(path)


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
    def ingest() -> list[str]:
        """Download, extract, and convert the GTFS feed to CSV files."""
        settings.raw_dir.mkdir(parents=True, exist_ok=True)
        settings.staging_dir.mkdir(parents=True, exist_ok=True)
        archive_path: Path = asyncio.run(main=download_gtfs_archive())
        extracted_files: list[Path] = extract_gtfs_archive(archive_path)
        csv_files: list[Path] = convert_to_csv(files=extracted_files)
        return [str(object=path) for path in csv_files]

    @task
    def source_data_quality(csv_files: list[str]) -> list[str]:
        """Validate all source rules before releasing files to transformations."""
        from importlib import import_module

        # The existing data-quality directory requires a dynamic import.
        source_quality = import_module("core.railway.data-quality.source")
        source_quality.validate_source(ARCHIVE_DOWNLOAD_PATH, settings.staging_dir)
        return csv_files

    @task
    def transform_dim_routes(csv_files: list[str]) -> str:
        source_paths = {Path(file).stem: Path(file) for file in csv_files}
        dimension = build_dim_routes(
            routes_df=read_source(source_paths["routes"]),
            agency_df=read_source(source_paths["agency"]),
        )
        return write_intermediate(dimension, "dim_routes")

    @task
    def transform_dim_station(csv_files: list[str]) -> str:
        source_paths = {Path(file).stem: Path(file) for file in csv_files}
        dimension = build_dim_station(stops_df=read_source(source_paths["stops"]))
        return write_intermediate(dimension, "dim_station")

    @task
    def transform_dim_trips(csv_files: list[str]) -> str:
        source_paths = {Path(file).stem: Path(file) for file in csv_files}
        dimension = build_dim_trips(trips_df=read_source(source_paths["trips"]))
        return write_intermediate(dimension, "dim_trips")

    @task
    def transform_fact_stop_times(
        csv_files: list[str],
        dim_trips: str,
        dim_routes: str,
        dim_station: str,
    ) -> str:
        source_paths = {Path(file).stem: Path(file) for file in csv_files}
        fact = build_fact_stop_times(
            stop_times_df=read_source(source_paths["stop_times"]),
            trips_df=read_source(source_paths["trips"]),
            stops_df=read_source(source_paths["stops"]),
            dim_trips=read_source(Path(dim_trips)),
            dim_routes=read_source(Path(dim_routes)),
            dim_station=read_source(Path(dim_station)),
        )
        return write_intermediate(fact, "fact_stop_times")

    @task
    def publish(path: str, name: str) -> str:
        """Load an intermediate table into the curated directory."""
        df = read_source(Path(path))
        for column in ("trip_key", "route_key", "station_key", "route_type"):
            if column in df.columns:
                df[column] = df[column].astype("Int64")
        settings.curated_dir.mkdir(parents=True, exist_ok=True)
        output_path = settings.curated_dir / f"{name}.parquet"
        df.to_parquet(output_path, index=False)
        return str(output_path)

    csv_files = cast(list[str], ingest())
    csv_files = cast(list[str], source_data_quality(csv_files))

    dim_routes = cast(str, transform_dim_routes(csv_files))
    dim_station = cast(str, transform_dim_station(csv_files))
    dim_trips = cast(str, transform_dim_trips(csv_files))

    fact_stop_times = cast(str, transform_fact_stop_times(
        csv_files=csv_files,
        dim_trips=dim_trips,
        dim_routes=dim_routes,
        dim_station=dim_station,
    ))

    publish.override(task_id="publish_dim_routes")(
        dim_routes, "dim_routes"
    )
    publish.override(task_id="publish_dim_station")(
        dim_station, "dim_station"
    )
    publish.override(task_id="publish_dim_trips")(
        dim_trips, "dim_trips"
    )
    publish.override(task_id="publish_fact_stop_times")(
        fact_stop_times, "fact_stop_times"
    )

