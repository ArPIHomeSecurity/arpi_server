from flask.helpers import make_response
from flask.json import jsonify


def process_ipc_response(response):
    if not response:
        return make_response(jsonify({"message": "No response from monitoring service"}), 503)
    if response["result"]:
        return jsonify(response.get("value"))
    else:
        return make_response(jsonify({"message": response["message"]}), 500)
