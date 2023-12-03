"""Workflow module."""
from __future__ import annotations

import ast
import logging

# from string import Formatter
from typing import Any, Dict, List, Tuple

from pydantic import BaseModel, Field, model_validator

from wfengine.base_runner import BaseRunner, RunStatus

logger = logging.getLogger(__name__)


class Condition(BaseModel):
    """A Generic Condition that can be validated"""

    expression_template: str
    """The expression template to check"""

    def _get_ast_expression(
        self, template, wf_context, step_name, step_parameters
    ) -> str:
        """Extract Prompt Variables and check the partial variables, if any"""

        kwargs = {
            **wf_context["wf_parameters"],
            **step_parameters,
            **wf_context["metadata"],
            **wf_context["variables"],
            "owner": wf_context["owner"],
            "step_name": step_name,
            "working_dir": wf_context["working_dir"],
        }

        # Get the variables for the template
        # template_variables = {
        #     v for _, v, _, _ in Formatter().parse(template) if v is not None
        # }
        # logger.debug(f"Template Variables = {template_variables}")
        # Actually, we dont need the template variables!
        # kwargs = {k: v for k, v in kwargs.items() if k in template_variables}

        ast_expression = template.format(**kwargs)
        return ast_expression

    def evaluate(self, wf_context, step_name, step_parameters) -> bool:
        expression = self._get_ast_expression(
            self.expression_template, wf_context, step_name, step_parameters
        )
        code = ast.parse(expression, mode="eval")
        codeobj = compile(code, "<string>", "eval")
        expr_result = eval(codeobj)  # nosec
        logger.debug(
            f"== Condition = {self.expression_template}; Expression = {expression}, "
            f"Result = {expr_result}"
        )
        return bool(expr_result)


class WFResult(BaseModel):
    """The result of a step execution"""

    step_id: str
    """The Step ID"""

    action: str
    """The Step Action"""

    inputs: Dict[str, Any]
    """The inputs to the action"""

    outputs: Dict[str, Any]
    """The outputs from the action"""

    status: RunStatus
    """The step execution status"""

    completion_reason: str
    """The Completion reason"""


