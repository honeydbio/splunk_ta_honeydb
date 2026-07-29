'''
HoneyDB sensor-data modular input: paginated drain with UTC-rollover
checkpointing (logic in honeydb_utils.drain_sensor_data).
'''
import json
from datetime import datetime, timezone

import import_declare_test # noqa: F401  pylint: disable=unused-import,import-error
from solnlib import log # pylint: disable=import-error
from splunklib import modularinput as smi # pylint: disable=import-error

import honeydb_account
import honeydb_utils

SOURCETYPE = "honeydb_sensor_data"


def validate_input(definition: smi.ValidationDefinition): # pylint: disable=unused-argument
    '''No extra validation beyond the UI validators.'''
    return


def make_fetch_page(headers, subscription, logger):
    '''Build the fetch_page(date, from_id) callable for the drain loop.'''
    mydata = "" if subscription.lower() == "gold" else "/mydata"

    def fetch_page(date_str, from_id):
        url = (f'{honeydb_utils.API_BASE}/sensor-data{mydata}'
               f'?sensor-data-date={date_str}&from-id={from_id}')
        logger.info("Sensor Data: Calling API with : %s ", url)
        response = honeydb_utils.get_with_retry(url, headers, logger, "Sensor Data")
        if response is None:
            raise honeydb_utils.ApiError("API unreachable after retries")
        if response.status_code != 200:
            raise honeydb_utils.ApiError(f"API status {response.status_code}")
        try:
            payload = response.json()
            rows = payload[0]['data'] if payload else []
            new_from_id = payload[1]['from_id'] if payload else 0
        except (ValueError, IndexError, KeyError, TypeError) as shapeerror:
            raise honeydb_utils.ApiError(f"unexpected API response structure: {shapeerror}") from shapeerror
        return rows, new_from_id

    return fetch_page


def process_input(input_name, input_item, session_key, event_writer, logger):
    '''Drain sensor-data pages for one configured input.'''
    account = honeydb_account.get_account(session_key, input_item.get("account"))
    headers = honeydb_account.api_headers(account)
    subscription = str(account.get("subscription", "community") or "community")

    ckpt_path = honeydb_utils.checkpoint_file()
    emitted = {'count': 0}

    def emit(row):
        event_writer.write_event(
            smi.Event(
                data=json.dumps(row, ensure_ascii=False, default=str),
                index=input_item.get("index"),
                sourcetype=SOURCETYPE,
            )
        )
        emitted['count'] += 1

    def read_ckpt():
        return honeydb_utils.read_checkpoint(ckpt_path)

    def write_ckpt(date_str, from_id):
        honeydb_utils.write_checkpoint(ckpt_path, date_str, from_id)

    today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    honeydb_utils.drain_sensor_data(
        fetch_page=make_fetch_page(headers, subscription, logger),
        emit=emit,
        read_ckpt=read_ckpt,
        write_ckpt=write_ckpt,
        today=today_utc,
        logger=logger,
    )
    log.events_ingested(
        logger,
        input_name,
        SOURCETYPE,
        emitted['count'],
        input_item.get("index"),
        account=input_item.get("account"),
    )


def stream_events(inputs: smi.InputDefinition, event_writer: smi.EventWriter):
    '''Drain sensor-data pages per input, checkpointed across runs.'''
    for input_name, input_item in inputs.inputs.items():
        normalized_input_name = input_name.split("/")[-1]
        logger = honeydb_account.logger_for_input(normalized_input_name)
        try:
            session_key = inputs.metadata["session_key"]
            honeydb_account.set_log_level(logger, session_key)
            log.modular_input_start(logger, normalized_input_name)
            process_input(input_name, input_item, session_key, event_writer, logger)
            log.modular_input_end(logger, normalized_input_name)
        except honeydb_utils.ApiError as apierror:
            logger.error("Sensor Data Error: %s", apierror)
        except Exception as exception: # pylint: disable=broad-exception-caught
            log.log_exception(logger, exception, "sensor data error",
                              msg_before="Exception raised while ingesting sensor data: ")
