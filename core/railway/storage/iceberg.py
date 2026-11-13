"""Apache Iceberg tables in MinIO, backed by a PostgreSQL SQL catalog."""

import hashlib
import json
import os
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pyiceberg.catalog import load_catalog
from sqlalchemy.engine import URL

from core.railway.pipelines.storage import run_directory
from core.railway.storage.create_s3_client import create_s3_client
from core.railway.storage.minio import bucket_name, latest_manifest, read_json


def get_catalog():
    uri = os.getenv("ICEBERG_CATALOG_URI") or URL.create(
        "postgresql+psycopg2", username="iceberg",
        password=os.getenv("ICEBERG_CATALOG_PASSWORD", os.environ.get("MINIO_ROOT_PASSWORD")),
        host=os.getenv("ICEBERG_CATALOG_HOST", "localhost"),
        port=int(os.getenv("ICEBERG_CATALOG_PORT", "7005")), database="iceberg",
    ).render_as_string(hide_password=False)
    return load_catalog(
        "railway", type="sql", uri=uri,
        warehouse=f"s3://{bucket_name()}/data",
        **{"s3.endpoint": os.getenv("S3_ENDPOINT", "http://localhost:7004"),
           "s3.access-key-id": os.environ["MINIO_ROOT_USER"],
           "s3.secret-access-key": os.environ["MINIO_ROOT_PASSWORD"],
           "s3.region": "us-east-1", "s3.force-virtual-addressing": "false"},
    )


class LakeStateError(RuntimeError):
    """The catalog and object storage no longer describe the same lake."""


def check_lake_state() -> None:
    """Reject deleted releases/metadata before running ingestion or resetting keys."""
    catalog = get_catalog()
    namespaces = set(catalog.list_namespaces())
    for layer in ("silver", "gold"):
        if (layer,) not in namespaces:
            continue
        identifiers = catalog.list_tables(layer)
        try:
            release = latest_manifest(layer)
        except ValueError as exc:
            raise LakeStateError(f"Published {layer} release manifest is missing") from exc
        if identifiers and release is None:
            raise LakeStateError(
                f"Iceberg catalog still contains {layer} tables but MinIO's published release is missing. "
                "Restore MinIO and its catalog together, or repair from retained outputs. "
                "Do not delete only the MinIO data/ prefix."
            )
        for identifier in identifiers:
            try:
                catalog.load_table(identifier)
            except FileNotFoundError as exc:
                raise LakeStateError(
                    f"Iceberg metadata for {'.'.join(identifier)} was deleted from MinIO. "
                    "Restore the missing objects or repair from retained outputs; table keys will not be reset."
                ) from exc


def repair_layer_from_files(files: list[str], layer: str, recovery_run_id: str) -> list[str]:
    """Explicit disaster recovery of missing metadata, using retained known-good outputs.

    This rebuilds current data and keys, not deleted Iceberg history. Healthy
    catalog entries are never dropped. Back up the catalog before calling.
    """
    if layer not in ("silver", "gold"):
        raise ValueError(layer)
    paths = [Path(file) for file in files]
    if not paths or any(not path.is_file() or path.suffix != ".parquet" for path in paths):
        raise ValueError("Recovery requires existing Parquet outputs")
    catalog = get_catalog()
    identifiers = set(catalog.list_tables(layer)) if (layer,) in catalog.list_namespaces() else set()
    supplied = {(layer, path.stem) for path in paths}
    if identifiers - supplied:
        raise LakeStateError("Recovery requires the complete layer backup, not a partial table set")
    for path in paths:
        pq.read_metadata(path)  # Validate every backup before changing catalog entries.
    orphaned = []
    for path in paths:
        identifier = (layer, path.stem)
        if identifier in identifiers:
            try:
                catalog.load_table(identifier)
            except FileNotFoundError:
                orphaned.append(identifier)
            else:
                raise LakeStateError(f"Refusing to replace healthy table {'.'.join(identifier)} during recovery")
    for identifier in orphaned:
        catalog.drop_table(identifier)
    return publish_layer(files, layer, recovery_run_id)


def table_name(reference: str) -> str:
    return Path(urlsplit(reference).path).name


def read_table(reference: str) -> pd.DataFrame:
    """Read exactly the Iceberg snapshot selected by the published release."""
    location = urlsplit(reference)
    if location.scheme != "iceberg" or location.netloc != "railway":
        raise ValueError(f"Expected an Iceberg snapshot reference: {reference}")
    namespace, name = location.path.strip("/").split("/")
    snapshot_id = int(parse_qs(location.query)["snapshot_id"][0])
    return get_catalog().load_table((namespace, name)).scan(snapshot_id=snapshot_id).to_pandas()


