'''
Send HoneyDB Sensor Data to Splunk
'''
import os
import sys
from datetime import datetime, timezone
import json
import logging
import logging.handlers

# use the requests library vendored under the app's lib/ directory
sys.path.insert(0, os.path.join(sys.path[0], "..", "lib"))
import requests # pylint: disable=wrong-import-position
from splunk.clilib import cli_common as cli # pylint: disable=import-error,wrong-import-position


def setup_logger(level):
    '''
    WRITE THE INTERNAL LOGS TO LOGFILE FOR HONEYDB
    '''
    logger = logging.getLogger('')
    logger.propagate = False # Prevent the log messages from being duplicated in the python.log file
    logger.setLevel(level)
    log_file = os.path.join(sys.path[0], "..", "..", "..", "..", 'var', 'log', 'splunk', 'honeydb.log')
    file_handler = logging.handlers.RotatingFileHandler(log_file, maxBytes=25000000, backupCount=5)
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
    file_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    return logger

### MAIN FUNCTION ###

if __name__ == "__main__":

    logger = setup_logger(logging.INFO)

    ## get splunk app version
    version = cli.getConfKeyValue("app", "launcher", "version")

    ## Check if honeydb.json file exists ##
    jsonfile = os.path.join(sys.path[0], "honeydb.json")

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

        # init from_id
        from_id = "0"
        # set path to from_id file
        from_id_file = os.path.join(sys.path[0], "from_id")

        try:
            # check if from_id file exists, if not create it
            if not os.path.exists(from_id_file):
                with open(from_id_file, 'w', encoding='utf-8') as file_from_id:
                    file_from_id.write(from_id)

            with open(from_id_file, 'r', encoding='utf-8') as file_from_id:
                from_id = file_from_id.read()
                # in case there was an issue initializing file with a value
                if from_id.strip() == "":
                    from_id = "0"

        except OSError:
            logger.error("Sensor Data Error: problem initializing from_id file : ./%s", from_id_file)

        # determine if data will be filtered based on subscription
        mydata = "/mydata"
        if subscription.lower() == "gold":
            mydata = ""

        # init sensor_data_date with today's date (UTC, to match the feed)
        sensor_data_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

        # call api
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

        # events are printed first and the checkpoint updated last: a failed
        # checkpoint write re-emits events next run (at-least-once, no data loss)
        try:
            if eventjson:
                for i in eventjson[0]['data']:
                    ### Send Data to Splunk ###
                    data_j = json.dumps(i)
                    print(data_j)

                try:
                    with open(from_id_file, 'w', encoding='utf-8') as file_from_id:
                        file_from_id.write(str(eventjson[1]['from_id']))

                except OSError:
                    logger.error("Sensor Data Error: problem writing from_id file : .%s", from_id_file)

        except (IndexError, KeyError, TypeError) as shapeerror:
            logger.error("Sensor Data Error: unexpected API response structure : %s", shapeerror)
            sys.exit()
    else:
        logger.error("HoneyDB API ID and API Key can not be blank. Please add your API ID and Key to the honeydb.json file.")
        sys.exit()
