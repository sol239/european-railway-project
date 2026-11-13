import unittest

import pandas as pd

from core.railway.transformation import build_fact_service_date


class ServiceDatesTests(unittest.TestCase):
    def test_exceptions_without_weekly_calendar(self):
        source = pd.DataFrame([
            ['001', '20261025', '1'],
            ['001', '20261026', '2'],
            ['002', '20261025', '1'],
        ], columns=['service_id', 'date', 'exception_type'])
        result = build_fact_service_date(source)
        self.assertEqual(result['service_id'].tolist(), ['001', '002'])
        self.assertEqual(result['service_date'].astype(str).tolist(), ['2026-10-25'] * 2)

    def test_weekly_calendar_with_addition_and_removal(self):
        calendar = pd.DataFrame([{
            'service_id': '001', 'start_date': '20261019', 'end_date': '20261025',
            **{day: '1' if day == 'monday' else '0' for day in
               ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday']},
        }])
        exceptions = pd.DataFrame([
            ['001', '20261019', '2'], ['001', '20261025', '1'],
        ], columns=['service_id', 'date', 'exception_type'])
        result = build_fact_service_date(exceptions, calendar)
        self.assertEqual(result['service_date'].astype(str).tolist(), ['2026-10-25'])

    def test_conflicting_exceptions_fail(self):
        source = pd.DataFrame([
            ['001', '20261025', '1'], ['001', '20261025', '2'],
        ], columns=['service_id', 'date', 'exception_type'])
        with self.assertRaises(ValueError):
            build_fact_service_date(source)

    def test_empty_calendar_keeps_columns(self):
        source = pd.DataFrame(columns=['service_id', 'date', 'exception_type'])
        self.assertEqual(build_fact_service_date(source).columns.tolist(),
                         ['service_id', 'service_date'])


if __name__ == '__main__':
    unittest.main()
