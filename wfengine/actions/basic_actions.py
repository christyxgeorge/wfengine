"""Set of predefined `atomic` actions that can be used in a workflow definition."""

import logging
import random

from typing import Any, Dict, List

from wfengine.base_runner import ActionRegister, BaseRunner, RunStatus

logger = logging.getLogger(__name__)


@ActionRegister(label="Run Search Actions")
class SearchRunner(BaseRunner):
    """Run Search Actions: perform Google Search using SerpApi."""

    def input_keys(self) -> Dict[str, str]:
        return {
            "search_term": "Search Term",
            "num_results": "Number of results to return",
        }

    def output_keys(self) -> List[str]:
        return ["search_results"]

    def run(self, **kwargs) -> Dict[str, Any]:
        """Run the search action."""
        logger.info(f"Search Action: {kwargs}")
        # TODO: Use SerpApi to actually do Google Search. For now, hardcode
        # the results.
        num_results = kwargs.get("num_results", 1)
        results = [f"Hello Workflow Engine {i+1}" for i in range(0, num_results)]
        return {"search_results": results, "status": RunStatus.COMPLETED}


@ActionRegister(label="Run SQL Actions")
class SqlRunner(BaseRunner):
    """Run SQL Action: Run the given SQL statement."""

    def input_keys(self) -> Dict[str, str]:
        return {
            "query": "SQL Query to execute",
            "db_url": "Database URL including the password",
        }

    def output_keys(self) -> List:
        return ["query_result"]

    def run(self, **kwargs) -> Dict[str, Any]:
        """Run the SQL action."""
        query = kwargs.get("query")
        logger.info(f"SQL Action: {query} // {kwargs}")
        return {
            "query_result": [{"a": 1, "b": 2}, {"a": 2, "b": 3}],
            "status": RunStatus.COMPLETED,
        }


@ActionRegister(label="Run an action on multiple inputs")
class MultiActionRunner(BaseRunner):
    """Run the same action on multiple inputs."""

    def input_keys(self) -> Dict[str, str]:
        return {"action": "Action to execute", "inputs": "Inputs to operate on"}

    def output_keys(self) -> List:
        return ["results"]

    def run(self, **kwargs):  # -> Dict[str, Any]:
        """Run the Multi action."""
        logger.info(f"Multi Action: {kwargs}")
        action = kwargs.get("action")
        inputs = kwargs.get("inputs")
        results = []
        for input in inputs:
            # TODO: Need to run these asynchronously (so that they are run in parallel)
            action_instance = self.get_action(action)
            # TODO: Need input mapping here and possibly output mapping as well... for query
            result = action_instance.run(query=input, **kwargs)
            status = result.pop("status", RunStatus.UNKNOWN)
            reason = result.pop("reason", "Step status is unknown")
            if status.not_successful():
                return {
                    "results": results,
                    "status": status,
                    "reason": f"Action {action} failed: {result}",
                }
            results.append(result)
        return {"results": results, "status": status, "reason": reason}


@ActionRegister(label="Fork Actions")
class ForkActionRunner(MultiActionRunner):
    """Fork Action: Allow for forking and joining of workflows."""

    def input_keys(self) -> Dict[str, str]:
        return {"actions": "Actions to execute", "inputs": "Inputs to operate on"}

    def output_keys(self) -> List:
        return ["results"]

    def run(self, **kwargs) -> Dict[str, Any]:
        """Run the Fork action."""
        logger.info(f"Fork Action: {kwargs}")
        actions = kwargs.get("actions")
        inputs = kwargs.get("inputs")
        if not actions or not inputs:
            raise ValueError("Actions and Inputs must be specified")
        if len(actions) != len(inputs):
            raise ValueError("Number of actions and inputs must be same")

        results = []  # type: ignore
        for action, input in zip(actions, inputs):
            # TODO: Need to run these asynchronously (so that they are run in parallel)
            result = action.run(input)
            status = result.pop("status", RunStatus.UNKNOWN)
            reason = result.pop("reason", "Step status is unknown")
            if status.not_successful():
                return {
                    "results": results,
                    "status": status,
                    "reason": f"Action {action} failed: {result}",
                }
            results.append(result)
        return {"results": results, "status": status, "reason": reason}


