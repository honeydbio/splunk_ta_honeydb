'''
Pure logic for the HoneyDB inputs: checkpoint handling, date math,
retry policy, and the sensor-data drain loop. No Splunk imports — this
module is unit-tested outside Splunk.
'''
import json
import os
import time
from datetime import datetime, timedelta

import requests

APP = "splunk_ta_honeydb"
ADDON_VERSION = "3.0.0"
API_BASE = "https://honeydb.io/api"

# retry policy for HoneyDB API calls
RETRY_STATUSES = (429, 500, 502, 503, 504)
RETRY_AFTER_CAP = 30

# safety bound on API pages fetched in a single run; an unfinished drain
# resumes from the checkpoint on the next scheduled run
MAX_PAGES_PER_RUN = 30


class ApiError(Exception):
    '''Raised when the HoneyDB API cannot be reached or rejects a call.'''


def parse_checkpoint(text, today):
    '''
    Parse checkpoint file content. Supports the JSON format
    {"date": "YYYY-MM-DD", "from_id": N} and the legacy bare-integer
    format (treated as progress within the current UTC date). Returns
    (date_str, from_id_int).
    '''
    text = text.strip() if text else ""

    if text == "":
        return today, 0

    try:
        return today, int(text)
    except ValueError:
        pass

    try:
        ckpt = json.loads(text)
        ckpt_date = str(ckpt["date"])
        datetime.strptime(ckpt_date, "%Y-%m-%d")
        return ckpt_date, int(ckpt["from_id"])
    except (ValueError, KeyError, TypeError):
        # unreadable checkpoint: restart today from 0 (at-least-once)
        return today, 0


def serialize_checkpoint(date_str, from_id):
    '''Serialize checkpoint state to the JSON file format.'''
    return json.dumps({"date": date_str, "from_id": from_id})


def next_date(date_str):
    '''Return the day after date_str in YYYY-MM-DD form.'''
    day = datetime.strptime(date_str, "%Y-%m-%d")
    return (day + timedelta(days=1)).strftime("%Y-%m-%d")


def checkpoint_file():
    '''
    Checkpoint path outside the app dir:
    $SPLUNK_HOME/var/lib/splunk/splunk_ta_honeydb/from_id — the same
    location and format used by v2.1, so upgrades resume seamlessly.
    '''
    splunk_home = os.environ.get("SPLUNK_HOME", ".")
    directory = os.path.join(splunk_home, "var", "lib", "splunk", APP)
    os.makedirs(directory, exist_ok=True)
    return os.path.join(directory, "from_id")


def read_checkpoint(path):
    '''Return checkpoint file content, or "" if unreadable/missing.'''
    try:
        with open(path, 'r', encoding='utf-8') as ckpt:
            return ckpt.read()
    except OSError:
        return ""


def write_checkpoint(path, date_str, from_id):
    '''Write checkpoint state; OSError propagates to the caller.'''
    with open(path, 'w', encoding='utf-8') as ckpt:
        ckpt.write(serialize_checkpoint(date_str, from_id))


def get_with_retry(url, headers, logger, label, retries=3):
    '''
    GET with bounded exponential backoff on transient failures
    (connection errors/timeouts, HTTP 429/5xx). Honors a numeric
    Retry-After header, capped at RETRY_AFTER_CAP seconds. Returns the
    final Response, or None when every attempt raised an exception.
    '''
    response = None
    for attempt in range(retries + 1):
        try:
            response = requests.get(url, headers=headers, timeout=30)
        except requests.exceptions.RequestException as requesterror:
            response = None
            if attempt == retries:
                logger.error("%s Error: problem calling API : %s : %s ", label, url, requesterror)
                return None
            delay = 2 ** (attempt + 1)
            logger.warning("%s: API request failed (attempt %s: %s); retrying in %ss", label, attempt + 1, requesterror, delay)
            time.sleep(delay)
            continue

        if response.status_code not in RETRY_STATUSES or attempt == retries:
            return response

        delay = 2 ** (attempt + 1)
        retry_after = response.headers.get("Retry-After", "")
        if retry_after.isdigit():
            delay = min(int(retry_after), RETRY_AFTER_CAP)
        logger.warning("%s: API returned status %s (attempt %s); retrying in %ss", label, response.status_code, attempt + 1, delay)
        time.sleep(delay)

    return response


# pylint: disable-next=too-many-arguments,too-many-positional-arguments
def drain_sensor_data(fetch_page, emit, read_ckpt, write_ckpt, today, logger,
                      max_pages=MAX_PAGES_PER_RUN):
    '''
    Drain sensor-data pages from the checkpoint date through today.

    fetch_page(date_str, from_id) -> (rows, new_from_id); may raise
    ApiError to abort the run. emit(row) writes one event. read_ckpt()
    returns checkpoint text; write_ckpt(date_str, from_id) persists it.

    Events are emitted first and the checkpoint written last per page,
    so a failed write re-emits events next run (at-least-once, no loss).
    Returns the number of pages fetched.
    '''
    date_str, from_id = parse_checkpoint(read_ckpt(), today)
    # clamp a future checkpoint date (clock skew) back to today
    date_str = min(date_str, today)

    pages = 0
    while pages < max_pages:
        pages += 1
        rows, new_from_id = fetch_page(date_str, from_id)

        if rows:
            for row in rows:
                emit(row)

            # forward-only checkpoint: never let an odd from_id rewind us
            try:
                new_from_id = int(new_from_id)
            except (ValueError, TypeError):
                new_from_id = 0

            if new_from_id <= from_id:
                logger.warning("Sensor Data: API from_id did not advance (%s -> %s); stopping this run", from_id, new_from_id)
                break

            from_id = new_from_id
        else:
            if date_str < today:
                # this past date is drained; advance to the next date
                date_str = next_date(date_str)
                from_id = 0
            else:
                # today is drained; done until the next scheduled run
                break

        write_ckpt(date_str, from_id)

    return pages
