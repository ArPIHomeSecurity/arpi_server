"""Service for registered Zigbee device management."""

from server.ipc import IPCClient
from server.services.base import (
    BaseService,
    ConfigChangesNotAllowed,
    ObjectNotChanged,
    ObjectNotFound,
)
from utils.models import ZigbeeDevice


class ZigbeeService(BaseService):
    """Service for registered Zigbee device CRUD operations."""

    def get_devices(self) -> list[ZigbeeDevice]:
        return (
            self._db_session.query(ZigbeeDevice)
            .filter_by(deleted=False)
            .order_by(ZigbeeDevice.name.asc())
            .all()
        )

    def get_device(self, device_id: int) -> ZigbeeDevice:
        device = self._db_session.get(ZigbeeDevice, device_id)
        if not device:
            raise ObjectNotFound("Zigbee device not found")
        return device

    def update_device(self, device_id: int, **data) -> ZigbeeDevice:
        if not self.are_changes_allowed:
            raise ConfigChangesNotAllowed()

        device = self.get_device(device_id)
        if "ieee_address" in data:
            duplicate = (
                self._db_session.query(ZigbeeDevice)
                .filter(
                    ZigbeeDevice.ieee_address == data["ieee_address"],
                    ZigbeeDevice.id != device_id,
                    ZigbeeDevice.deleted.is_(False),
                )
                .first()
            )
            if duplicate:
                raise ObjectNotChanged("A Zigbee device with this IEEE address already exists")

        if not device.update(data):
            raise ObjectNotChanged("Zigbee device not changed")

        self._db_session.commit()
        self._db_session.refresh(device)
        IPCClient().update_configuration()
        return device

    def delete_device(self, device_id: int) -> None:
        if not self.are_changes_allowed:
            raise ConfigChangesNotAllowed()

        device = self.get_device(device_id)
        sensors = [s for s in device.sensors if not s.deleted]
        if sensors and len(sensors) > 0:
            raise ObjectNotChanged("Zigbee device is connected to one or more sensors")

        device.deleted = True
        self._db_session.commit()
        IPCClient().zigbee_unpair_device(ieee_address=device.ieee_address)
