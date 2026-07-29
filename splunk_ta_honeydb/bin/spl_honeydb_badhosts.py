'''
Send HoneyDB Bad Hosts to Splunk
'''
import os
import sys
import json
import logging
import logging.handlers

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

# use the requests library vendored under the app's lib/ directory
sys.path.insert(0, os.path.join(SCRIPT_DIR, "..", "lib"))
import requests # pylint: disable=wrong-import-position
import honeydb_common # pylint: disable=wrong-import-position
from splunk.clilib import cli_common as cli # pylint: disable=import-error,wrong-import-position


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

### MAIN FUNCTION ###

if __name__ == "__main__":

    logger = setup_logger(logging.INFO)

    ## get splunk app version
    version = cli.getConfKeyValue("app", "launcher", "version")

    ## load credentials: Splunk credential store first, honeydb.json fallback ##
    apiId, apiKey, subscription, cred_source = honeydb_common.load_credentials(SCRIPT_DIR, cli, logger, "Bad Hosts")

    if (apiId and apiKey):
        logger.info("Bad Hosts: using credentials from %s", cred_source)
        headers = {
            'X-HoneyDb-ApiId': apiId,
            'X-HoneyDb-ApiKey': apiKey,
            'User-Agent': f'HoneyDB Splunk App/{version}'
        }

        url = 'https://honeydb.io/api/bad-hosts'
        logger.info("Bad Hosts: Calling API with : %s ", url)

        try:
            response = requests.get(url, headers=headers, timeout=30)
        except requests.exceptions.RequestException as requesterror:
            logger.error("Bad Hosts Error: problem calling API : %s : %s ", url, requesterror)
            sys.exit()

        if response.status_code != 200:
            logger.error("Bad Hosts Error: API error with status code: %s ", response.status_code)
            sys.exit()

        try:
            badhostsjson = response.json()
            if badhostsjson:
                for i in badhostsjson:
                    ### Send Data to Splunk ###
                    data_j = json.dumps(i)
                    print(data_j)

        except ValueError:
            logger.error("Bad Hosts API call failed . Please check your authentication key or check with HoneyDB Support team. API response code: %s", response.status_code)
            sys.exit()
    else:
        logger.error("HoneyDB API key ID and Secret Key can not be blank. Please Enter the right keys")
        sys.exit()
