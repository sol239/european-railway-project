"""An independent, manually triggered raw-file ingestion for RFN line geometry."""

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

from airflow.sdk import dag, task

from core.config.settings import settings
from core.railway.ingestion.rfn_lines import DATASET, FILENAME, download_rfn_lines
from core.railway.pipelines.storage import run_directory
from core.railway.storage.rfn_lines import upload_rfn_lines


@dag(
    dag_id='rfn_lines_download',
    description='Download the SNCF RFN GeoParquet export unchanged and upload it to MinIO.',
    start_date=datetime(2026, 11, 13, tzinfo=timezone.utc),
    schedule=None,
    catchup=False,
    max_active_runs=1,
    is_paused_upon_creation=False,
    default_args={'retries': 2, 'retry_delay': timedelta(minutes=1)},
    dagrun_timeout=timedelta(minutes=15),
    tags=['railway', 'rfn', 'raw', 'geometry'],
)
def rfn_lines_pipeline():
    @task(execution_timeout=timedelta(minutes=5))
    def download_parquet(pipeline_run_id: str) -> str:
        path = run_directory(settings.tmp_dir / DATASET, pipeline_run_id) / FILENAME
        return str(asyncio.run(download_rfn_lines(path)))

    @task(execution_timeout=timedelta(minutes=5))
    def upload_to_minio(file_path: str, pipeline_run_id: str) -> str:
        return upload_rfn_lines(Path(file_path), pipeline_run_id)

    pipeline_run_id = '{{ run_id }}'
    upload_to_minio(download_parquet(pipeline_run_id), pipeline_run_id)
