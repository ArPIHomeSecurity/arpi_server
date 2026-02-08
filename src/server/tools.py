import logging

from flask.helpers import make_response
from flask.json import jsonify

from utils.constants import LOG_IPC

logger = logging.getLogger(LOG_IPC)

def get_ipc_response(ipc_response):
    """
    result => return code 200 or 500 
    message => copied as is if exists
    value, other => dictionary merged into the response

    """
    if not ipc_response:
        return {"message": "No response from monitoring service"}, 503

    return_code = 200 if ipc_response["result"] else 500

    response = {}
    if "message" in ipc_response:
        response["message"] = ipc_response["message"]

    try:
        response |= ipc_response.get("value", {})
        response |= ipc_response.get("other", {})
    except TypeError as error:
        logging.error("Failed to merge response values: %s! %s - %s", error, response, ipc_response)

    logger.info("Code: %s", return_code)
    logger.info("Response: %s", response)

    return response, return_code


def process_ipc_response(ipc_response):
    """
    Process IPC response and return Flask response.

    :param ipc_response: The IPC response to process.
    """
    response, return_code = get_ipc_response(ipc_response)
    return make_response(jsonify(response), return_code)
