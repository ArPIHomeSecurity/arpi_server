from monitor.service import start_background_service, stop_background_service
from monitor.logging import initialize_logging

initialize_logging()


def post_worker_init(worker):
    start_background_service()


def worker_exit(server, worker):
    stop_background_service()


bind = "localhost:8081"
workers = 1
graceful_timeout = 3
threads = 100
