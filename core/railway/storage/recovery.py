"""Recover missing Iceberg objects from verified completed-layer backups."""

import hashlib
import json
import logging
import shutil
from pathlib import Path
from uuid import uuid4

import pyarrow.parquet as pq

from core.config.settings import settings
from core.railway.pipelines.storage import run_directory

log = logging.getLogger(__name__)


def save_backup(files: list[str], layer: str, run_id: str, manifest: dict) -> None:
    """Keep a complete local recovery copy before promoting the remote release."""
    root = settings.tmp_dir / '_recovery' / layer
    destination = run_directory(root, run_id)
    root.mkdir(parents=True, exist_ok=True)
    pending = root / f'.pending-{uuid4().hex}'
    pending.mkdir()
    try:
        for file in files:
            source = Path(file)
            target = pending / source.name
            shutil.copyfile(source, target)
            with target.open('rb') as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            if digest != manifest['files'][source.stem]['sha256']:
                raise ValueError(f'Recovery backup checksum mismatch: {source.name}')
        (pending / 'manifest.json').write_text(json.dumps(manifest))
        if destination.exists():
            # Immutable completed backup already exists; validate it on read.
            shutil.rmtree(pending)
        else:
            pending.rename(destination)
        temporary = root / '_latest.writing'
        temporary.write_text(destination.name)
        temporary.replace(root / '_latest')
    finally:
        if pending.exists():
            shutil.rmtree(pending)


def load_backup(layer: str, identifiers: set[tuple[str, str]]) -> list[str]:
    from core.railway.storage.iceberg import LakeStateError
    root = settings.tmp_dir / '_recovery' / layer
    try:
        name = (root / '_latest').read_text().strip()
        if not name or Path(name).name != name or name in ('.', '..'):
            raise ValueError('Invalid backup pointer')
        directory = root / name
        manifest = json.loads((directory / 'manifest.json').read_text())
        if manifest['layer'] != layer or {(layer, table) for table in manifest['files']} != identifiers:
            raise ValueError('Incomplete backup table set')
        files = []
        for table, entry in manifest['files'].items():
            path = directory / f'{table}.parquet'
            with path.open('rb') as stream:
                digest = hashlib.file_digest(stream, 'sha256').hexdigest()
            if digest != entry['sha256'] or pq.read_metadata(path).num_rows != entry['rows']:
                raise ValueError(f'Invalid backup: {table}')
            files.append(str(path))
        return files
    except (OSError, ValueError, KeyError) as exc:
        raise LakeStateError(f'Cannot recover {layer}: no complete checksum-verified backup. Restore a lake backup.') from exc


def ensure_lake_state() -> None:
    """Repair deleted metadata/releases when complete backups exist; never reset keys."""
    from core.railway.storage.iceberg import get_catalog, check_lake_state, publish_layer, LakeStateError
    from core.railway.storage.minio import latest_manifest

    try:
        check_lake_state()
        return
    except LakeStateError:
        pass
    catalog = get_catalog()
    namespaces = set(catalog.list_namespaces())
    repairs = []
    # Validate every affected layer's backup before changing any catalog entry.
    for layer in ('silver', 'gold'):
        if (layer,) not in namespaces:
            continue
        identifiers = set(catalog.list_tables(layer))
        if not identifiers:
            continue
        missing = []
        for identifier in identifiers:
            try:
                catalog.load_table(identifier)
            except FileNotFoundError:
                missing.append(identifier)
        try:
            release_missing = latest_manifest(layer) is None
        except ValueError:
            release_missing = True
        if missing or release_missing:
            repairs.append((layer, missing, load_backup(layer, identifiers)))
    for layer, missing, files in repairs:
        log.warning('Recovering %s from verified retained outputs: %s missing catalog metadata objects', layer, len(missing))
        for identifier in missing:
            catalog.drop_table(identifier)
        publish_layer(files, layer, f'recovery__{uuid4().hex}')
    check_lake_state()
