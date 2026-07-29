'''
Shared helpers for the HoneyDB scripted inputs: credential loading
(Splunk credential store with honeydb.json fallback) and checkpoint
path resolution/migration.

Callers must insert the app's lib/ directory into sys.path before
importing this module (it needs the vendored requests library).
'''
import os
import sys
import json

import requests # pylint: disable=wrong-import-order
import urllib3 # pylint: disable=wrong-import-order

REALM = "splunk_ta_honeydb"
APP = "splunk_ta_honeydb"


def get_session_key():
    '''
    Read the splunkd session key that passAuth writes to stdin at launch.
    Returns "" when not available (manual/interactive runs).
    '''
    try:
        if sys.stdin.isatty():
            return ""
        return sys.stdin.readline().strip()
    except OSError:
        return ""


def get_mgmt_host_port(cli):
    '''
    Resolve the local splunkd management host:port from web.conf,
    defaulting to 127.0.0.1:8089.
    '''
    try:
        host_port = cli.getConfKeyValue("web", "settings", "mgmtHostPort")
        if host_port:
            return host_port
    except Exception: # pylint: disable=broad-exception-caught
        pass
    return "127.0.0.1:8089"


def credentials_from_store(session_key, mgmt_host_port, logger):
    '''
    Fetch the HoneyDB credential (realm splunk_ta_honeydb) from Splunk's
    credential store. Returns (api_id, api_key) or (None, None).
    '''
    if not session_key:
        return None, None

    url = f'https://{mgmt_host_port}/servicesNS/nobody/{APP}/storage/passwords?output_mode=json&count=0'
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    try:
        response = requests.get(url, headers={'Authorization': f'Splunk {session_key}'},
                                verify=False, timeout=10)
    except requests.exceptions.RequestException as requesterror:
        logger.error("Credential store request failed : %s", requesterror)
        return None, None

    if response.status_code != 200:
        logger.error("Credential store request returned status code: %s", response.status_code)
        return None, None

    try:
        for entry in response.json().get('entry', []):
            content = entry.get('content', {})
            if content.get('realm') == REALM:
                return content.get('username'), content.get('clear_password')
    except (ValueError, AttributeError, TypeError) as parseerror:
        logger.error("Credential store response parse error : %s", parseerror)

    return None, None


def read_config_file(script_dir, logger, label):
    '''
    Read and parse bin/honeydb.json. Returns a dict ({} on any failure).
    '''
    jsonfile = os.path.join(script_dir, "honeydb.json")

    try:
        with open(jsonfile, 'r', encoding='utf-8') as argfile:
            return json.loads(argfile.read())
    except OSError:
        logger.info("%s: HoneyDB args file not readable : ./%s ", label, jsonfile)
    except ValueError as jsonerror:
        logger.error("%s Error: File %s data read error %s ", label, jsonfile, jsonerror)
    return {}


def load_credentials(script_dir, cli, logger, label):
    '''
    Load HoneyDB API credentials: Splunk credential store first, then
    bin/honeydb.json. Returns (api_id, api_key, subscription, source)
    where source is "credential store" or "honeydb.json"; api_id/api_key
    are "" when neither source has them.
    '''
    config = read_config_file(script_dir, logger, label)
    subscription = str(config.get("subscription", "community") or "community")

    session_key = get_session_key()
    api_id, api_key = credentials_from_store(session_key, get_mgmt_host_port(cli), logger)
    if api_id and api_key:
        return str(api_id), str(api_key), subscription, "credential store"

    api_id = str(config.get("X-HoneyDb-ApiId", "") or "")
    api_key = str(config.get("X-HoneyDb-ApiKey", "") or "")
    return api_id, api_key, subscription, "honeydb.json"


def checkpoint_dir(script_dir):
    '''
    Resolve the checkpoint directory outside the app dir:
    $SPLUNK_HOME/var/lib/splunk/splunk_ta_honeydb (SPLUNK_HOME is always
    set for scripted inputs; falls back to a path relative to bin/).
    '''
    splunk_home = os.environ.get("SPLUNK_HOME")
    if not splunk_home:
        splunk_home = os.path.join(script_dir, "..", "..", "..", "..")
    return os.path.join(splunk_home, "var", "lib", "splunk", APP)


def resolve_checkpoint_file(script_dir, logger):
    '''
    Return the checkpoint file path, creating its directory and migrating
    a legacy bin/from_id file on first use. Falls back to the legacy path
    if the new directory cannot be created.
    '''
    legacy_file = os.path.join(script_dir, "from_id")
    new_file = os.path.join(checkpoint_dir(script_dir), "from_id")

    try:
        os.makedirs(os.path.dirname(new_file), exist_ok=True)
    except OSError as oserror:
        logger.error("Checkpoint directory not creatable (%s); using legacy path : %s", oserror, legacy_file)
        return legacy_file

    if not os.path.exists(new_file) and os.path.exists(legacy_file):
        try:
            with open(legacy_file, 'r', encoding='utf-8') as oldfile:
                content = oldfile.read()
            with open(new_file, 'w', encoding='utf-8') as newfile:
                newfile.write(content)
            logger.info("Migrated checkpoint from %s to %s", legacy_file, new_file)
        except OSError as oserror:
            logger.error("Checkpoint migration failed (%s); using legacy path : %s", oserror, legacy_file)
            return legacy_file

    return new_file