class WFStep(BaseModel):

    """The workflow Step"""

    id: str
    """Step ID [Unique across all the steps in the workflow]"""

    desc: str
    """The description of the Workflow Step."""

    action: BaseRunner
    """
    The ActioNRunner/WFRunner to run the step. [Can be another Workflow or a Task]]
    """

    parameters: Dict[str, Any] = {}
    """Any extra parameters defined in the workflow"""

    input_keys: List[str]
    output_keys: List[str]
    """Input and Output keys for the step"""

    exec_if: List[Condition] = []
    """The conditions to be satisfied for the step to be executed."""

    input_mapping: Dict[str, str] = {}
    reverse_input_mapping: Dict[str, str] = {}
    """
    The mapping of workflow context variables to the action input keys for each step
    """

    output_mapping: Dict[str, str] = {}
    """
    The mapping of workflow context variables to the action output keys for each step
    """

    @model_validator(mode="before")
    def set_input_values(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        if not values.get("id"):
            index = values.pop("index")
            raise ValueError(f"Step ID not specified for step [{index}]")

        # Get the ActionRunner for the step.
        action_key = values.get("action")
        if not action_key:
            raise ValueError("Action for the step must be specified")

        action_info = BaseRunner.actions.get(action_key)
        if not action_info:
            raise ValueError(f"Specified Action {action_key} not found")
        action = action_info["class"]()
        values["action"] = action

        # Compute the input keys and output keys needed for the step
        step_parameters = list(values.get("parameters", {}).keys())
        values["input_keys"] = list(
            set(action.input_keys().keys()) - set(step_parameters)
        )
        values["input_keys"] = [
            values.get("input_mapping", {}).get(k, k) for k in values["input_keys"]
        ]
        values["output_keys"] = [
            values.get("output_mapping", {}).get(k, k) for k in action.output_keys()
        ]
        values["reverse_input_mapping"] = {
            value: key for key, value in values.get("input_mapping", {}).items()
        }

        logger.debug(
            f"{values['id']}: Input Keys = {values['input_keys']}"
            f", Output Keys = {values['output_keys']}"
            f", Parameters = {step_parameters}"
        )

        # Setup exec_if conditions for the step
        if values.get("exec_if"):
            values["exec_if"] = (
                [Condition(expression_template=values["exec_if"])]
                if isinstance(values["exec_if"], str)
                else [Condition(expression_template=expr) for expr in values["exec_if"]]
            )

        return values

    def input_mapped_context(self, **kwargs) -> Dict[str, Any]:
        """Create the workflow context for the step with the input mapping."""
        inputs = {}
        for input_key in kwargs:
            mapped_input_key = self.reverse_input_mapping.get(input_key, input_key)
            inputs[mapped_input_key] = kwargs.get(input_key)
        return inputs

    def output_mapped_context(self, **kwargs) -> Dict[str, Any]:
        """Create the workflow context for the step with the output mapping."""
        outputs = {}
        for output_key in kwargs:
            mapped_output_key = self.output_mapping.get(output_key, output_key)
            outputs[mapped_output_key] = kwargs.get(output_key)
        return outputs

    def execute(self, wf_context: Dict[str, Any], resumed_step=False) -> WFResult:
        """Execute the step using the BaseRunner defined for the step."""
        should_exec_step = all(
            condition.evaluate(wf_context, self.id, self.parameters)
            for condition in self.exec_if
        )
        inputs = wf_context["variables"]
        if should_exec_step:
            logger.info(f"Executing Step: {self.id} // {self.action.name}")
            exec_func = self.action.resume if resumed_step else self.action.run
            mapped_inputs = self.input_mapped_context(**inputs)
            outputs = exec_func(
                **wf_context["wf_parameters"],
                **self.parameters,
                **wf_context["metadata"],
                **mapped_inputs,
                owner=wf_context["owner"],
            )
            status = outputs.pop("status", RunStatus.UNKNOWN)
            reason = outputs.pop("reason", f"Step [{status.value}]")
            outputs = self.output_mapped_context(**outputs)
            step_response = WFResult(
                step_id=self.id,
                action=self.action.name,
                inputs=inputs,
                outputs=outputs,
                status=status,
                completion_reason=reason,
            )
        else:
            logger.info(f"Skipping Step: {self.id} // {self.action.name}")
            step_response = WFResult(
                step_id=self.id,
                action=self.action.name,
                inputs=inputs,
                outputs={},
                status=RunStatus.SKIPPED,
                completion_reason="Skipping step: condition not met",
            )

        return step_response


class WFTransition(BaseModel):
    """The workflow Transition"""

    from_step: str
    """The step to transition from."""

    to_step: str
    """The step to transition to."""

    conditions: List[Condition] = []
    """The conditions to be satisfied for the transition."""

    @model_validator(mode="before")
    def set_input_values(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        if values["from_step"] == values["to_step"]:
            raise ValueError(
                f"Transition: From Step [{values['from_step']}] cannot be same "
                f"as next step [{values['to_step']}]"
            )
        conditions = values.get("conditions")
        if conditions:
            values["conditions"] = (
                [Condition(expression_template=conditions)]
                if isinstance(conditions, str)
                else [Condition(expression_template=expr) for expr in conditions]
            )
        logger.debug(f"Transition Values = {values}")
        return values


class Workflow(BaseModel):
    """The workflow Definition"""

    name: str
    """The name of the workflow."""

    description: str = Field(alias="desc")
    """The name of the workflow."""

    parameters: Dict[str, Any] = {}
    """Any pre-defined parameters that are included with the workflow."""

    input_keys: List[str] = []
    """The inputs needed for the agent to execute"""

    output_keys: List[str] = []
    """The outputs provided by the agent"""

    first_step: WFStep
    """Start execution with this steps"""

    steps: Dict[str, WFStep]
    """The steps in the workflow."""

    transitions: List[WFTransition] = []
    """The transitions between the steps."""

    @model_validator(mode="before")
    def set_input_values(cls, values: Dict[str, Any]) -> Dict[str, Any]:
        # Convert from step names to WFStep classes
        inputs = []
        outputs = []
        step_dict = {}
        for i, step_info in enumerate(values["steps"]):
            step_info["index"] = i + 1
            wf_step = WFStep(**step_info)
            logger.debug(f"Added Step = {wf_step}")
            inputs.extend(wf_step.input_keys)
            outputs.extend(wf_step.output_keys)
            if wf_step.id in step_dict:
                raise ValueError(f"Duplicate Step ID: {wf_step.id}")
            step_dict[wf_step.id] = wf_step

        values["steps"] = step_dict

        # Setup the first step
        first_step_id = values.get("first_step")
        if not first_step_id:
            raise ValueError("First Step not specified for the workflow")
        if first_step_id not in step_dict:
            raise ValueError(f"First Step [{first_step_id}] not found")

        values["first_step"] = step_dict.get(values["first_step"])

        # Compute the input keys needed for the workflow
        wf_parameters = list(values.get("parameters", {}).keys())
        wf_inputs = list(set(inputs) - set(outputs) - set(wf_parameters))
        values["input_keys"] = wf_inputs

        return values

    def get_step(self, step_id: str) -> WFStep | None:
        """Get the step with the given ID."""
        return self.steps.get(step_id)

    def get_next_step(
        self, curr_step: WFStep, wf_context: Dict[str, Any]
    ) -> Tuple[str, WFStep | None]:
        """Get the next step to be executed."""
        transitions = [x for x in self.transitions if x.from_step == curr_step.id]
        try:
            for transition in transitions:
                if not transition.conditions:
                    return "OK", self.steps.get(transition.to_step)
                if all(
                    condition.evaluate(wf_context, curr_step.id, curr_step.parameters)
                    for condition in transition.conditions
                ):
                    return "OK", self.steps.get(transition.to_step)
        except Exception as e:
            logger.error(f"Error getting next step for [{curr_step.id}]: {e}")
            return "ERROR", None

        return "OK", None
