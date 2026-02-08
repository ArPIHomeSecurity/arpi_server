"""
Output service module to handle output-related operations.
"""

from server.ipc import IPCClient
from server.services.base import BaseService, ConfigChangesNotAllowed, ObjectNotChanged, ObjectNotFound
from utils.models import Output


class OutputService(BaseService):
    """
    Service for Output management operations.
    """

    def get_outputs(self) -> list[Output]:
        """
        Get all outputs.

        Returns:
            List of Output objects
        """
        query = self._db_session.query(Output)

        return query.order_by(Output.name.asc()).all()

    def get_output_by_id(self, output_id: int) -> Output:
        """
        Get an output by its ID.

        Args:
            output_id: ID of the output to retrieve

        Returns:
            Output object or None if not found
        """
        output = self._db_session.query(Output).get(output_id)
        if not output:
            raise ObjectNotFound("Output not found")
        
        return output

    def create_output(
        self,
        name: str,
        description: str = "",
        channel: int = 0,
        trigger_type: str = "manual",
        area_id: int = None,
        delay: int = 0,
        duration: int = 0,
        default_state: bool = False,
        enabled: bool = True,
    ) -> Output:
        """
        Create a new output in the database.

        Args:
            name: The name of the new output
            description: Optional description of the output
        Returns:
            The newly created Output object
        """
        if not self.are_changes_allowed:
            raise ConfigChangesNotAllowed()

        new_output = Output(
            name=name,
            description=description,
            channel=channel,
            trigger_type=trigger_type,
            area_id=area_id,
            delay=delay,
            duration=duration,
            default_state=default_state,
            enabled=enabled,
        )
        self._db_session.add(new_output)
        self._db_session.commit()
        IPCClient().update_configuration()
        return new_output

    def update_output(self, output_id, **kwargs) -> Output:
        """
        Update an existing output in the database.
        """
        if not self.are_changes_allowed:
            raise ConfigChangesNotAllowed()

        output = self._db_session.query(Output).filter(Output.id == output_id).first()
        if not output:
            raise ObjectNotFound("Output not found")

        output_changed = output.update(kwargs)
        if not output_changed:
            raise ObjectNotChanged("Output not changed")

        self._db_session.commit()
        self._db_session.refresh(output)
        IPCClient().update_configuration()
        return output

    def delete_output(self, output_id: int) -> None:
        """
        Delete an output by its ID if it has no associated sensors.

        Args:
            output_id: ID of the output to delete
        Returns:
            True if deletion was successful, False otherwise
        """
        if not self.are_changes_allowed:
            raise ConfigChangesNotAllowed()

        output = self._db_session.query(Output).get(output_id)
        if not output:
            raise ObjectNotFound("Output not found")

        self._db_session.delete(output)
        self._db_session.commit()
        IPCClient().update_configuration()
