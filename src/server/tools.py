import logging

from flask.helpers import make_response
from flask.json import jsonify

from utils.constants import LOG_IPC

logger = logging.getLogger(LOG_IPC)

def evaluate_ipc_response(ipc_response) -> tuple[dict, bool]:
    """
    Process IPC response and return a tuple of response dict and success boolean.

    :param ipc_response: The IPC response to process.
    :return: A tuple of response dict and success boolean.
    """
    if not ipc_response:
        logger.info("No response from monitoring service")
        return {"message": "No response from monitoring service"}, False

    success = bool(ipc_response.get("result"))

    response = {}
    if "message" in ipc_response:
        response["message"] = ipc_response["message"]

    try:
        response |= ipc_response.get("value", {})
        response |= ipc_response.get("other", {})
    except TypeError as error:
        logging.error("Failed to merge response values: %s! %s - %s", error, response, ipc_response)

    logger.info("Success: %s", success)
    logger.info("Response: %s", response)

    return response, success


def process_ipc_response(ipc_response):
    """
    Process IPC response and return Flask response.

    :param ipc_response: The IPC response to process.
    """
    response, success = evaluate_ipc_response(ipc_response)
    if not ipc_response:
        http_code = 503
    else:
        http_code = 200 if success else 500

    return make_response(jsonify(response), http_code)
