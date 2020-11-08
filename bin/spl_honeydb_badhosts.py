'''
Send HoneyDB Bad Hosts to Splunk
'''
import os
import sys
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
        logger.error("Bad Hosts Error: HoneyDB args file missing : ./%s ", jsonfile)
        exit()

    # parse file
    try:
        args = json.loads(data)
    except ValueError as jsonerror:
        logger = setup_logger(logging.ERROR)
        logger.error("Bad Hosts Error: File %s data read error %s ", jsonfile, jsonerror)
        exit()

    if ("X-HoneyDb-ApiId" in args) and ("X-HoneyDb-ApiKey" in args):
        apiId = str(args['X-HoneyDb-ApiId'])
        apiKey = str(args['X-HoneyDb-ApiKey'])
    else:
        logger = setup_logger(logging.ERROR)
        logger.error("Bad Hosts Error: HoneyDB args X-HoneyDb-ApiId OR/AND X-HoneyDb-ApiKey missing in file : ./%s ", jsonfile)
        exit()

    if (apiId and apiKey):
        headers = {
            'X-HoneyDb-ApiId': apiId,
            'X-HoneyDb-ApiKey': apiKey,
        }

        url = 'https://honeydb.io/api/bad-hosts'
        logger = setup_logger(logging.INFO)
        logger.info("Bad Hosts: Calling API with : %s ", url)
        response = requests.get(url, headers=headers)

        if response.status_code != 200:
                logger = setup_logger(logging.ERROR)
                logger.error("Bad Hosts Error: API error with status code: %s ", response.status_code)

        try:
            badhostsjson = response.json()
            if badhostsjson:
                for i in badhostsjson:
                    ### Send Data to Splunk ###
                    data_j = json.dumps(i)
                    print data_j

        except ValueError:
            logger = setup_logger(logging.ERROR)
            logger.error("Bad Hosts API call failed . Please check your authentication key or check with HoneyDB Support team. API response code: %s", response.status_code)
            exit()
    else:
        logger = setup_logger(logging.ERROR)
        logger.error("HoneyDB API key ID and Secret Key can not be blank. Please Enter the right keys")
        exit()
