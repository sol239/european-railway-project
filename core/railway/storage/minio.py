"""Run-scoped MinIO datasets with manifests published after all uploads succeed."""

import json
import os
from pathlib import Path

from botocore.exceptions import ClientError

from core.railway.pipelines.storage import run_directory
from core.railway.storage.create_s3_client import create_s3_client


def bucket_name() -> str:
    return os.getenv("S3_BUCKET", "railway")


def read_json(key: str, bucket: str | None = None) -> dict | None:
    try:
        response = create_s3_client().get_object(Bucket=bucket or bucket_name(), Key=key)
    except ClientError as exc:
        if exc.response["Error"]["Code"] in ("NoSuchKey", "404", "NotFound"):
            return None
        raise
    with response["Body"] as body:
        return json.loads(body.read())


def latest_manifest(layer: str, bucket: str | None = None) -> dict | None:
    bucket = bucket or bucket_name()
    pointer = read_json(f"data/{layer}/_latest.json", bucket)
    if pointer is None:
        return None
    manifest = read_json(pointer["manifest_key"], bucket)
    if manifest is None:
        raise ValueError(f"Missing published manifest: {pointer['manifest_key']}")
    return manifest


def upload_gtfs_archive(archive_path: Path, pipeline_run_id: str, bucket: str | None = None) -> str:
    bucket = bucket or bucket_name()
    archive_path = Path(archive_path)
    if not archive_path.is_file():
        raise FileNotFoundError(archive_path)
    key = f"data/raw/{run_directory(Path(), pipeline_run_id).name}/data-gtfs.zip"
    create_s3_client().upload_file(str(archive_path), bucket, key,
                                 ExtraArgs={"ContentType": "application/zip"})
    return f"s3://{bucket}/{key}"
