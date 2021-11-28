from abc import ABC, abstractmethod
from enum import Enum
import os
from sqlalchemy.engine import create_engine

from sqlalchemy.engine.url import URL
from sqlalchemy.orm.session import sessionmaker

from monitoring.adapters.keypads.delay import DelayPhase, Handler


class Action(Enum):
    """Actions of the keypad"""
    KEY = 0
    FUNCTION = 1
    CARD = 2


class Function(Enum):
    """Functions keys"""
    AWAY = 1
    STAY = 2


class KeypadBase(ABC):
    """Base class for the keypads"""

    def __init__(self):
        self._id = None
        self._armed = False
        self._keys = []
        self._card = None
        self._function: Action = None
        self._delay: Handler = None
        self._db_session = None

    def get_last_key(self):
        if self._keys:
            return self._keys.pop(0)
        else:
            return None

    def get_card(self):
        card = self._card
        self._card = None
        return card

    def get_function(self):
        function = self._function
        self._function = None
        return function

    def last_action(self) -> Action:
        """Last identified action on the keypad"""
        if self._card is not None:
            return Action.CARD
        elif self._keys:
            return Action.KEY
        elif self._function:
            return Action.FUNCTION

    def initialise(self):
        pass

    @abstractmethod
    def set_error(self, state: bool):
        pass

    @abstractmethod
    def set_ready(self, state: bool):
        pass

    def set_armed(self, state: bool):
        self._armed = state

    def get_armed(self):
        return self._armed

    def start_delay(self, start, delay):
        self._delay = Handler(start, delay)

    def stop_delay(self):
        self._delay = None

    @abstractmethod
    def communicate(self):
        pass

    def get_database_session(self):
        if self._db_session:
            return self._db_session

        uri = None
        try:
            uri = URL(
                drivername="postgresql+psycopg2",
                username=os.environ.get("DB_USER", None),
                password=os.environ.get("DB_PASSWORD", None),
                host=os.environ.get("DB_HOST", None),
                port=os.environ.get("DB_PORT", None),
                database=os.environ.get("DB_SCHEMA", None),
            )
        except KeyError:
            self._logger.error("Database connnection not configured")
            return

        engine = create_engine(uri)
        self._db_session = sessionmaker(bind=engine)()
        return self._db_session

    def manage_delay(self):
        if self._delay:
            beep = self._delay.do()
            self._logger.debug("Beep type: %s", beep)
            if beep == DelayPhase.NORMAL:
                self.beeps(1, 0.1, 0.1)
            elif beep == DelayPhase.LAST_5_SECS:
                self.beeps(2, 0.1, 0.1)
            elif beep == DelayPhase.NO_BEEP:
                pass
            elif beep == DelayPhase.NO_DELAY:
                self._delay = None
                self.beeps(3, 0.1, 0.1)
            else:
                self._logger.error("Unknown beep type!")
