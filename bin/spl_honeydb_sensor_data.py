'''
Send HoneyDB Sensor Data to Splunk
'''
import os
import sys
from datetime import date
import json
import logging
import logging.handlers
import requests


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

    ## Check if honeydb.json file exists ##
    jsonfile = os.path.join(sys.path[0], "honeydb.json")

    try:
        with open(jsonfile, 'r') as argfile:
            data = argfile.read()
    except:
        logger = setup_logger(logging.ERROR)
        logger.error("Sensor Data Error: HoneyDB args file missing : ./%s ", jsonfile)
        exit()

    # parse file
    try:
        args = json.loads(data)
    except ValueError as jsonerror:
        logger = setup_logger(logging.ERROR)
        logger.error("Sensor Data Error: File %s data read error %s ", jsonfile, jsonerror)
        exit()

    if ("X-HoneyDb-ApiId" in args) and ("X-HoneyDb-ApiKey" in args):
        apiId = str(args['X-HoneyDb-ApiId'])
        apiKey = str(args['X-HoneyDb-ApiKey'])
    else:
        logger = setup_logger(logging.ERROR)
        logger.error("Sensor Data Error: HoneyDB args X-HoneyDb-ApiId OR/AND X-HoneyDb-ApiKey missing in file : ./%s ", jsonfile)
        exit()

    if (apiId and apiKey):
        headers = {
            'X-HoneyDb-ApiId': apiId,
            'X-HoneyDb-ApiKey': apiKey,
        }

        # init from_id
        from_id = 0
        # set path to from_id file
        from_id_file = os.path.join(sys.path[0], "from_id")

        try:
            # check if from_id file exists, if not create it
            if not os.path.exists(from_id_file):
                with open(from_id_file, 'w') as file_from_id:
                    file_from_id.write(from_id)

            with open(from_id_file, 'r') as file_from_id:
                from_id = file_from_id.read()
                # in case there was an issue initializing file with a value
                if from_id.strip() == "":
                    from_id = 0

        except Exception as err:
            logger = setup_logger(logging.ERROR)
            logger.error("Sensor Data Error: problem initializing from_id file : ./%s %s", from_id_file, type(err))

        # init sensor_data_date with today's date
        today = date.today()
        sensor_data_date = today.strftime("%Y-%m-%d")

        # call api
        try:
            url = 'https://honeydb.io/api/sensor-data?sensor-data-date={}&from-id={}'.format(sensor_data_date, from_id)
            logger = setup_logger(logging.INFO)
            logger.info("Sensor Data: Calling API with : %s ", url)
            response = requests.get(url, headers=headers)

            if response.status_code != 200:
                logger = setup_logger(logging.ERROR)
                logger.error("Sensor Data Error: API error with status code: %s ", response.status_code)

        except:
            logger = setup_logger(logging.ERROR)
            logger.error("Sensor Data Error: problem calling API : %s ", url)

        try:
            eventjson = response.json()
            if eventjson:
                for i in eventjson[0]['data']:
                    ### Send Data to Splunk ###
                    data_j = json.dumps(i)
                    print data_j

                try:
                    with open(from_id_file, 'w') as file_from_id:
                        file_from_id.write(eventjson[1]['from_id'])

                except Exception as err:
                    logger = setup_logger(logging.ERROR)
                    logger.error("Sensor Data Error: problem writing from_id file : .%s %s", from_id_file, type(err))

        except ValueError:
            logger = setup_logger(logging.ERROR)
            logger.error("Events API call failed . Please check your authentication key or check with HoneyDB support team. API response code : %s", response.status_code)
            exit()
    else:
        logger = setup_logger(logging.ERROR)
        logger.error("HoneyDB API ID and API Key can not be blank. Please add your API ID and Key to the honeydb.json file.")
        exit()