@ActionRegister(label="Delay Actions")
class DelayActionRunner(BaseRunner):
    """Delay Action: Allow for introducing a delay in the workflow execution."""

    def input_keys(self) -> Dict[str, str]:
        return {"delay": "Delay in seconds"}

    def output_keys(self) -> List:
        return []

    def run(self, **kwargs) -> Dict[str, Any]:
        """Run the Delay action."""
        # TODO: Cannot sleep for 1 day... Need to setup a time based trigger!
        logger.info(f"Delay Action: {kwargs}")
        return {"status": RunStatus.WAITING}


@ActionRegister(label="Notification Actions")
class NotificationRunner(BaseRunner):
    """Notification Action: Notifying a set of users via Email."""

    def input_keys(self) -> Dict[str, str]:
        # NOTE: recipients is an optional parameter. If not defined, we will use the
        # owner of the workflow as the recipient.
        # return {"recipients": "Email IDs of recipients"}
        return {}

    def output_keys(self) -> List:
        return []

    def run(self, **kwargs) -> Dict[str, Any]:
        """Run the Notification action."""
        recipients = kwargs.get("recipients")
        if not recipients:
            recipients = [kwargs.get("owner")]
        logger.info(f"Notification Sent to [{recipients}]: {kwargs}")
        return {"status": RunStatus.COMPLETED}


@ActionRegister(label="Approval Actions")
class ApprovalRunner(BaseRunner):
    """Approval Action: Allow for getting approvals during a workflow execution."""

    def input_keys(self) -> Dict[str, str]:
        return {
            "approvers": "Approver Email IDs",
            "retry_count": "Number of attempts",
            "retry_delay": "Delay between retries (in secs)",
            "escalations": "Escalation Email IDs",
            "timeout": "Timeout (in secs)",
        }

    def output_keys(self) -> List:
        return []

    def run(self, **kwargs) -> Dict[str, Any]:
        """Run the Approval action. Wait for the approval to be completed via Email/UI."""
        approvers = kwargs.get("approvers")
        if approvers:
            logger.info(f"Waiting for approval from {approvers}: {kwargs}")
            return {
                "status": RunStatus.WAITING,
                "approved": False,
                "pending_approvers": approvers,
                "reason": "Waiting for approval",
            }
        else:
            return {
                "status": RunStatus.FAILED,
                "approved": False,
                "pending_approvers": approvers,
                "reason": "No approvers specified",
            }

    def resume(self, **kwargs) -> Dict[str, Any]:
        """Resume the workflow with the transaction_id"""
        # TODO: Handle escalations, rejections, etc.
        # Timeout will need to be handled by an external trigger
        logger.info(f"Approval Action: {kwargs}")
        approved_by = kwargs.get("approved_by")
        pending_approvers = kwargs.get("pending_approvers", [])
        pending_approvers = [a for a in pending_approvers if a != approved_by]
        if pending_approvers:
            return {
                "status": RunStatus.WAITING,
                "approved": False,
                "pending_approvers": pending_approvers,
            }
        return {
            "status": RunStatus.COMPLETED,
            "approved": True,
            "pending_approvers": pending_approvers,
        }


@ActionRegister(label="Run General Function Actions")
class FunctionRunner(BaseRunner):
    """Run General Function Actions"""

    def input_keys(self) -> Dict[str, str]:
        return {"func": "Function to execute", "input": "Input to operate on"}

    def output_keys(self) -> List:
        return ["func_result"]

    def run(self, **kwargs) -> Dict[str, Any]:
        """Run the function."""
        func = kwargs.get("func")
        input = kwargs.get("input")
        logger.info(f"Function Action: {func} // {input}")
        match func:
            case "upper":
                input = [input] if isinstance(input, str) else input
                value = [i.upper() for i in input] if input else ""
            case "num_words":
                # Handles array of strings, string. Returns number of words
                input = [input] if isinstance(input, str) else input
                value = sum([len(i.split()) for i in input]) if input else 0
            case "gen_rand":
                (min, max) = input.split(",") if input else (0, 100)
                value = random.randint(int(min), int(max))  # noqa: S311 #nosec
                logger.info(f"Random value generated = {value}")
            case "format":
                template = kwargs.get("template")
                value = template.format(**kwargs) if template else ""
            case "sum_rows":
                value = sum([len(i) for i in input]) if input else 0
            case _:
                raise ValueError(f"Unsupported function: {func}")
        return {"func_result": value}
