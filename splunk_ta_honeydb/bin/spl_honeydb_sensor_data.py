'''
Send HoneyDB Sensor Data to Splunk
'''
import os
import sys
from datetime import datetime, timedelta, timezone
import json
import logging
import logging.handlers

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# use the requests library vendored under the app's lib/ directory
sys.path.insert(0, os.path.join(SCRIPT_DIR, "..", "lib"))
import requests # pylint: disable=wrong-import-position
from splunk.clilib import cli_common as cli # pylint: disable=import-error,wrong-import-position

# safety bound on API pages fetched in a single run; an unfinished drain
# resumes from the checkpoint on the next scheduled run
MAX_PAGES_PER_RUN = 30


def setup_logger(level):
    '''
    WRITE THE INTERNAL LOGS TO LOGFILE FOR HONEYDB
    '''
    logger = logging.getLogger('')
    logger.propagate = False # Prevent the log messages from being duplicated in the python.log file
    logger.setLevel(level)
    log_file = os.path.join(SCRIPT_DIR, "..", "..", "..", "..", 'var', 'log', 'splunk', 'honeydb.log')
    file_handler = logging.handlers.RotatingFileHandler(log_file, maxBytes=25000000, backupCount=5)
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
    file_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    return logger


def parse_checkpoint(text, today):
    '''
    Parse the from_id checkpoint file content. Supports the current JSON
    format {"date": "YYYY-MM-DD", "from_id": N} and the legacy bare-integer
    format (treated as progress within the current UTC date, matching the
    old single-date behavior). Returns (date_str, from_id_int).
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
    '''
    Serialize checkpoint state to the JSON file format.
    '''
    return json.dumps({"date": date_str, "from_id": from_id})


def next_date(date_str):
    '''
    Return the day after date_str in YYYY-MM-DD form.
    '''
    day = datetime.strptime(date_str, "%Y-%m-%d")
    return (day + timedelta(days=1)).strftime("%Y-%m-%d")

### MAIN FUNCTION ###

if __name__ == "__main__":

    logger = setup_logger(logging.INFO)

    ## get splunk app version
    version = cli.getConfKeyValue("app", "launcher", "version")

    ## Check if honeydb.json file exists ##
    jsonfile = os.path.join(SCRIPT_DIR, "honeydb.json")

    try:
        with open(jsonfile, 'r', encoding='utf-8') as argfile:
            data = argfile.read()
    except OSError:
        logger.error("Sensor Data Error: HoneyDB args file missing : ./%s ", jsonfile)
        sys.exit()

    # parse file
    try:
        args = json.loads(data)
    except ValueError as jsonerror:
        logger.error("Sensor Data Error: File %s data read error %s ", jsonfile, jsonerror)
        sys.exit()

    if ("X-HoneyDb-ApiId" in args) and ("X-HoneyDb-ApiKey" in args):
        apiId = str(args['X-HoneyDb-ApiId'])
        apiKey = str(args['X-HoneyDb-ApiKey'])

        subscription = "community"
        if "subscription" in args:
            subscription = args['subscription']


    else:
        logger.error("Sensor Data Error: HoneyDB args X-HoneyDb-ApiId OR/AND X-HoneyDb-ApiKey missing in file : ./%s ", jsonfile)
        sys.exit()

    if (apiId and apiKey):
        headers = {
            'X-HoneyDb-ApiId': apiId,
            'X-HoneyDb-ApiKey': apiKey,
            'User-Agent': f'HoneyDB Splunk App/{version}'
        }

        # set path to from_id file
        from_id_file = os.path.join(SCRIPT_DIR, "from_id")

        # today's date (UTC, to match the feed)
        today_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        checkpoint_text = ""
        try:
            if os.path.exists(from_id_file):
                with open(from_id_file, 'r', encoding='utf-8') as file_from_id:
                    checkpoint_text = file_from_id.read()
        except OSError:
            logger.error("Sensor Data Error: problem reading from_id file : ./%s", from_id_file)

        sensor_data_date, from_id = parse_checkpoint(checkpoint_text, today_utc)
        # clamp a future checkpoint date (clock skew) back to today
        sensor_data_date = min(sensor_data_date, today_utc)

        # determine if data will be filtered based on subscription
        mydata = "/mydata"
        if subscription.lower() == "gold":
            mydata = ""

        # drain pages from the checkpoint date through today; events are
        # printed first and the checkpoint updated last per page, so a failed
        # checkpoint write re-emits events next run (at-least-once, no loss)
        pages = 0
        while pages < MAX_PAGES_PER_RUN:
            pages += 1

            url = f'https://honeydb.io/api/sensor-data{mydata}?sensor-data-date={sensor_data_date}&from-id={from_id}'
            logger.info("Sensor Data: Calling API with : %s ", url)

            try:
                response = requests.get(url, headers=headers, timeout=30)
            except requests.exceptions.RequestException as requesterror:
                logger.error("Sensor Data Error: problem calling API : %s : %s ", url, requesterror)
                sys.exit()

            if response.status_code != 200:
                logger.error("Sensor Data Error: API error with status code: %s ", response.status_code)
                sys.exit()

            try:
                eventjson = response.json()
            except ValueError:
                logger.error("Events API call failed . Please check your authentication key or check with HoneyDB support team. API response code : %s", response.status_code)
                sys.exit()

            try:
                rows = eventjson[0]['data'] if eventjson else []
                new_from_id = eventjson[1]['from_id'] if eventjson else 0
            except (IndexError, KeyError, TypeError) as shapeerror:
                logger.error("Sensor Data Error: unexpected API response structure : %s", shapeerror)
                sys.exit()

            if rows:
                for i in rows:
                    ### Send Data to Splunk ###
                    data_j = json.dumps(i)
                    print(data_j)

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
                if sensor_data_date < today_utc:
                    # this past date is drained; advance to the next date
                    sensor_data_date = next_date(sensor_data_date)
                    from_id = 0
                else:
                    # today is drained; done until the next scheduled run
                    break

            try:
                with open(from_id_file, 'w', encoding='utf-8') as file_from_id:
                    file_from_id.write(serialize_checkpoint(sensor_data_date, from_id))
            except OSError:
                logger.error("Sensor Data Error: problem writing from_id file : .%s", from_id_file)
    else:
        logger.error("HoneyDB API ID and API Key can not be blank. Please add your API ID and Key to the honeydb.json file.")
        sys.exit()
