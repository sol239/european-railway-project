import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pyarrow as pa
import pyarrow.parquet as pq

from core.railway.ingestion import rfn_lines as ingestion
from core.railway.storage import rfn_lines as storage, minio
from test_minio import MemoryS3


class RFNLinesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def write_export(self, path, code='001000'):
        path.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(pa.table({'code_ligne': [code], 'geo_shape': [b'unchanged-wkb']}), path)

    def test_download_uses_file_helper_and_keeps_original_bytes_on_retry(self):
        path = self.root / ingestion.FILENAME
        async def download(url, path):
            self.assertEqual(url, ingestion.SOURCE_URL)
            self.write_export(path)
        helper = AsyncMock(side_effect=download)
        with patch.object(ingestion.FetchingHelper, 'download_file', helper):
            self.assertEqual(asyncio.run(ingestion.download_rfn_lines(path)), path)
            original = path.read_bytes()
            self.assertEqual(asyncio.run(ingestion.download_rfn_lines(path)).read_bytes(), original)
        helper.assert_awaited_once()
        self.assertFalse(path.with_suffix('.parquet.downloading').exists())

    def test_interrupted_and_invalid_downloads_never_become_complete_files(self):
        path = self.root / ingestion.FILENAME
        async def interrupted(url, path):
            path.write_bytes(b'partial download')
            raise OSError('Disconnected')
        async def invalid(url, path):
            path.write_bytes(b'<html>not parquet</html>')
        for handler, expected in [(interrupted, OSError), (invalid, ValueError)]:
            with patch.object(ingestion.FetchingHelper, 'download_file', AsyncMock(side_effect=handler)):
                with self.assertRaises(expected):
                    asyncio.run(ingestion.download_rfn_lines(path))
            self.assertFalse(path.exists())
            self.assertFalse(path.with_suffix('.parquet.downloading').exists())

    def test_upload_publishes_original_file_and_latest_only_after_success(self):
        path = self.root / ingestion.FILENAME
        self.write_export(path)
        client = MemoryS3()
        with patch.object(storage, 'create_s3_client', return_value=client), \
             patch.object(minio, 'create_s3_client', return_value=client):
            uri = storage.upload_rfn_lines(path, 'first/run', bucket='railway')
            prefix = f'data/raw/{ingestion.DATASET}'
            latest_key = ('railway', f'{prefix}/_latest.json')
            pointer = json.loads(client.objects[latest_key])
            manifest = json.loads(client.objects[('railway', pointer['manifest_key'])])
            self.assertIn('first%2Frun', uri)
            self.assertEqual(manifest['rows'], 1)
            self.assertEqual(client.objects[('railway', manifest['key'])], path.read_bytes())
            self.assertEqual(storage.upload_rfn_lines(path, 'first/run', bucket='railway'), uri)
            client.fail_upload = True
            with self.assertRaises(OSError):
                storage.upload_rfn_lines(path, 'second', bucket='railway')
            self.assertEqual(json.loads(client.objects[latest_key]), pointer)
            client.fail_upload = False
            self.write_export(path, code='changed')
            with self.assertRaisesRegex(ValueError, 'different bytes'):
                storage.upload_rfn_lines(path, 'first/run', bucket='railway')

    def test_dag_has_only_download_and_upload_with_paths_in_shared_scratch(self):
        from core.railway.pipelines.rfn_lines_pipeline import rfn_lines_pipeline
        from airflow.sdk.bases.decorator import KeywordParameters
        from airflow.sdk.definitions.context import KNOWN_CONTEXT_KEYS
        dag = rfn_lines_pipeline()
        self.assertEqual(set(dag.task_ids), {'download_parquet', 'upload_to_minio'})
        self.assertEqual(dag.get_task('upload_to_minio').upstream_task_ids, {'download_parquet'})
        self.assertIsNone(dag.schedule)
        for task in dag.tasks:
            KeywordParameters.determine(task.python_callable, task.op_args,
                                        {key: None for key in KNOWN_CONTEXT_KEYS})
        with patch.dict(os.environ, {'RAILWAY_WORK_DIR': str(self.root)}), \
             patch('core.railway.pipelines.rfn_lines_pipeline.download_rfn_lines', AsyncMock(side_effect=lambda path: path)) as mock:
            path = dag.get_task('download_parquet').python_callable('one/run')
            self.assertTrue(Path(path).is_relative_to(self.root))
            self.assertIn('one%2Frun', path)
            mock.assert_awaited_once()
