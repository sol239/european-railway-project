import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from pandas.testing import assert_frame_equal

from core.railway.transformation import (
    clean_source, build_dim_route, build_dim_station, build_dim_trip, build_fact_stop_time,
)


def sources():
    return {
        'agency': pd.DataFrame([{'agency_id': ' A ', 'agency_name': ' Rail '}]),
        'routes': pd.DataFrame([{'route_id': ' R ', 'agency_id': ' A ',
            'route_short_name': ' EXPRESS ', 'route_long_name': ' CITY ', 'route_type': ' 2 ',
            'route_url': ' https://example.com '}]),
        'stops': pd.DataFrame([
            {'stop_id': ' StopArea:S ', 'stop_name': ' CENTRAL ', 'parent_station': '', 'stop_lat': '50'},
            {'stop_id': ' StopPoint:P ', 'stop_name': ' PLATFORM ', 'parent_station': ' StopArea:S ', 'stop_lat': '50'},
        ]),
        'trips': pd.DataFrame([{'trip_id': ' T ', 'route_id': ' R ', 'service_id': ' 001 ',
            'shape_id': ' shape ', 'trip_headsign': ' Town '}]),
        'stop_times': pd.DataFrame([{'trip_id': ' T ', 'stop_id': ' StopPoint:P ',
            'arrival_time': ' 25:10:00 ', 'departure_time': ' 25:11:00 ', 'stop_sequence': '0',
            'stop_headsign': '', 'pickup_type': '0', 'drop_off_type': '0', 'shape_dist_traveled': ' 2 '}]),
    }


def run_silver_tasks(dag, inputs, run_id):
    from core.railway.transformation.silver import SOURCE_TABLES
    return [path for name in SOURCE_TABLES
            if (path := dag.get_task(f'transform_{name}').python_callable(inputs, run_id, name)) is not None]


def run_gold_tasks(dag, processed, run_id):
    dimensions = [dag.get_task(f'transform_{name}').python_callable(processed, run_id)
                  for name in ['dim_route', 'dim_station', 'dim_trip']]
    service_dates = dag.get_task('transform_fact_service_date').python_callable(processed, run_id)
    stops = dag.get_task('transform_fact_stop_time').python_callable(processed, run_id, *dimensions)
    return [*dimensions, service_dates, stops]


