'''
Shared UCC account/config access for the HoneyDB inputs.
'''
import logging

import import_declare_test # noqa: F401  pylint: disable=unused-import,import-error
from solnlib import conf_manager, log # pylint: disable=import-error

ADDON_NAME = "splunk_ta_honeydb"
ACCOUNT_CONF = "splunk_ta_honeydb_account"
SETTINGS_CONF = "splunk_ta_honeydb_settings"


def logger_for_input(input_name):
    '''Framework logger for one input instance.'''
    return log.Logs().get_logger(f"{ADDON_NAME.lower()}_{input_name}")


def set_log_level(logger, session_key):
    '''Apply the log level configured on the add-on's logging tab.'''
    try:
        log_level = conf_manager.get_log_level(
            logger=logger,
            session_key=session_key,
            app_name=ADDON_NAME,
            conf_name=SETTINGS_CONF,
        )
        logger.setLevel(log_level)
    except Exception: # pylint: disable=broad-exception-caught
        logger.setLevel(logging.INFO)


def get_account(session_key, account_name):
    '''
    Return the account stanza (api_id, decrypted api_key, subscription)
    for account_name from the add-on's encrypted account storage.
    '''
    cfm = conf_manager.ConfManager(
        session_key,
        ADDON_NAME,
        realm=f"__REST_CREDENTIAL__#{ADDON_NAME}#configs/conf-{ACCOUNT_CONF}",
    )
    account_conf_file = cfm.get_conf(ACCOUNT_CONF)
    return account_conf_file.get(account_name)


def api_headers(account):
    '''HoneyDB API auth headers for the given account stanza.'''
    # local import so this module's import doesn't require honeydb_utils
    from honeydb_utils import ADDON_VERSION # pylint: disable=import-outside-toplevel
    return {
        'X-HoneyDb-ApiId': str(account.get("api_id", "")),
        'X-HoneyDb-ApiKey': str(account.get("api_key", "")),
        'User-Agent': f'HoneyDB Splunk App/{ADDON_VERSION}',
    }
