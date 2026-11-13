import json
import os
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch, AsyncMock

import pandas as pd
from botocore.exceptions import ClientError
from pandas.testing import assert_frame_equal

from core.railway.storage import minio, iceberg
from core.railway.pipelines import railway_gtfs_pipeline as pipeline
from core.railway.pipelines.storage import write_temporary, run_directory
from core.config.settings import Settings
from test_layers import sources, run_silver_tasks, run_gold_tasks


class MemoryS3:
    def __init__(self):
        self.objects = {}
        self.fail_upload = False

    def get_object(self, Bucket, Key):
        try:
            return {'Body': BytesIO(self.objects[(Bucket, Key)])}
        except KeyError:
            raise ClientError({'Error': {'Code': 'NoSuchKey'}}, 'GetObject')

    def put_object(self, Bucket, Key, Body, **kwargs):
        self.objects[(Bucket, Key)] = Body

    def upload_file(self, Filename, Bucket, Key, **kwargs):
        if self.fail_upload:
            raise OSError('Upload interrupted')
        self.objects[(Bucket, Key)] = Path(Filename).read_bytes()


class MinioTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.s3 = MemoryS3()
        patcher = patch.object(minio, 'create_s3_client', return_value=self.s3)
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch.dict(os.environ, {'RAILWAY_WORK_DIR': str(self.root/'scratch'), 'S3_BUCKET': 'railway'})
        patcher.start()
        self.addCleanup(patcher.stop)
        from pyiceberg.catalog import load_catalog
        self.catalog = load_catalog('railway', type='sql', uri=f'sqlite:///{self.root}/catalog.db',
                                    warehouse=(self.root/'warehouse').as_uri())
        for target, value in [('get_catalog', self.catalog), ('create_s3_client', self.s3)]:
            patcher = patch.object(iceberg, target, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.config = Settings()
        patcher = patch.object(pipeline, 'settings', self.config)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.dag = pipeline.railway_pipeline()

    def test_two_runs_and_retries_keep_keys_and_never_write_data_directory(self):
        initial = pd.DataFrame({'trip_key': [501], 'trip_id': ['T'], 'service_id': ['001'], 'trip_headsign': ['Town']})
        initial.to_parquet(self.root/'dim_trip.parquet', index=False)
        cleaned = {name: pipeline.clean_source(name, frame) for name, frame in sources().items()}
        pipeline.build_dim_route(cleaned['routes'], cleaned['agency']).to_parquet(self.root/'dim_route.parquet', index=False)
        pipeline.build_dim_station(cleaned['stops']).to_parquet(self.root/'dim_station.parquet', index=False)
        iceberg.publish_layer([str(path) for path in self.root.glob('*.parquet')], 'gold', 'seed')
        for run_id in ['first/run', 'second']:
            stage = self.root/'staging'/run_id
            stage.mkdir(parents=True)
            frames = sources()
            if run_id == 'second':
                added = frames['trips'].iloc[[0]].copy()
                added['trip_id'] = 'NEW'
                frames['trips'] = pd.concat([added, frames['trips']], ignore_index=True)
            frames['calendar_dates'] = pd.DataFrame({'service_id': ['001'], 'date': ['20261025'], 'exception_type': ['1']})
            inputs = []
            for name, frame in frames.items():
                path = stage/f'{name}.csv'
                frame.to_csv(path, index=False)
                inputs.append(str(path))
            silver = run_silver_tasks(self.dag, inputs, run_id)
            self.assertTrue(all(Path(file).suffix == '.parquet' for file in silver))
            published = self.dag.get_task('publish_silver_minio').python_callable(silver, run_id)
            self.assertTrue(all(uri.startswith('iceberg://railway/silver/') for uri in published))
            gold = run_gold_tasks(self.dag, published, run_id)
            uris = self.dag.get_task('publish_gold_minio').python_callable(gold, run_id)
            manifest = minio.latest_manifest('gold')
            self.assertEqual(manifest['run_id'], run_id)
            self.assertEqual(len(uris), 5)
            trips = iceberg.read_table(manifest['files']['dim_trip']['reference']).set_index('trip_id')
            self.assertEqual(trips.loc['T', 'trip_key'], 501)
            if run_id == 'second':
                self.assertEqual(trips.loc['NEW', 'trip_key'], 502)
            retry = run_gold_tasks(self.dag, published, run_id)
            self.assertEqual(uris, self.dag.get_task('publish_gold_minio').python_callable(retry, run_id))
        self.assertFalse((self.root/'data').exists())
        self.assertTrue(all(str(self.root/'scratch') in path for path in gold))

    def test_failed_upload_does_not_publish_manifest_or_change_latest(self):
        path = write_temporary(pd.DataFrame({'id': [1]}), self.root/'table.parquet')
        iceberg.publish_layer([path], 'silver', 'first')
        with patch.object(iceberg, 'get_catalog', side_effect=OSError('Commit interrupted')):
            with self.assertRaises(OSError):
                iceberg.publish_layer([path], 'silver', 'second')
        self.assertEqual(minio.latest_manifest('silver')['run_id'], 'first')
        self.assertIsNone(minio.read_json('data/silver/runs/second/manifest.json'))
        iceberg.publish_layer([path], 'silver', 'second')
        iceberg.publish_layer([path], 'silver', 'first')
        self.assertEqual(minio.latest_manifest('silver')['run_id'], 'second')
        write_temporary(pd.DataFrame({'id': [2]}), Path(path))
        with self.assertRaisesRegex(ValueError, 'different data'):
            iceberg.publish_layer([path], 'silver', 'second')

    def test_pointer_write_failure_can_be_retried_after_manifest_was_saved(self):
        path = write_temporary(pd.DataFrame({'id': [1]}), self.root/'table.parquet')
        iceberg.publish_layer([path], 'silver', 'first')
        put = self.s3.put_object
        def fail_pointer(**kwargs):
            if kwargs['Key'] == 'data/silver/_latest.json':
                raise OSError('Pointer upload interrupted')
            return put(**kwargs)
        with patch.object(self.s3, 'put_object', side_effect=fail_pointer):
            with self.assertRaises(OSError):
                iceberg.publish_layer([path], 'silver', 'second')
        self.assertEqual(minio.latest_manifest('silver')['run_id'], 'first')
        self.assertIsNotNone(minio.read_json('data/silver/runs/second/manifest.json'))
        iceberg.publish_layer([path], 'silver', 'second')
        self.assertEqual(minio.latest_manifest('silver')['run_id'], 'second')

    def test_real_iceberg_snapshots_support_history_and_empty_tables(self):
        path = write_temporary(pd.DataFrame({'id': pd.Series([1], dtype='Int64')}), self.root/'table.parquet')
        first = iceberg.publish_layer([path], 'silver', 'one')[0]
        write_temporary(pd.DataFrame({'id': pd.Series([2], dtype='Int64')}), Path(path))
        second = iceberg.publish_layer([path], 'silver', 'two')[0]
        self.assertEqual(iceberg.read_table(first)['id'].tolist(), [1])
        self.assertEqual(iceberg.read_table(second)['id'].tolist(), [2])
        write_temporary(pd.DataFrame({'id': pd.Series([], dtype='Int64')}), Path(path))
        empty = iceberg.publish_layer([path], 'silver', 'empty')[0]
        self.assertTrue(iceberg.read_table(empty).empty)
        table = self.catalog.load_table(('silver', 'table'))
        self.assertEqual(table.metadata.format_version, 2)
        self.assertGreaterEqual(len(table.snapshots()), 3)
        self.assertTrue(table.metadata_location.endswith('.metadata.json'))

    def test_deleted_metadata_is_detected_and_explicit_recovery_keeps_keys(self):
        path = write_temporary(pd.DataFrame({'trip_key': [501], 'trip_id': ['T']}),
                               self.root/'dim_trip.parquet')
        iceberg.publish_layer([path], 'gold', 'original')
        table = self.catalog.load_table(('gold', 'dim_trip'))
        Path(table.metadata_location.removeprefix('file://')).unlink()
        with self.assertRaisesRegex(iceberg.LakeStateError, 'metadata.*deleted'):
            iceberg.check_lake_state()
        restored = iceberg.repair_layer_from_files([path], 'gold', 'recovery')
        self.assertEqual(iceberg.read_table(restored[0])['trip_key'].tolist(), [501])
        iceberg.check_lake_state()
        with self.assertRaisesRegex(iceberg.LakeStateError, 'healthy table'):
            iceberg.repair_layer_from_files([path], 'gold', 'unsafe-reset')

    def test_deleted_release_does_not_silently_reset_gold_keys(self):
        path = write_temporary(pd.DataFrame({'trip_key': [501], 'trip_id': ['T']}),
                               self.root/'dim_trip.parquet')
        iceberg.publish_layer([path], 'gold', 'original')
        del self.s3.objects[('railway', 'data/gold/_latest.json')]
        with self.assertRaisesRegex(iceberg.LakeStateError, 'published release is missing'):
            pipeline.read_existing_dimension('dim_trip')

    def test_ingestion_automatically_recovers_empty_object_store_without_resetting_keys(self):
        import shutil
        path = write_temporary(pd.DataFrame({'trip_key': [501], 'trip_id': ['T']}),
                               self.root/'dim_trip.parquet')
        iceberg.publish_layer([path], 'gold', 'original')
        self.s3.objects.clear()
        shutil.rmtree(self.root/'warehouse')
        from core.railway.storage.recovery import ensure_lake_state
        ensure_lake_state()
        release = minio.latest_manifest('gold')
        self.assertTrue(release['run_id'].startswith('recovery__'))
        self.assertEqual(iceberg.read_table(release['files']['dim_trip']['reference'])['trip_key'].tolist(), [501])
        iceberg.check_lake_state()
        # A second check is a no-op, rather than producing more snapshots.
        count = len(self.catalog.load_table(('gold', 'dim_trip')).snapshots())
        ensure_lake_state()
        self.assertEqual(count, len(self.catalog.load_table(('gold', 'dim_trip')).snapshots()))

    def test_automatic_recovery_rejects_corrupted_backup_before_dropping_catalog_entries(self):
        import shutil
        path = write_temporary(pd.DataFrame({'trip_key': [501], 'trip_id': ['T']}),
                               self.root/'dim_trip.parquet')
        iceberg.publish_layer([path], 'gold', 'original')
        backup = next((self.config.tmp_dir/'_recovery/gold/original').glob('*.parquet'))
        backup.write_bytes(b'corrupt')
        self.s3.objects.clear()
        shutil.rmtree(self.root/'warehouse')
        from core.railway.storage.recovery import ensure_lake_state
        with self.assertRaisesRegex(iceberg.LakeStateError, 'checksum-verified backup'):
            ensure_lake_state()
        self.assertEqual(self.catalog.list_tables('gold'), [('gold', 'dim_trip')])

    def test_missing_or_unauthorized_gold_does_not_silently_reset_keys(self):
        self.s3.put_object(Bucket='railway', Key='data/gold/_latest.json',
                           Body=json.dumps({'manifest_key': 'data/gold/missing/manifest.json'}).encode())
        with self.assertRaises(ValueError):
            pipeline.read_existing_dimension('dim_trip')
        error = ClientError({'Error': {'Code': 'AccessDenied'}}, 'GetObject')
        with patch.object(self.s3, 'get_object', side_effect=error):
            with self.assertRaises(ClientError):
                pipeline.read_existing_dimension('dim_trip')

    def test_ingestion_uploads_raw_and_quality_uses_scratch(self):
        archive = run_directory(self.config.tmp_dir, 'test')/'raw/data-gtfs.zip'
        archive.parent.mkdir(parents=True)
        archive.write_bytes(b'ZIP')
        from importlib import import_module
        quality = import_module('core.railway.data-quality.source')
        with patch.object(pipeline, 'download_gtfs_archive', new_callable=AsyncMock, return_value=archive), \
             patch.object(pipeline, 'extract_gtfs_archive', return_value=[]), \
             patch.object(quality, 'validate_source') as validate:
            result = self.dag.get_task('ingest').python_callable('test')
            self.assertEqual(self.s3.objects[('railway', 'data/raw/test/data-gtfs.zip')], b'ZIP')
            self.dag.get_task('source_data_quality').python_callable(result, 'test')
            validate.assert_called_once_with(archive, run_directory(self.config.tmp_dir, 'test')/'staging')
        self.assertFalse((self.root/'data').exists())
