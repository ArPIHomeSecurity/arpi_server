import logging
from dataclasses import asdict
from enum import Enum, auto
from functools import wraps
from typing import Callable

from monitor.actions import MonitorCommand


class MonitorActionResult(Enum):
    result_normal = auto()
    result_break = auto()
    result_continue = auto()


logger = logging.getLogger()


def handle_action(*actions: MonitorCommand):
    """
    Decorator to handle specific monitor actions.
    The handler function will be called when any of the specified actions are triggered.

    Handler function:
      * The handler function should accept the same arguments as the *MonitorCommand* instances it is handling.
      * The handler function should return a *MonitorActionResult* to indicate how the monitoring system should proceed

    Args:
        *actions: A variable number of *MonitorCommand* instances that this handler should respond to.
    """

    def decorator(
        func: Callable[[MonitorCommand], MonitorActionResult | None],
    ) -> Callable[[MonitorCommand], MonitorActionResult]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> MonitorActionResult:
            for action in actions:
                logger.debug("Handling action: %s, with arguments: %s, %s", action, args, kwargs)

            result = func(*args, **kwargs)
            if result is None:
                return MonitorActionResult.result_normal

            return result

        # add the action to the wrapper function
        wrapper._monitor_actions = [action.action for action in actions]
        return wrapper

    return decorator


class ActionHandler:
    """
    Base class for handling actions in the monitoring system.
    This class helps processing actions.
    """

    def __init__(self):
        self._action_handlers = {}

    def register_action_handlers(self) -> None:
        """
        Find and register all methods for handling actions in the class.
        This method should be called after initializing the class to ensure that all handlers
        are registered.
        """
        # iterate over all attributes of the class
        for attr_name in dir(self):
            # get the attribute
            attr = getattr(self, attr_name)

            # check if the attribute is a callable and has the _monitor_action attribute
            if callable(attr) and hasattr(attr, "_monitor_actions"):
                actions = getattr(attr, "_monitor_actions")
                for action in actions:
                    self._action_handlers[action] = attr

    def handle_action(self, action: MonitorCommand) -> MonitorActionResult:
        """
        Handle an action by invoking the registered handler.

        Args:
            action: The *MonitorCommand* instance representing the action to be handled.

        Returns:
            A *MonitorActionResult* indicating how the monitoring system should proceed
            after handling the action.
        """
        handler = self._action_handlers.get(action.action)
        if handler:
            # pass the action arguments to the handler
            arguments = asdict(action)
            arguments.pop("action", None)
            logger.debug("Invoking handler for action: %s, with arguments: %s", action, arguments)
            return handler(**arguments)

        return MonitorActionResult.result_normal
