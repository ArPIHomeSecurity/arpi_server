"""
The credentials of the internal MQTT broker accounts exposed over the REST API.

Both accounts are system managed and an administrator has to be able to read their
password to configure an external client, so they are exempt from the password masking
of the other options.
"""

import logging

import pytest
from data import create_test_no_delay_v2
from dotenv import load_dotenv
from helpers import call_api, check_api_response

load_dotenv(".env.pytest")

logger = logging.getLogger(__name__)

MASKED = "******"

# the passwords of the test environment, see .env.pytest
ACCOUNTS = [
    ("internal_read", "argus_reader", "argus_reader_password"),
    ("internal_control", "argus_control", "argus_control_password"),
]


@pytest.mark.parametrize("database_data", [create_test_no_delay_v2], indirect=True)
@pytest.mark.parametrize("section, username, password", ACCOUNTS)
def test_01_internal_account_credentials(user_token, section, username, password):
    response = call_api("GET", f"/api/config/mqtt/{section}", {}, user_token)
    check_api_response(response)

    value = response.json()["value"]
    assert value["username"] == username
    # the password must not be masked, the administrator hands it to the external client
    assert value["password"] == password
    assert value["tls_enabled"] is True
