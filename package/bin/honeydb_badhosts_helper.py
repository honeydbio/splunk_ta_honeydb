'''
HoneyDB bad-hosts modular input: pull the bad-hosts feed and index it.
'''
import json

import import_declare_test # noqa: F401  pylint: disable=unused-import,import-error
from solnlib import log # pylint: disable=import-error
from splunklib import modularinput as smi # pylint: disable=import-error

import honeydb_account
import honeydb_utils

SOURCETYPE = "honeydb_badhosts"


def validate_input(definition: smi.ValidationDefinition): # pylint: disable=unused-argument
    '''No extra validation beyond the UI validators.'''
    return


def stream_events(inputs: smi.InputDefinition, event_writer: smi.EventWriter):
    '''Fetch the bad-hosts feed once per scheduled run, per input.'''
    for input_name, input_item in inputs.inputs.items():
        normalized_input_name = input_name.split("/")[-1]
        logger = honeydb_account.logger_for_input(normalized_input_name)
        try:
            session_key = inputs.metadata["session_key"]
            honeydb_account.set_log_level(logger, session_key)
            log.modular_input_start(logger, normalized_input_name)

            account = honeydb_account.get_account(session_key, input_item.get("account"))
            headers = honeydb_account.api_headers(account)

            url = f'{honeydb_utils.API_BASE}/bad-hosts'
            logger.info("Bad Hosts: Calling API with : %s ", url)
            response = honeydb_utils.get_with_retry(url, headers, logger, "Bad Hosts")
            if response is None:
                continue
            if response.status_code != 200:
                logger.error("Bad Hosts Error: API error with status code: %s ", response.status_code)
                continue

            badhosts = response.json()
            for host in badhosts:
                event_writer.write_event(
                    smi.Event(
                        data=json.dumps(host, ensure_ascii=False, default=str),
                        index=input_item.get("index"),
                        sourcetype=SOURCETYPE,
                    )
                )
            log.events_ingested(
                logger,
                input_name,
                SOURCETYPE,
                len(badhosts),
                input_item.get("index"),
                account=input_item.get("account"),
            )
            log.modular_input_end(logger, normalized_input_name)
        except Exception as exception: # pylint: disable=broad-exception-caught
            log.log_exception(logger, exception, "badhosts error",
                              msg_before="Exception raised while ingesting bad hosts: ")
