"""Base Runner module; Can be a workflow or an action (step)."""
from __future__ import annotations

import logging

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, ClassVar, Dict, List, Type

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class RunStatus(str, Enum):
    """Step Status"""

    STARTED = "Started"
    COMPLETED = "Completed"
    DENIED = "Denied"  # Permission
    SKIPPED = "Skipped"  # Step Execution Conditions not met
    FAILED = "Failed"
    KILLED = "Killed"  # Timeout
    CANCELLED = "Cancelled"  # User Cancelled
    WAITING = "Waiting"  # Waiting for some trigger to happen
    UNKNOWN = "Unknown"

    def not_successful(self) -> bool:
        """Return True if the step has ended unsuccessfully."""
        return self in [RunStatus.CANCELLED, RunStatus.FAILED, RunStatus.KILLED]

    def is_waiting(self) -> bool:
        """Return True if the step is waiting for some trigger to happen."""
        return self == RunStatus.WAITING


class ActionRegister(object):
    """Class Decorater to register the list of supported action"""

    def __init__(self, *, label: str) -> None:
        # NOTE: Label can also be extracted from the docstring.
        self.action_label = label

    def __call__(self, clz: Type[BaseRunner]) -> Type[BaseRunner]:
        """Register the list of supported actions"""
        action_key = clz.__name__  # Use Class Name
        logger.debug(f"=*=*= Adding Action = {action_key} // {clz} =*=*=")
        BaseRunner.register_action(action_key, clz, self.action_label)
        return clz


class BaseRunner(BaseModel, ABC):
    actions: ClassVar[Dict[str, Dict[str, Any]]] = {}

    @property
    def name(self):
        """Return the name for the runner. By default return the class name"""
        return f"{self.__class__.__name__}"

    @abstractmethod
    def input_keys(self) -> Dict[str, Any]:
        """Return the Dictionary of input keys & UI labels for the action."""
        # TODO: Need to have a way to specify whether the key is mandatory
        # or optional. For now, we will assume that all keys are mandatory.
        # Optional keys are not included in this function

    @abstractmethod
    def output_keys(self) -> List[str]:
        """Return the list of output keys for the action."""
        # TODO: This also needs to have the UI labels.

    @abstractmethod
    def run(self, **kwargs) -> Dict[str, Any]:
        """Run the workflow or step/action."""

    def resume(self, **kwargs) -> Dict[str, Any]:
        """Resume the workflow with the transaction_id"""
        raise NotImplementedError("Resumption is not supported")

    def get_action(self, action_key: str) -> BaseRunner:
        """Get the step with the given ID."""
        action_info = BaseRunner.actions.get(action_key, None)
        if not action_info:
            raise ValueError(f"Action Key {action_key} not found")
        return action_info["class"]()

    @staticmethod
    def register_action(action_key: str, action_class, action_label: str) -> None:
        BaseRunner.actions[action_key] = {
            "class": action_class,
            "label": action_label,
        }
