"""Publish the raw RFN export and a discoverable latest-file pointer in MinIO."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from core.railway.ingestion.rfn_lines import DATASET, FILENAME, SOURCE_URL, parquet_metadata
from core.railway.pipelines.storage import run_directory
from core.railway.storage.create_s3_client import create_s3_client
from core.railway.storage.minio import bucket_name, read_json


def upload_rfn_lines(path: Path, pipeline_run_id: str, bucket: str | None = None) -> str:
    path = Path(path)
    metadata = parquet_metadata(path)
    bucket = bucket or bucket_name()
    prefix = f'data/raw/{DATASET}'
    run = run_directory(Path(), pipeline_run_id).name
    key = f'{prefix}/{run}/{FILENAME}'
    manifest_key = f'{prefix}/{run}/manifest.json'
    with path.open('rb') as stream:
        digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    previous = read_json(manifest_key, bucket)
    if previous and previous['sha256'] != digest:
        raise ValueError('This RFN run has already been published with different bytes')
    manifest = previous or {
        'dataset': DATASET, 'run_id': pipeline_run_id, 'source_url': SOURCE_URL,
        'bucket': bucket, 'key': key, 'uri': f's3://{bucket}/{key}',
        'sha256': digest, 'size_bytes': path.stat().st_size, 'rows': metadata.num_rows,
        'uploaded_at': datetime.now(timezone.utc).isoformat(),
    }
    client = create_s3_client()
    client.upload_file(str(path), bucket, key, ExtraArgs={
        'ContentType': 'application/vnd.apache.parquet', 'Metadata': {'sha256': digest},
    })
    client.put_object(Bucket=bucket, Key=manifest_key, Body=json.dumps(manifest).encode(),
                      ContentType='application/json')
    # Advance discovery only after the raw file and its manifest are uploaded.
    client.put_object(Bucket=bucket, Key=f'{prefix}/_latest.json',
                      Body=json.dumps({'run_id': pipeline_run_id, 'manifest_key': manifest_key}).encode(),
                      ContentType='application/json')
    return manifest['uri']
