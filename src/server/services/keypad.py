"""
Keypad service module to handle keypad-related operations.
"""

from server.ipc import IPCClient
from server.services.base import BaseService, ObjectNotChanged, ObjectNotFound
from utils.models import Keypad, KeypadType


class KeypadService(BaseService):
    """
    Service for keypad management operations.
    """

    def get_keypads(self) -> list[Keypad]:
        """
        Get all existing keypads.
        """
        return self._db_session.query(Keypad).all()

    def get_keypad(self, keypad_id: int) -> Keypad:
        """
        Get a keypad by ID.
        """
        keypad = self._db_session.query(Keypad).get(keypad_id)
        if not keypad:
            raise ObjectNotFound("Keypad not found")

        return keypad

    def create_keypad(self, type_id: int, enabled: bool = True) -> dict:
        """
        Create a new keypad and notify the monitor.
        """
        keypad_type = self._db_session.query(KeypadType).get(type_id)
        keypad = Keypad(keypad_type=keypad_type, enabled=enabled)
        self._db_session.add(keypad)
        self._db_session.commit()
        return IPCClient().update_keypad()

    def update_keypad(self, keypad_id: int, **kwargs) -> dict:
        """
        Update an existing keypad and notify the monitor.
        """
        keypad = self._db_session.query(Keypad).get(keypad_id)
        if not keypad:
            raise ObjectNotFound("Keypad not found")

        if not keypad.update(kwargs):
            raise ObjectNotChanged("Keypad not changed")

        self._db_session.commit()
        return IPCClient().update_keypad()

    def delete_keypad(self, keypad_id: int) -> dict:
        """
        Soft-delete a keypad and notify the monitor.
        """
        keypad = self._db_session.query(Keypad).get(keypad_id)
        if not keypad:
            raise ObjectNotFound("Keypad not found")

        keypad.deleted = True
        self._db_session.commit()
        return IPCClient().update_keypad()

    def get_keypad_types(self) -> list[KeypadType]:
        """
        Get all keypad types.
        """
        return self._db_session.query(KeypadType).all()