class LayerTests(unittest.TestCase):
    def setUp(self):
        self.silver = {name: clean_source(name, frame) for name, frame in sources().items()}

    def test_silver_preserves_source_grains_ids_and_attributes(self):
        self.assertEqual(len(self.silver['stops']), 2)
        self.assertEqual(self.silver['stops'].iloc[1]['parent_station'], 'StopArea:S')
        self.assertEqual(self.silver['trips'].iloc[0]['route_id'], 'R')
        self.assertEqual(self.silver['trips'].iloc[0]['shape_id'], 'shape')
        self.assertEqual(self.silver['trips'].iloc[0]['service_id'], '001')
        self.assertEqual(self.silver['routes'].iloc[0]['route_short_name'], 'express')
        self.assertEqual(str(self.silver['routes']['route_type'].dtype), 'Int64')
        self.assertEqual(self.silver['stop_times'].iloc[0]['arrival_time'], '25:10:00')
        for name, frame in self.silver.items():
            self.assertFalse(any(column.endswith('_key') for column in frame.columns))
            assert_frame_equal(frame, clean_source(name, frame))

    def test_keys_survive_reordering_new_rows_and_retries(self):
        cases = [
            ('routes', build_dim_route, 'route_id', 'route_key', {'agency_df': self.silver['agency']}),
            ('trips', build_dim_trip, 'trip_id', 'trip_key', {}),
            ('stops', build_dim_station, 'stop_id', 'station_key', {}),
        ]
        for name, builder, identifier, key, kwargs in cases:
            with self.subTest(name=name):
                current = self.silver[name]
                old = builder(current, **kwargs)
                old[key] += 100
                added = current.iloc[[0]].copy()
                added[identifier] = 'StopArea:NEW' if name == 'stops' else 'NEW'
                updated = pd.concat([added, current.iloc[::-1]], ignore_index=True)
                result = builder(updated, existing_dim=old, **kwargs)
                business_key = 'station_id' if name == 'stops' else identifier
                self.assertEqual(result.set_index(business_key).loc[old[business_key].iloc[0], key],
                                 old[key].iloc[0])
                self.assertEqual(result[key].max(), old[key].max() + 1)
                assert_frame_equal(result, builder(updated, existing_dim=result, **kwargs))

    def test_gold_resolves_platform_visit_and_rejects_unresolved_keys(self):
        s = self.silver
        kwargs = dict(stop_times_df=s['stop_times'], trips_df=s['trips'], stops_df=s['stops'],
            dim_trip=build_dim_trip(s['trips']), dim_route=build_dim_route(s['routes'], s['agency']),
            dim_station=build_dim_station(s['stops']))
        fact = build_fact_stop_time(**kwargs)
        self.assertEqual(len(fact), 1)
        self.assertEqual(fact.iloc[0]['station_key'], kwargs['dim_station'].iloc[0]['station_key'])
        self.assertNotIn('stop_id', fact.columns)
        kwargs['dim_station'] = kwargs['dim_station'].iloc[:0]
        with self.assertRaisesRegex(ValueError, 'Unresolved station_key'):
            build_fact_stop_time(**kwargs)

    def test_retired_routes_keep_agency_attributes(self):
        s = self.silver
        old = build_dim_route(s['routes'], s['agency'])
        result = build_dim_route(s['routes'].iloc[:0], s['agency'].iloc[:0], existing_dim=old)
        assert_frame_equal(old, result)

    def test_current_routes_cannot_resolve_agencies_from_old_feed(self):
        s = self.silver
        old = build_dim_route(s['routes'], s['agency'])
        with self.assertRaisesRegex(ValueError, 'matching source agency'):
            build_dim_route(s['routes'], s['agency'].iloc[:0], existing_dim=old)

    def test_dag_dependencies_separate_silver_from_gold(self):
        from core.railway.pipelines.railway_gtfs_pipeline import railway_pipeline
        dag = railway_pipeline()
        from core.railway.transformation.silver import SOURCE_TABLES
        silver_tasks = {f'transform_{name}' for name in SOURCE_TABLES}
        gold_tasks = {f'transform_{name}' for name in
                      ['dim_route', 'dim_station', 'dim_trip', 'fact_service_date', 'fact_stop_time']}
        self.assertNotIn('transform_silver', dag.task_ids)
        self.assertNotIn('transform_curated', dag.task_ids)
        for name in silver_tasks:
            self.assertEqual(dag.get_task(name).upstream_task_ids, {'source_data_quality'})
        self.assertEqual(dag.get_task('publish_silver_minio').upstream_task_ids, silver_tasks)
        for name in gold_tasks - {'transform_fact_stop_time'}:
            self.assertEqual(dag.get_task(name).upstream_task_ids, {'publish_silver_minio'})
        self.assertEqual(dag.get_task('transform_fact_stop_time').upstream_task_ids,
                         {'publish_silver_minio', 'transform_dim_route', 'transform_dim_station', 'transform_dim_trip'})
        self.assertEqual(dag.get_task('publish_gold_minio').upstream_task_ids, gold_tasks)
        for name in silver_tasks | gold_tasks | {'publish_silver_minio', 'publish_gold_minio'}:
            self.assertIn('{{ run_id }}', dag.get_task(name).op_args)

    def test_task_arguments_do_not_collide_with_airflow_context(self):
        from airflow.sdk.bases.decorator import KeywordParameters
        from airflow.sdk.definitions.context import KNOWN_CONTEXT_KEYS
        from core.railway.pipelines.railway_gtfs_pipeline import railway_pipeline
        dag = railway_pipeline()
        context = {key: None for key in KNOWN_CONTEXT_KEYS}
        context['run_id'] = 'manual__regression'
        for task in dag.tasks:
            with self.subTest(task=task.task_id):
                # Exercise the same argument resolver that failed before execution.
                KeywordParameters.determine(task.python_callable, task.op_args,
                                            {**context, **task.op_kwargs})

    def test_extract_and_csv_conversion_are_scoped_to_the_supplied_run(self):
        from zipfile import ZipFile
        from core.railway.ingestion.gtfs import extract_gtfs_archive, convert_to_csv
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive = root/'raw'/'first'/'feed.zip'
            archive.parent.mkdir(parents=True)
            with ZipFile(archive, 'w') as output:
                output.writestr('trips.txt', 'trip_id,service_id\nT,001\n')
            for run in ['first', 'second']:
                stage = root/'staging'/run
                files = extract_gtfs_archive(archive, stage)
                csv_files = convert_to_csv(files)
                self.assertEqual(csv_files, [stage/'trips.csv'])
                self.assertEqual(pd.read_csv(csv_files[0], dtype='string').iloc[0]['service_id'], '001')
            self.assertFalse((root/'staging'/'trips.csv').exists())

