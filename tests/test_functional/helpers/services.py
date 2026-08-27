import logging
from contextlib import contextmanager
from threading import Thread
from time import sleep

import requests
from werkzeug.serving import make_server

from monitor.service import create_app, stop_background_service
from server import app as server_app

logger = logging.getLogger(__name__)


@contextmanager
def server_service(host: str, port: str):
    server = make_server(host, int(port), server_app, threaded=True)
    server_thread = Thread(target=server.serve_forever, name="server-test-server", daemon=True)
    server_thread.start()

    logger.debug("Server test service started on %s:%s", host, port)

    try:
        for _ in range(30):
            try:
                response = requests.get(f"http://{host}:{port}/api/version", timeout=1)
                if response.status_code == 200:
                    logger.debug("Server is ready")
                    break
            except requests.ConnectionError:
                logger.debug("Waiting for server to be ready...")
                sleep(0.5)
        else:
            raise RuntimeError("Server did not become ready in time")

        yield server_thread
    finally:
        logger.debug("Shutting down server test service...")
        server.shutdown()
        server_thread.join(timeout=5)
        logger.debug("Server test service stopped")


@contextmanager
def monitor_service(host: str, port: str):
    app = create_app()
    server = make_server(host, int(port), app, threaded=True)
    server_thread = Thread(target=server.serve_forever, name="monitor-test-server", daemon=True)
    server_thread.start()

    logger.debug("Monitor test server started on %s:%s", host, port)

    try:
        for _ in range(30):
            try:
                requests.get(f"http://{host}:{port}/", timeout=1)
                logger.debug("Monitor is ready")
                break
            except requests.ConnectionError:
                logger.debug("Waiting for monitor to be ready...")
                sleep(0.5)
        else:
            raise RuntimeError("Monitor did not become ready in time")

        yield server_thread
    finally:
        logger.debug("Shutting down monitor test server...")
        stop_background_service()
        server.shutdown()
        server_thread.join(timeout=5)
        logger.debug("Monitor test server stopped")
