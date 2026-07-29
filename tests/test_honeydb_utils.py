'''Unit tests for honeydb_utils: checkpoints, dates, retry, drain loop.'''
import logging
import os
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_ROOT, 'package', 'bin'))

import requests  # noqa: E402  pylint: disable=wrong-import-position
import honeydb_utils as hu  # noqa: E402  pylint: disable=wrong-import-position

logging.disable(logging.CRITICAL)
LOG = logging.getLogger('test')

TODAY = '2026-07-29'


class ParseCheckpointTests(unittest.TestCase):

    def test_empty_and_none(self):
        self.assertEqual(hu.parse_checkpoint('', TODAY), (TODAY, 0))
        self.assertEqual(hu.parse_checkpoint(None, TODAY), (TODAY, 0))

    def test_legacy_bare_int(self):
        self.assertEqual(hu.parse_checkpoint('413326453', TODAY), (TODAY, 413326453))

    def test_json_format(self):
        self.assertEqual(
            hu.parse_checkpoint('{"date": "2026-07-28", "from_id": 42}', TODAY),
            ('2026-07-28', 42))

    def test_corrupt_falls_back_to_today(self):
        for text in ('{"date": "bogus", "from_id": 1}', '{"from_id": 1}',
                     '{"date": "2026-07-28"}', 'not json {',
                     '{"date": null, "from_id": 1}'):
            with self.subTest(text=text):
                self.assertEqual(hu.parse_checkpoint(text, TODAY), (TODAY, 0))

    def test_round_trip(self):
        text = hu.serialize_checkpoint('2026-07-28', 99)
        self.assertEqual(hu.parse_checkpoint(text, TODAY), ('2026-07-28', 99))


class NextDateTests(unittest.TestCase):

    def test_boundaries(self):
        self.assertEqual(hu.next_date('2026-07-28'), '2026-07-29')
        self.assertEqual(hu.next_date('2026-07-31'), '2026-08-01')
        self.assertEqual(hu.next_date('2026-12-31'), '2027-01-01')
        self.assertEqual(hu.next_date('2028-02-28'), '2028-02-29')


class CheckpointFileTests(unittest.TestCase):

    def test_path_and_io(self):
        with tempfile.TemporaryDirectory() as tmp:
            os.environ['SPLUNK_HOME'] = tmp
            try:
                path = hu.checkpoint_file()
                self.assertEqual(path, os.path.join(
                    tmp, 'var', 'lib', 'splunk', 'splunk_ta_honeydb', 'from_id'))
                self.assertEqual(hu.read_checkpoint(path), '')
                hu.write_checkpoint(path, '2026-07-28', 7)
                self.assertEqual(hu.parse_checkpoint(hu.read_checkpoint(path), TODAY),
                                 ('2026-07-28', 7))
            finally:
                del os.environ['SPLUNK_HOME']


class FakeResponse:
    def __init__(self, status, retry_after=None):
        self.status_code = status
        self.headers = {'Retry-After': retry_after} if retry_after else {}


class RetryTests(unittest.TestCase):

    def setUp(self):
        self.sleeps = []
        self.real_get = requests.get
        self.real_sleep = hu.time.sleep
        hu.time.sleep = self.sleeps.append

    def tearDown(self):
        requests.get = self.real_get
        hu.time.sleep = self.real_sleep

    def script(self, items):
        state = {'n': 0}

        def fake_get(_url, headers=None, timeout=None):  # pylint: disable=unused-argument
            item = items[state['n']]
            state['n'] += 1
            if isinstance(item, Exception):
                raise item
            return item
        requests.get = fake_get

    def test_retry_on_500_then_200(self):
        self.script([FakeResponse(500), FakeResponse(200)])
        self.assertEqual(hu.get_with_retry('u', {}, LOG, 'T').status_code, 200)
        self.assertEqual(self.sleeps, [2])

    def test_no_retry_on_404(self):
        self.script([FakeResponse(404)])
        self.assertEqual(hu.get_with_retry('u', {}, LOG, 'T').status_code, 404)
        self.assertEqual(self.sleeps, [])

    def test_retry_after_honored_and_capped(self):
        self.script([FakeResponse(429, '5'), FakeResponse(429, '9999'), FakeResponse(200)])
        self.assertEqual(hu.get_with_retry('u', {}, LOG, 'T').status_code, 200)
        self.assertEqual(self.sleeps, [5, hu.RETRY_AFTER_CAP])

    def test_none_after_exhausted_exceptions(self):
        self.script([requests.exceptions.Timeout('t')] * 4)
        self.assertIsNone(hu.get_with_retry('u', {}, LOG, 'T'))
        self.assertEqual(self.sleeps, [2, 4, 8])

    def test_persistent_503_returns_last_response(self):
        self.script([FakeResponse(503)] * 4)
        self.assertEqual(hu.get_with_retry('u', {}, LOG, 'T').status_code, 503)
        self.assertEqual(len(self.sleeps), 3)


