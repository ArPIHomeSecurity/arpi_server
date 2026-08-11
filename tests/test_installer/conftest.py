"""
The installer tests only read the static configuration files shipped with the installer.

They do not need the database and the server that the autouse fixtures of the parent
conftest start, so those fixtures are overridden with empty ones.
"""

import pytest


@pytest.fixture(scope="module", autouse=True)
def server():
    yield


@pytest.fixture(scope="function", autouse=True)
def cleanup_database_fixture():
    yield
