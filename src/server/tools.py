import logging

from flask.helpers import make_response
from flask.json import jsonify


def process_ipc_response(ipc_response):
    """
    result => return code 200 or 500
    message => copied as is if exists
    value, other => dictionary merged into the response

    """
    if not ipc_response:
        return make_response(jsonify({"message": "No response from monitoring service"}), 503)

    return_code = 200 if ipc_response["result"] else 500

    # copy values to response
    response = {}
    if "message" in ipc_response:
        response["message"] = ipc_response["message"]

    response |= ipc_response.get("value", {})
    response |= ipc_response.get("other", {})

    logging.info("Code: %s", return_code)
    logging.info("Response: %s", response)

    return make_response(jsonify(response), return_code)
