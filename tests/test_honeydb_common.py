'''Unit tests for honeydb_common: credentials, checkpoint paths, retry.'''
import json
import logging
import os
import sys
import tempfile
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_HERE, 'stubs'))
sys.path.insert(0, os.path.join(_ROOT, 'splunk_ta_honeydb', 'lib'))
sys.path.insert(0, os.path.join(_ROOT, 'splunk_ta_honeydb', 'bin'))

import requests  # noqa: E402  pylint: disable=wrong-import-position
import honeydb_common as hc  # noqa: E402  pylint: disable=wrong-import-position

logging.disable(logging.CRITICAL)
LOG = logging.getLogger('test')


class CliStub:
    @staticmethod
    def getConfKeyValue(*_args):
        return '127.0.0.1:8089'


class RaisingCli:
    @staticmethod
    def getConfKeyValue(*_args):
        raise RuntimeError('no conf')


class CredentialAndConfigTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        self.bindir = os.path.join(self.tmp.name, 'etc', 'apps', 'app', 'bin')
        os.makedirs(self.bindir)

    def tearDown(self):
        self.tmp.cleanup()

    def write_config(self, config):
        with open(os.path.join(self.bindir, 'honeydb.json'), 'w', encoding='utf-8') as f:
            json.dump(config, f)

    def test_fallback_to_config_file(self):
        self.write_config({'X-HoneyDb-ApiId': 'id1', 'X-HoneyDb-ApiKey': 'key1',
                           'subscription': 'gold'})
        result = hc.load_credentials(self.bindir, CliStub, LOG, 'Test')
        self.assertEqual(result, ('id1', 'key1', 'gold', 'honeydb.json'))

    def test_missing_config_file(self):
        api_id, api_key, subscription, _ = hc.load_credentials(
            os.path.join(self.tmp.name, 'nowhere'), CliStub, LOG, 'Test')
        self.assertEqual((api_id, api_key, subscription), ('', '', 'community'))

    def test_default_subscription(self):
        self.write_config({'X-HoneyDb-ApiId': 'a', 'X-HoneyDb-ApiKey': 'b'})
        _, _, subscription, _ = hc.load_credentials(self.bindir, CliStub, LOG, 'Test')
        self.assertEqual(subscription, 'community')

    def test_mgmt_host_port_fallback(self):
        self.assertEqual(hc.get_mgmt_host_port(RaisingCli), '127.0.0.1:8089')
        self.assertEqual(hc.get_mgmt_host_port(CliStub), '127.0.0.1:8089')


class CheckpointPathTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()  # pylint: disable=consider-using-with
        self.bindir = os.path.join(self.tmp.name, 'etc', 'apps', 'app', 'bin')
        os.makedirs(self.bindir)
        os.environ['SPLUNK_HOME'] = self.tmp.name

    def tearDown(self):
        del os.environ['SPLUNK_HOME']
        self.tmp.cleanup()

    def new_path(self):
        return os.path.join(self.tmp.name, 'var', 'lib', 'splunk',
                            'splunk_ta_honeydb', 'from_id')

    def test_fresh_resolution_creates_dir(self):
        path = hc.resolve_checkpoint_file(self.bindir, LOG)
        self.assertEqual(path, self.new_path())
        self.assertTrue(os.path.isdir(os.path.dirname(path)))
        self.assertFalse(os.path.exists(path))

    def test_legacy_migration(self):
        with open(os.path.join(self.bindir, 'from_id'), 'w', encoding='utf-8') as f:
            f.write('{"date": "2026-07-28", "from_id": 123}')
        path = hc.resolve_checkpoint_file(self.bindir, LOG)
        with open(path, encoding='utf-8') as f:
            self.assertEqual(f.read(), '{"date": "2026-07-28", "from_id": 123}')

    def test_migration_never_overwrites(self):
        os.makedirs(os.path.dirname(self.new_path()))
        with open(self.new_path(), 'w', encoding='utf-8') as f:
            f.write('EXISTING')
        with open(os.path.join(self.bindir, 'from_id'), 'w', encoding='utf-8') as f:
            f.write('LEGACY')
        path = hc.resolve_checkpoint_file(self.bindir, LOG)
        with open(path, encoding='utf-8') as f:
            self.assertEqual(f.read(), 'EXISTING')


class FakeResponse:
    def __init__(self, status, retry_after=None):
        self.status_code = status
        self.headers = {'Retry-After': retry_after} if retry_after else {}


class RetryTests(unittest.TestCase):

    def setUp(self):
        self.sleeps = []
        self.real_get = requests.get
        self.real_sleep = hc.time.sleep
        hc.time.sleep = self.sleeps.append

    def tearDown(self):
        requests.get = self.real_get
        hc.time.sleep = self.real_sleep

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
        response = hc.get_with_retry('u', {}, LOG, 'T')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.sleeps, [2])

    def test_retry_on_exception_then_200(self):
        self.script([requests.exceptions.ConnectionError('x'), FakeResponse(200)])
        response = hc.get_with_retry('u', {}, LOG, 'T')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.sleeps, [2])

    def test_no_retry_on_404(self):
        self.script([FakeResponse(404)])
        response = hc.get_with_retry('u', {}, LOG, 'T')
        self.assertEqual(response.status_code, 404)
        self.assertEqual(self.sleeps, [])

    def test_retry_after_honored_and_capped(self):
        self.script([FakeResponse(429, '5'), FakeResponse(429, '9999'), FakeResponse(200)])
        response = hc.get_with_retry('u', {}, LOG, 'T')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.sleeps, [5, hc.RETRY_AFTER_CAP])

    def test_none_after_exhausted_exceptions(self):
        self.script([requests.exceptions.Timeout('t')] * 4)
        response = hc.get_with_retry('u', {}, LOG, 'T')
        self.assertIsNone(response)
        self.assertEqual(self.sleeps, [2, 4, 8])

    def test_persistent_503_returns_last_response(self):
        self.script([FakeResponse(503)] * 4)
        response = hc.get_with_retry('u', {}, LOG, 'T')
        self.assertEqual(response.status_code, 503)
        self.assertEqual(len(self.sleeps), 3)


if __name__ == '__main__':
    unittest.main()
