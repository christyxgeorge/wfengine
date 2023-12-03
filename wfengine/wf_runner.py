"""WF Runner module."""
from __future__ import annotations

import json
import logging
import os
import sqlite3

from pathlib import Path
from typing import Any, Dict
from uuid import UUID, uuid4

from wfengine.base_runner import ActionRegister, BaseRunner, RunStatus
from wfengine.workflow import WFResult, WFStep, Workflow

logger = logging.getLogger(__name__)


@ActionRegister(label="Run Workflow Actions")
class WFRunner(BaseRunner):
    """Class to orchestrate/run the given workflow."""

    sql_conn: Any  # Sqlite3 connection
    """Sqlite3 connection to store the workflow run details."""

    workflow: Workflow
    transaction_id: UUID | None = None
    working_dir: Path | None = None

    owner: str
    """The owner of the workflow."""

    metadata: Dict[str, Any] = {}
    """Any metadata included with the workflow."""

    @property
    def name(self) -> str:
        return f"WF:{self.workflow.name}"

    @staticmethod
    def from_file(wf_name: str, sql_conn, **kwargs) -> BaseRunner:
        """Create an WFRunner from a definition file."""
        if not wf_name:
            raise ValueError("Workflow name must be provided")

        root_path = Path(os.getenv("WF_ROOT_DIR", os.getcwd()))
        def_file = root_path / "definitions" / f"{wf_name}.json"
        if not def_file.is_file():
            raise ValueError(
                f"Workflow definition file not found: {def_file} [or not a file!]"
            )
        logger.info(f"Loading Workflow from {def_file}")

        try:
            with open(def_file) as f:
                wf_def = json.load(f)
                workflow = Workflow(**wf_def)

            if not kwargs.get("owner"):
                owner = kwargs.get("metadata", {}).get("owner")
                if not owner:
                    raise ValueError("Workflow Owner must be specified")
                kwargs["owner"] = kwargs.get("metadata", {}).pop("owner")
            return WFRunner(
                workflow=workflow,
                sql_conn=sql_conn,
                **kwargs,
            )
        except Exception as e:
            logger.error(f"Error loading workflow {def_file} : {e}")
            raise e

    def input_keys(self):
        return self.workflow.input_keys

    def output_keys(self):
        return self.workflow.output_keys

    def get_last_transaction_id(self) -> str:
        """Get the last transaction ID from the database."""
        cursor = self.sql_conn.cursor()
        result = cursor.execute(
            "SELECT transaction_id FROM wf_run ORDER BY created_at DESC LIMIT 1"
        )
        row = result.fetchone()
        return None if not row else row[0]

    def log_run(self, status: RunStatus, reason: str, context: Dict[str, Any]):
        """Log the workflow run details to the database."""
        cursor = self.sql_conn.cursor()
        cursor.execute(
            """
            INSERT INTO wf_run (
                transaction_id, working_dir, owner, context, status, reason
            ) VALUES (
                ?, ?, ?, ?, ?, ?
            )
            """,
            [
                str(self.transaction_id),
                str(self.working_dir),
                self.owner,
                json.dumps(context),
                status,
                reason,
            ],
        )
        self.sql_conn.commit()

    def update_run(self, status: RunStatus, reason: str, context: Dict[str, Any]):
        """Update the workflow run details to the database."""
        cursor = self.sql_conn.cursor()
        try:
            cursor.execute(
                """
                UPDATE wf_run SET
                    status = ?, reason = ?, context = ?, updated_at = CURRENT_TIMESTAMP
                WHERE
                    transaction_id = ?
                """,
                [status, reason, json.dumps(context), str(self.transaction_id)],
            )
            self.sql_conn.commit()
        except sqlite3.Error as err:
            logger.error(f"Error updating wf_run: {err}")
            raise err

    def log_step_run(self, step: WFStep, result: WFResult):
        """Log the step run details to the database."""
        cursor = self.sql_conn.cursor()
        cursor.execute(
            """
            INSERT INTO wf_step_run (
                wf_id, step_name, input, output, status, reason
            ) VALUES (
                ?, ?, ?, ?, ?, ?
            )
            """,
            [
                str(self.transaction_id),
                step.id,
                json.dumps(result.inputs),
                json.dumps(result.outputs),
                result.status,
                result.completion_reason,
            ],
        )
        self.sql_conn.commit()

    def update_step_run(self, step: WFStep, result: WFResult) -> None:
        """Update the step run details to the database when we have resumed"""
        cursor = self.sql_conn.cursor()
        try:
            cursor.execute(
                """
                UPDATE wf_step_run SET
                    input = ?, output = ?, status = ?, reason = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE
                    wf_id = ? AND step_name = ?
                """,
                [
                    json.dumps(result.inputs),
                    json.dumps(result.outputs),
                    result.status,
                    result.completion_reason,
                    str(self.transaction_id),
                    step.id,
                ],
            )
            self.sql_conn.commit()
        except sqlite3.Error as err:
            logger.error(f"Error updating wf_step_run: {err}")
            raise err

    def get_row_dict(self, cursor, row):
        row_dict = {}
        for idx, col in enumerate(cursor.description):
            row_dict[col[0]] = row[idx]
        return row_dict

    def restore_transaction(self, transaction_id: UUID | None, **kwargs):
        """Resume a workflow from a previous run."""
        cursor = self.sql_conn.cursor()
        result = cursor.execute(
            "SELECT * FROM wf_run where transaction_id = ?", [str(transaction_id)]
        )
        row = result.fetchone()
        if not row:
            raise ValueError(
                f"Transaction ID not found: {transaction_id}, Cannot resume"
            )
        row_dict = self.get_row_dict(cursor, row)
        return row_dict

    def get_waiting_step(self, transaction_id: UUID) -> str:
        cursor = self.sql_conn.cursor()
        result = cursor.execute(
            "SELECT * FROM wf_step_run where wf_id = ? and status = ?",
            [str(transaction_id), RunStatus.WAITING.value],
        )
        # [LATER] What if two steps are waiting? In that case, we will need a CLI
        # argument to indicate which step to resume. Anyways, from the front-end,
        # we will always know that.
        row = result.fetchone()
        if not row:
            raise ValueError(
                f"No Step found in waiting state: {transaction_id}, Cannot resume"
            )
        row_dict = self.get_row_dict(cursor, row)
        logger.debug(f"Step Run [Waiting] = {row_dict['step_name']} // {row_dict}")
        return row_dict["step_name"]

    def resume(self, **kwargs) -> Dict[str, Any]:
        transaction_id = kwargs.pop("transaction_id")
        if transaction_id == "last":
            transaction_id = self.get_last_transaction_id()

        if not transaction_id:
            raise ValueError("Transaction ID must be provided")

        logger.info(
            f"Workflow resumed: {self.workflow.name} // {self.workflow.first_step} "
            f"// {transaction_id}"
        )
        # Restore context from the working directory and continue
        if transaction_id:
            transaction_id = UUID(transaction_id)
        db_row = self.restore_transaction(transaction_id, **kwargs)
        self.transaction_id = transaction_id
        self.working_dir = Path(db_row["working_dir"])
        self.owner = db_row["owner"]
        context = json.loads(db_row["context"])
        logger.debug(f"Context: {context} / Kwargs: {kwargs}")
        context.update(kwargs)

        curr_step_id = self.get_waiting_step(transaction_id)
        curr_step = self.workflow.get_step(curr_step_id)
        if not curr_step:
            raise ValueError(f"Resume Step not found: {curr_step_id}")

        return self.run_internal(
            curr_step,
            status=RunStatus(db_row["status"]),
            completion_reason=db_row["reason"],
            **context,
        )

    def run(self, **kwargs) -> Dict[str, Any]:
        logger.info(
            f"Workflow invoked: {self.workflow.name} // {self.workflow.first_step} "
            f"// {self.transaction_id}"
        )
        root_path = Path(os.getenv("WF_ROOT_DIR", os.getcwd()))
        status = RunStatus.STARTED
        completion_reason = "Workflow Started"
        self.transaction_id: UUID = uuid4()
        self.working_dir = root_path / "workflows" / str(self.transaction_id)
        # self.working_dir.mkdir(parents=True, exist_ok=True)
        self.log_run(status, completion_reason, kwargs)

        curr_step: WFStep | None = self.workflow.first_step
        return self.run_internal(
            curr_step, status=status, completion_reason=completion_reason, **kwargs
        )

    def run_internal(
        self, curr_step, status, completion_reason, **kwargs
    ) -> Dict[str, Any]:
        # Save the first step. We will need this to handle resumed workflow
        first_step_id = curr_step.id
        resumed_step_id = (
            first_step_id if (first_step_id != self.workflow.first_step.id) else None
        )

        # Check if all the required inputs are available in the kwargs, parameters
        # included in definition
        missing_inputs = list(set(self.workflow.input_keys) - set(list(kwargs.keys())))
        if missing_inputs:
            raise ValueError(
                f"Inputs not provided [{len(missing_inputs)}]: {missing_inputs}"
            )

        # Check if the owner is valid and allowed to invoke this workflow
        # Hard-coding for now, but we need to check permissions to ensure
        # the owner exists and allowed to invoke this workflow
        # [Multi-tenancy check will also happen here]
        if self.owner != "abc@example.com":
            raise ValueError(f"Owner not permitted for this workflow: {self.owner}")

        # Setup the context
        wf_context = {
            "wf_parameters": self.workflow.parameters,
            "metadata": self.metadata,
            "owner": self.owner,
            "working_dir": self.working_dir,
            "variables": kwargs,
        }

        logger.info(
            f"============ Executing Workflow @ {curr_step.id} [{status}] ============"
        )

        # Get the first step to execute
        while curr_step:
            curr_step_id = curr_step.id
            resumed_step = resumed_step_id == curr_step_id
            result: WFResult = curr_step.execute(wf_context, resumed_step=resumed_step)
            logger.info(f"Result: {result}")
            wf_context["variables"].update(result.outputs)  # type: ignore
            if resumed_step:
                # We have resumed the workflow, and the first step has changed!
                # We need to update the first step and continue
                self.update_step_run(curr_step, result)
            else:
                self.log_step_run(curr_step, result)

            # Check Status, and get the next step
            if result.status.not_successful():
                status = result.status
                completion_reason = result.completion_reason
                curr_step = None
            elif result.status.is_waiting():
                status = result.status
                completion_reason = result.completion_reason
                curr_step = None
            else:
                # Get the next step [When step is COMPLETED, SKIPPED, DENIED]
                ns_status, curr_step = self.workflow.get_next_step(
                    curr_step, wf_context
                )
                status = RunStatus.COMPLETED if ns_status == "OK" else RunStatus.FAILED
                if ns_status != "OK":
                    completion_reason = f"Next step not found for [{curr_step_id}]"
                    curr_step = None
                else:
                    completion_reason = (
                        f"Step [{curr_step_id}] Completed"
                        if curr_step
                        else "Workflow Completed"
                    )

            # End While Loop
        self.update_run(status, completion_reason, wf_context["variables"])
        logger.info(
            f"Workflow {self.workflow.name} / Step {curr_step_id} / "
            f"{self.transaction_id} => {status} // {completion_reason}"
        )
        return {
            "status": status,
            "reason": completion_reason,
            **wf_context["variables"],  # type: ignore
        }
