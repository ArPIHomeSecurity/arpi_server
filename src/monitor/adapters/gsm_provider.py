"""
Process wide owner of the GSM modem.

The modem is a single physical device behind one serial port: opening it from multiple
GsmModem instances makes the read loops race for the same bytes. All users (notifications,
IPC helpers, SMS receiving) share one instance here, serialized by a reentrant lock.
"""

import logging
import os
from contextlib import contextmanager
from threading import RLock

from monitor.config.models import GSMConfig
from utils.constants import LOG_ADGSM

logger = logging.getLogger(LOG_ADGSM)

# check if running with simulator
if os.environ.get("USE_SIMULATOR", "false").lower() == "false":
    from monitor.adapters.gsm import GSM
else:
    from monitor.adapters.mock.gsm import GSM


class GSMProvider:
    _lock = RLock()
    _instance: GSM = None
    _config: GSMConfig = None
    _connection_settings = None
    _sms_received_callback = None

    @classmethod
    def load_config(cls):
        """
        Reload the GSM configuration and apply it on the modem, which is
        dropped only when the connection settings changed.
        """
        with cls._lock:
            cls._config = GSMConfig.load_config()
            if not cls._instance:
                return

            if cls._connection_settings != cls._get_connection_settings():
                cls.destroy()
            else:
                cls._instance.set_enabled(cls._config.enabled)

    @classmethod
    def get_config(cls) -> GSMConfig:
        with cls._lock:
            if cls._config is None:
                cls.load_config()

            return cls._config

    @classmethod
    def is_enabled(cls) -> bool:
        return cls.get_config().enabled

    @classmethod
    def set_sms_received_callback(cls, callback):
        with cls._lock:
            cls._sms_received_callback = callback
            if cls._instance:
                cls._instance.set_sms_received_callback(callback)

    @classmethod
    @contextmanager
    def session(cls):
        """
        Exclusive access to the modem, connecting it on demand. A disabled or
        unreachable modem is not connected but still accepts the calls.
        """
        with cls._lock:
            gsm = cls._get_instance()
            if not gsm.connected:
                gsm.setup()

            yield gsm

            gsm.destroy()

    @classmethod
    def destroy(cls):
        with cls._lock:
            if cls._instance:
                cls._instance.destroy()
                cls._instance = None
                cls._connection_settings = None

    @classmethod
    def _get_instance(cls) -> GSM:
        with cls._lock:
            if cls._instance is None:
                settings = cls._get_connection_settings()
                logger.debug("Creating GSM modem on %s", settings[1])
                cls._instance = GSM(
                    pin_code=settings[0],
                    port=settings[1],
                    baud=settings[2],
                    sms_received_callback=cls._sms_received_callback,
                    enabled=cls.get_config().enabled,
                )
                cls._connection_settings = settings

            return cls._instance

    @classmethod
    def _get_connection_settings(cls):
        return (
            cls.get_config().pin_code,
            os.environ["GSM_PORT"],
            os.environ["GSM_PORT_BAUD"],
        )
