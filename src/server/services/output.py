"""
Output service module to handle output-related operations.
"""

from server.ipc import IPCClient
from server.services.base import (
    BaseService,
    ChannelConflictError,
    ConfigChangesNotAllowed,
    InvalidConfiguration,
    ObjectNotChanged,
    ObjectNotFound,
)
from utils.models import Output, OutputTriggerType


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
        trigger_type: OutputTriggerType = OutputTriggerType.BUTTON,
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

        if (
            trigger_type in [OutputTriggerType.BUTTON, OutputTriggerType.SYSTEM]
            and area_id is not None
        ):
            raise ValueError("Area ID must be None for BUTTON and SYSTEM trigger types")

        if trigger_type == OutputTriggerType.AREA and area_id is None:
            raise ValueError("Area ID must be provided for AREA trigger type")

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

        try:
            self.validate_configuration(new_output)
        except ValueError as e:
            raise InvalidConfiguration(str(e))

        if not self.validate_channel(new_output):
            raise ChannelConflictError("Channel conflict with existing outputs.")

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
        
        try:
            self.validate_configuration(output)
        except ValueError as e:
            raise InvalidConfiguration(str(e))
        
        if not self.validate_channel(output):
            raise ChannelConflictError("Channel conflict with existing outputs.")

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

    def activate_output(self, output_id: int) -> dict:
        """
        Activate an output by its ID.

        Args:
            output_id: ID of the output to activate

        Returns:
            IPC response dict
        """
        output = self._db_session.query(Output).get(output_id)
        if not output:
            raise ObjectNotFound("Output not found")
        
        if output.trigger_type != OutputTriggerType.BUTTON:
            raise ObjectNotChanged("Only buttons can be activated manually")

        return IPCClient().activate_output(output_id)

    def deactivate_output(self, output_id: int) -> dict:
        """
        Deactivate an output by its ID.

        Args:
            output_id: ID of the output to deactivate

        Returns:
            IPC response dict
        """
        output = self._db_session.query(Output).get(output_id)
        if not output:
            raise ObjectNotFound("Output not found")
        
        if output.trigger_type != OutputTriggerType.BUTTON:
            raise ObjectNotChanged("Only buttons can be deactivated manually")

        return IPCClient().deactivate_output(output_id)

    def validate_configuration(self, output: Output) -> None:
        """
        Validate the output configuration to ensure it meets the required constraints.

        Args:
            output: The Output object to validate

        Raises:
            ValueError: If the configuration is invalid
        """
        if (
            output.trigger_type in [OutputTriggerType.BUTTON, OutputTriggerType.SYSTEM]
            and output.area_id is not None
        ):
            raise ValueError("Area ID must be None for BUTTON and SYSTEM trigger types")

        if output.trigger_type == OutputTriggerType.AREA and output.area_id is None:
            raise ValueError("Area ID must be provided for AREA trigger type")

    def validate_channel(self, output: Output) -> bool:
        """
        Validate that the output's channel does not conflict with existing outputs.

        Args:
            output: The Output object to validate

        Returns:
            True if the channel is valid, False otherwise
        """
        query = self._db_session.query(Output).filter(
            Output.channel == output.channel, Output.id != output.id
        )

        return not self._db_session.query(query.exists()).scalar()