class DrainTests(unittest.TestCase):
    '''drain_sensor_data against an in-memory API and checkpoint.'''

    def setUp(self):
        self.ckpt = {'text': ''}
        self.emitted = []

    def read_ckpt(self):
        return self.ckpt['text']

    def write_ckpt(self, date_str, from_id):
        self.ckpt['text'] = hu.serialize_checkpoint(date_str, from_id)

    def emit(self, row):
        self.emitted.append(row)

    @staticmethod
    def paged_api(data_by_date, page_size=2):
        '''fetch_page over {date: [(id, row), ...]} with from-id filtering.'''
        def fetch_page(date_str, from_id):
            remaining = [(i, r) for i, r in data_by_date.get(date_str, [])
                         if i > from_id]
            page = remaining[:page_size]
            if not page:
                return [], from_id
            return [r for _, r in page], page[-1][0]
        return fetch_page

    def test_single_day_multi_page_drain(self):
        data = {TODAY: [(i, {'id': i}) for i in range(1, 6)]}
        pages = hu.drain_sensor_data(self.paged_api(data), self.emit,
                                     self.read_ckpt, self.write_ckpt, TODAY, LOG)
        self.assertEqual(len(self.emitted), 5)
        self.assertEqual(pages, 4)  # 3 data pages + 1 empty terminal page
        self.assertEqual(hu.parse_checkpoint(self.ckpt['text'], TODAY), (TODAY, 5))

    def test_rollover_drains_previous_day_first(self):
        yesterday = '2026-07-28'
        data = {
            yesterday: [(101, {'d': 'y1'}), (102, {'d': 'y2'})],
            TODAY: [(201, {'d': 't1'})],
        }
        self.write_ckpt(yesterday, 100)
        hu.drain_sensor_data(self.paged_api(data), self.emit,
                             self.read_ckpt, self.write_ckpt, TODAY, LOG)
        self.assertEqual([r['d'] for r in self.emitted], ['y1', 'y2', 't1'])
        self.assertEqual(hu.parse_checkpoint(self.ckpt['text'], TODAY), (TODAY, 201))

    def test_page_cap_resumes_next_run(self):
        data = {TODAY: [(i, {'id': i}) for i in range(1, 100)]}
        pages = hu.drain_sensor_data(self.paged_api(data), self.emit,
                                     self.read_ckpt, self.write_ckpt, TODAY, LOG,
                                     max_pages=3)
        self.assertEqual(pages, 3)
        self.assertEqual(len(self.emitted), 6)
        # second run continues where the first stopped
        hu.drain_sensor_data(self.paged_api(data), self.emit,
                             self.read_ckpt, self.write_ckpt, TODAY, LOG,
                             max_pages=100)
        self.assertEqual(len(self.emitted), 99)

    def test_stalled_from_id_stops_run(self):
        def stalled(_date, from_id):
            return [{'x': 1}], from_id  # rows but no advance
        pages = hu.drain_sensor_data(stalled, self.emit,
                                     self.read_ckpt, self.write_ckpt, TODAY, LOG)
        self.assertEqual(pages, 1)
        self.assertEqual(len(self.emitted), 1)
        self.assertEqual(self.ckpt['text'], '')  # checkpoint not rewritten

    def test_legacy_checkpoint_resumes_today(self):
        self.ckpt['text'] = '50'
        data = {TODAY: [(51, {'id': 51}), (52, {'id': 52})]}
        hu.drain_sensor_data(self.paged_api(data), self.emit,
                             self.read_ckpt, self.write_ckpt, TODAY, LOG)
        self.assertEqual(len(self.emitted), 2)
        self.assertEqual(hu.parse_checkpoint(self.ckpt['text'], TODAY), (TODAY, 52))


if __name__ == '__main__':
    unittest.main()