def publish_layer(files: list[str], layer: str, pipeline_run_id: str) -> list[str]:
    """Commit real Iceberg snapshots, then publish a complete layer release.

    Commits are atomic per table. Release manifests pin snapshot IDs so consumers
    retain the previous complete layer if a later table fails. Retries reuse
    previously committed snapshots for the same run and input hash.
    """
    if layer not in ("silver", "gold"):
        raise ValueError(layer)
    paths = sorted(Path(file) for file in files)
    if not paths or len({path.stem for path in paths}) != len(paths):
        raise ValueError("Expected a non-empty set of unique Parquet tables")
    key = f"data/{layer}/runs/{run_directory(Path(), pipeline_run_id).name}/manifest.json"
    existing = read_json(key)
    pointer = read_json(f"data/{layer}/_latest.json")
    previous = existing.get("previous_manifest_key") if existing else (pointer["manifest_key"] if pointer else None)
    catalog = get_catalog()
    catalog.create_namespace_if_not_exists(layer)
    entries = {}
    for path in paths:
        if path.suffix != ".parquet" or not path.is_file():
            raise ValueError(f"Expected a Parquet file: {path}")
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        data = pq.read_table(path)
        # Iceberg stores logical string types; pandas may emit large_string/null.
        schema = pa.schema([
            pa.field(field.name, pa.string() if pa.types.is_large_string(field.type) or pa.types.is_null(field.type)
                     else field.type, nullable=True) for field in data.schema
        ])
        data = data.cast(schema)
        identifier = (layer, path.stem)
        if catalog.table_exists(identifier):
            table = catalog.load_table(identifier)
        else:
            table = catalog.create_table(identifier, schema=schema,
                                         location=f"{catalog.properties['warehouse'].rstrip('/')}/{layer}/{path.stem}",
                                         properties={"format-version": "2"})
        snapshot = next((snapshot for snapshot in reversed(table.snapshots())
                         if snapshot.summary and snapshot.summary.get("pipeline_run_id") == pipeline_run_id), None)
        if snapshot is not None:
            if snapshot.summary.get("source_sha256") != digest:
                raise ValueError(f"Run already committed with different data: {path.stem}/{pipeline_run_id}")
        else:
            with table.update_schema() as update:
                update.union_by_name(schema)
            properties = {"pipeline_run_id": pipeline_run_id, "source_sha256": digest}
            if table.current_snapshot() is None:
                table.append(data, snapshot_properties=properties)
            else:
                table.overwrite(data, snapshot_properties=properties)
            snapshot = table.current_snapshot()
        entries[path.stem] = {
            "identifier": f"{layer}.{path.stem}", "snapshot_id": snapshot.snapshot_id,
            "metadata_location": table.metadata_location, "rows": data.num_rows,
            "sha256": digest,
            "reference": f"iceberg://railway/{layer}/{path.stem}?snapshot_id={snapshot.snapshot_id}",
        }
    manifest = {"format": "iceberg", "run_id": pipeline_run_id, "layer": layer,
                "files": entries, "previous_manifest_key": previous}
    if existing is not None:
        # metadata_location may advance while the pinned snapshot stays identical.
        for name, entry in entries.items():
            old = existing["files"].get(name)
            if old is None or old["snapshot_id"] != entry["snapshot_id"] or old["sha256"] != entry["sha256"]:
                raise ValueError(f"Run already published with different tables: {pipeline_run_id}")
        if set(existing["files"]) != set(entries):
            raise ValueError("Run already published with different table set")
        manifest = existing
    else:
        create_s3_client().put_object(Bucket=bucket_name(), Key=key, Body=json.dumps(manifest).encode(),
                                     ContentType="application/json")
    pointer = read_json(f"data/{layer}/_latest.json")
    if (pointer["manifest_key"] if pointer else None) in (key, previous):
        from core.railway.storage.recovery import save_backup
        save_backup(files, layer, pipeline_run_id, manifest)
        create_s3_client().put_object(Bucket=bucket_name(), Key=f"data/{layer}/_latest.json",
                                     Body=json.dumps({"run_id": pipeline_run_id, "manifest_key": key}).encode(),
                                     ContentType="application/json")
    return [entry["reference"] for entry in manifest["files"].values()]
