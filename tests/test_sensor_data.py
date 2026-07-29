'''Unit tests for spl_honeydb_sensor_data checkpoint and date logic.'''
import os
import sys
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_HERE, 'stubs'))
sys.path.insert(0, os.path.join(_ROOT, 'splunk_ta_honeydb', 'lib'))
sys.path.insert(0, os.path.join(_ROOT, 'splunk_ta_honeydb', 'bin'))

import spl_honeydb_sensor_data as sensor  # noqa: E402  pylint: disable=wrong-import-position

TODAY = '2026-07-29'


class ParseCheckpointTests(unittest.TestCase):

    def test_empty_and_none(self):
        self.assertEqual(sensor.parse_checkpoint('', TODAY), (TODAY, 0))
        self.assertEqual(sensor.parse_checkpoint(None, TODAY), (TODAY, 0))
        self.assertEqual(sensor.parse_checkpoint('   \n', TODAY), (TODAY, 0))

    def test_legacy_bare_int(self):
        self.assertEqual(sensor.parse_checkpoint('413326453', TODAY), (TODAY, 413326453))
        self.assertEqual(sensor.parse_checkpoint('  0\n', TODAY), (TODAY, 0))

    def test_json_format(self):
        self.assertEqual(
            sensor.parse_checkpoint('{"date": "2026-07-28", "from_id": 42}', TODAY),
            ('2026-07-28', 42))
        self.assertEqual(
            sensor.parse_checkpoint('{"date": "2026-07-28", "from_id": "42"}', TODAY),
            ('2026-07-28', 42))

    def test_corrupt_falls_back_to_today(self):
        corrupt = [
            '{"date": "bogus", "from_id": 1}',
            '{"from_id": 1}',
            '{"date": "2026-07-28"}',
            'not json {',
            '{"date": null, "from_id": 1}',
        ]
        for text in corrupt:
            with self.subTest(text=text):
                self.assertEqual(sensor.parse_checkpoint(text, TODAY), (TODAY, 0))

    def test_round_trip(self):
        text = sensor.serialize_checkpoint('2026-07-28', 99)
        self.assertEqual(sensor.parse_checkpoint(text, TODAY), ('2026-07-28', 99))


class NextDateTests(unittest.TestCase):

    def test_boundaries(self):
        self.assertEqual(sensor.next_date('2026-07-28'), '2026-07-29')
        self.assertEqual(sensor.next_date('2026-07-31'), '2026-08-01')
        self.assertEqual(sensor.next_date('2026-12-31'), '2027-01-01')
        self.assertEqual(sensor.next_date('2028-02-28'), '2028-02-29')
        self.assertEqual(sensor.next_date('2027-02-28'), '2027-03-01')


if __name__ == '__main__':
    unittest.main()
