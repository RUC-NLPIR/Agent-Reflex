from copy import deepcopy
from enum import Enum
from pathlib import Path
from typing import Optional

import pandas as pd
from pydantic import BaseModel, Field
from typing_extensions import Annotated

from tau2.config import (
    DEFAULT_LLM_AGENT,
    DEFAULT_LLM_ARGS_AGENT,
    DEFAULT_LLM_ARGS_USER,
    DEFAULT_LLM_USER,
    DEFAULT_LOG_LEVEL,
    DEFAULT_MAX_CONCURRENCY,
    DEFAULT_MAX_ERRORS,
    DEFAULT_MAX_STEPS,
    DEFAULT_NUM_TRIALS,
    DEFAULT_SAVE_TO,
    DEFAULT_SEED,
)
from tau2.data_model.message import Message
from tau2.data_model.tasks import Action, EnvAssertion, RewardType, Task
from tau2.environment.environment import EnvironmentInfo
from tau2.utils.utils import get_now


class RunConfig(BaseModel):
    domain: Annotated[
        str,
        Field(
            description="The domain to run the simulation on",
            default="airline",
        ),
    ]
    task_set_name: Annotated[
        Optional[str],
        Field(
            description="The task set to run the simulation on. If not provided, will load default task set for the domain.",
            default=None,
        ),
    ]
    task_ids: Annotated[
        Optional[list[str]],
        Field(
            description="The task IDs to run the simulation on",
            default=None,
        ),
    ]
    num_tasks: Annotated[
        Optional[int],
        Field(
            description="The number of tasks to run the simulation on",
            default=None,
        ),
    ]
    is_remote: Annotated[
        bool,
        Field(
            description="Whether to run the simulation remotely",
            default=False,
        ),
    ]
    agent: Annotated[
        str,
        Field(
            description="The type of agent to run the simulation on",
            default="llm_agent",
        ),
    ]
    llm_agent: Annotated[
        str,
        Field(
            description="The model to use for the agent",
            default=DEFAULT_LLM_AGENT,
        ),
    ]
    llm_args_agent: Annotated[
        dict,
        Field(
            description="The arguments to pass to the LLM for the agent",
            default_factory=lambda: deepcopy(DEFAULT_LLM_ARGS_AGENT),
        ),
    ]
    user: Annotated[
        str,
        Field(
            description="The type of user to run the simulation on",
            default="user_simulator",
        ),
    ]
    llm_user: Annotated[
        str,
        Field(
            description="The model to use for the user",
            default=DEFAULT_LLM_USER,
        ),
    ]
    llm_args_user: Annotated[
        dict,
        Field(
            description="The arguments to pass to the LLM for the user",
            default_factory=lambda: deepcopy(DEFAULT_LLM_ARGS_USER),
        ),
    ]
    num_trials: Annotated[
        int,
        Field(
            description="The number of trials to run the simulation on",
            default=DEFAULT_NUM_TRIALS,
        ),
    ]
    max_steps: Annotated[
        int,
        Field(
            description="The maximum number of steps to run the simulation",
            default=DEFAULT_MAX_STEPS,
        ),
    ]
    max_errors: Annotated[
        int,
        Field(
            description="The maximum number of tool errors allowed in a row in the simulation",
            default=DEFAULT_MAX_ERRORS,
        ),
    ]
    save_to: Annotated[
        Optional[str],
        Field(
            description="The path to json file where to save the simulation results",
            default=DEFAULT_SAVE_TO,
        ),
    ]
    max_concurrency: Annotated[
        int,
        Field(
            description="The maximum number of concurrent simulations to run",
            default=DEFAULT_MAX_CONCURRENCY,
        ),
    ]
    seed: Annotated[
        Optional[int],
        Field(
            description="The seed to use for the simulation",
            default=DEFAULT_SEED,
        ),
    ]
    log_level: Annotated[
        Optional[str],
        Field(
            description="The log level to use for the simulation",
            default=DEFAULT_LOG_LEVEL,
        ),
    ]
    user_noise: Annotated[
        str,
        Field(
            description="The noise for the user simulation",
            default='original',
        ),
    ]
    noise_category: Annotated[                                                                            # 下面三个为新增代码
        str,
        Field(
            description="Add noise to tool responses. 'fault' simulates a failed tool call by replacing the result with a random HTTP error; 'wrong', 'induce', 'redundant', 'incomplete' rewrite it through the injector; 'others' injects nothing. Omit to skip",
            default=None,
        ),
    ]
    priority_level: Annotated[
        int,
        Field(
            description="Set the priority level for task processing (higher number = higher priority). Default is 1",
            default=1,
        ),
    ]
    noise_nums: Annotated[
        int,
        Field(
            description="Number of tool calls to apply noise to. Default: 2",
            default=2,
        ),
    ]
    enable_think: Annotated[
        bool,
        Field(
            description="Whether to enable think step for the agent",
            default=False,
        ),
    ]
    max_single_tool_noise: Annotated[
        int,
        Field(
            description="Number of a single tool calls to apply noise to. Default: 1",
            default=1,
        ),
    ]
    def validate(self) -> None:
        """
        Validate the run config
        """
        pass


class NLAssertionCheck(BaseModel):
    """
    A natural language assertion.
    """

    nl_assertion: str
    met: bool
    justification: str


class CommunicateCheck(BaseModel):
    """
    A communication check.
    """

    info: str
    met: bool
    justification: str


class DBCheck(BaseModel):
    """
    A database check.
    """

    db_match: bool
    db_reward: float


class ActionCheck(BaseModel):
    """
    An action check.
    """

    action: Action
    action_match: bool
    action_reward: float


class EnvAssertionCheck(BaseModel):
    """
    An environment assertion check.
    """

    env_assertion: EnvAssertion
    met: bool
    reward: float


class NoiseInjection(BaseModel):
    """
    A tool-side noise injection, recorded at the moment it happens.

    The injector is the only place that knows the original payload and the exact
    text it substituted in; keeping the pair lets the evaluator judge deviation
    against ground truth instead of re-inferring the noise from the transcript.
    """

    tool_id: str = Field(description="Id of the tool call whose response was poisoned.")
    tool_name: str = Field(description="Name of the tool whose response was poisoned.")
    category: str = Field(description="The noise category that was applied.")
    turn_idx: Optional[int] = Field(
        description="Turn index of the poisoned tool response.", default=None
    )
    original: Optional[str] = Field(
        description="The tool response before injection.", default=None
    )
    injected: Optional[str] = Field(
        description="The tool response after injection.", default=None
    )


class StepDeviationCheck(BaseModel):
    """
    Per-injection verdict: did the agent act on this specific injected content?

    `deviated=None` means the judge could not be reached and is deliberately kept
    distinct from a clean verdict.
    """

    tool_name: str
    deviated: Optional[bool] = None
    turn_idx: Optional[int] = None
    justification: str = ""


class RewardInfo(BaseModel):
    """
    The reward received by the agent.
    """

    reward: Annotated[float, Field(description="The reward received by the agent.")]
    average_nl_reward: Annotated[float, Field(description="The nl average reward received by the agent.", default=0.0),]
    task_success: Annotated[
        Optional[float],
        Field(
            description=(
                "I_task: task completion scored on the same basis as an origin run. "
                "Comparable across noise categories."
            ),
            default=None,
        ),
    ]
    task_nl_reward: Annotated[
        Optional[float],
        Field(
            description=(
                "Mean of the NL assertions alone. `average_nl_reward` additionally folds "
                "the deviation verdict into the same mean, which shifts its denominator "
                "for induce/redundant and breaks comparison against an origin run."
            ),
            default=None,
        ),
    ]
    traj_ok: Annotated[
        Optional[bool],
        Field(
            description=(
                "I_traj: True when no injected lure steered the agent, False when at "
                "least one did, None when the deviation judge was unavailable."
            ),
            default=None,
        ),
    ]
    sga: Annotated[
        Optional[float],
        Field(
            description="SGA = I_traj * I_task. None when I_traj is unavailable.",
            default=None,
        ),
    ]
    step_deviations: Annotated[
        Optional[list[StepDeviationCheck]],
        Field(description="Per-injection deviation verdicts.", default=None),
    ]
    db_check: Annotated[
        Optional[DBCheck], Field(description="The database check.", default=None)
    ]
    env_assertions: Annotated[
        Optional[list[EnvAssertionCheck]],
        Field(description="The environment assertions.", default=None),
    ]
    action_checks: Annotated[
        Optional[list[ActionCheck]],
        Field(description="The action checks.", default=None),
    ]
    bool_deviation: Annotated[
        # Declared as `str` with `default=None`, which made model_dump_json() emit
        # `null` and then refuse to validate it back, so no saved simulation could be
        # reloaded. Only the annotation is widened to match the existing default; the
        # field itself is left in place and still unassigned.
        Optional[str],
        Field(description="Whether it deviates from the original trajectory.", default=None),
    ]
    nl_assertions: Annotated[
        Optional[list[NLAssertionCheck]],
        Field(description="The natural language assertions.", default=None),
    ]
    communicate_checks: Annotated[
        Optional[list[CommunicateCheck]],
        Field(
            description="Checks that the agent communicated the required information.",
            default=None,
        ),
    ]
    reward_basis: Annotated[
        Optional[list[RewardType]],
        Field(
            description="The basis of the reward. Fields that are used to calculate the reward.",
            default_factory=lambda: [RewardType.DB],
        ),
    ]
    reward_breakdown: Annotated[
        Optional[dict[RewardType, float]],
        Field(
            description="The breakdown of the reward.",
            default=None,
        ),
    ]
    info: Annotated[
        Optional[dict],
        Field(description="Additional information about the reward.", default=None),
    ]


class AgentInfo(BaseModel):
    """
    Agent information.
    """

    implementation: str = Field(description="The type of agent.")
    llm: Optional[str] = Field(description="The LLM used by the agent.", default=None)
    llm_args: Optional[dict] = Field(
        description="The arguments to pass to the LLM for the agent.", default=None
    )


class UserInfo(BaseModel):
    """
    User information.
    """

    implementation: str = Field(description="The type of user.")
    llm: Optional[str] = Field(description="The LLM used by the user.", default=None)
    llm_args: Optional[dict] = Field(
        description="The arguments to pass to the LLM for the user.", default=None
    )
    global_simulation_guidelines: Optional[str] = Field(
        description="The global simulation guidelines for the user.", default=None
    )


class Info(BaseModel):
    """Information about the simulator."""

    git_commit: str = Field(description="The git commit hash.")
    num_trials: int = Field(description="The number of trials.")
    max_steps: int = Field(description="The maximum number of steps.")
    max_errors: int = Field(description="The maximum number of errors.")
    user_info: UserInfo = Field(description="User information.")
    agent_info: AgentInfo = Field(description="Agent information.")
    environment_info: EnvironmentInfo = Field(description="Environment information.")
    seed: Optional[int] = Field(
        description="The seed used for the simulation.", default=None
    )


class TerminationReason(str, Enum):
    USER_STOP = "user_stop"
    AGENT_STOP = "agent_stop"
    MAX_STEPS = "max_steps"
    TOO_MANY_ERRORS = "too_many_errors"
    TASK_TIMEOUT = "task_timeout"


class SimulationRun(BaseModel):
    """
    Simulation run for the given task.
    """

    id: str = Field(description="The unique identifier for the simulation run.")
    task_id: str = Field(description="The unique identifier for the task.")
    timestamp: str = Field(
        description="The timestamp of the simulation.", default_factory=get_now
    )
    start_time: str = Field(description="The start time of the simulation.")
    end_time: str = Field(description="The end time of the simulation.")
    duration: float = Field(description="The duration of the simulation.")
    termination_reason: TerminationReason = Field(
        description="The reason for the termination of the simulation."
    )
    agent_cost: Optional[float] = Field(
        description="The cost of the agent.", default=None
    )
    user_cost: Optional[float] = Field(
        description="The cost of the user.", default=None
    )
    reward_info: Optional[RewardInfo] = Field(
        description="The reward received by the agent.", default=None
    )
    messages: list[Message] = Field(
        description="The messages exchanged between the user, agent and environment."
    )
    trial: Optional[int] = Field(description="Trial number", default=None)
    seed: Optional[int] = Field(
        description="Seed used for the simulation.", default=None
    )
    noise_injections: Optional[list[NoiseInjection]] = Field(
        description="Tool-side noise injections recorded during the simulation.",
        default=None,
    )


class Results(BaseModel):
    """
    Run results
    """

    timestamp: Optional[str] = Field(
        description="The timestamp of the simulation.", default_factory=get_now
    )
    info: Info = Field(description="Information.")
    tasks: list[Task] = Field(description="The list of tasks.")
    simulations: list[SimulationRun] = Field(description="The list of simulations.")

    @classmethod
    def load(cls, path: Path) -> "Results":
        with open(path, "r") as f:
            return cls.model_validate_json(f.read())

    def save(self, path: Path) -> None:
        """
        Save the results to a file.
        """
        with open(path, "w") as f:
            f.write(self.model_dump_json(indent=4))

    def to_df(self) -> pd.DataFrame:
        """
        Convert a Results object to a pandas DataFrame.
        """

        def transfer_only(task: Task) -> bool:
            """
            Check if the task is a transfer only task.
            """
            if task.evaluation_criteria is None:
                return False
            if task.evaluation_criteria.actions is None:
                return False
            actions = task.evaluation_criteria.actions
            if len(actions) != 1:
                return False
            action = actions[0]
            if "transfer" in action.name.lower():
                return True
            return False

        def get_task_metrics(task: Task) -> dict:
            eval_metrics = (
                task.evaluation_criteria.info()
                if task.evaluation_criteria is not None
                else {}
            )
            num_actions = (
                eval_metrics["num_agent_actions"] + eval_metrics["num_user_actions"]
            )
            if transfer_only(task):
                num_actions = -1
            info = {
                "task_num_agent_actions": eval_metrics["num_agent_actions"],
                "task_num_user_actions": eval_metrics["num_user_actions"],
                "task_num_actions": num_actions,
                "task_num_env_assertions": eval_metrics["num_env_assertions"],
                "task_num_nl_assertions": eval_metrics["num_nl_assertions"],
            }
            return info

        rows = []
        for sim in self.simulations:
            row = {
                "simulation_id": sim.id,
                "task_id": sim.task_id,
                "trial": sim.trial,
                "seed": sim.seed,
                "reward": sim.reward_info.reward,
                "agent_cost": sim.agent_cost,
                "user_cost": sim.user_cost,
                "termination_reason": sim.termination_reason,
                "duration": sim.duration,
                "num_messages": len(sim.messages),
                "info_git_commit": self.info.git_commit,
                "info_seed": self.info.seed,
                "info_num_trials": self.info.num_trials,
                "info_max_steps": self.info.max_steps,
                "info_max_errors": self.info.max_errors,
                "info_domain": self.info.environment_info.domain_name,
                "info_user_implementation": self.info.user_info.implementation,
                "info_user_llm": self.info.user_info.llm,
                "info_user_llm_args": self.info.user_info.llm_args,
                "info_agent_implementation": self.info.agent_info.implementation,
                "info_agent_llm": self.info.agent_info.llm,
                "info_agent_llm_args": self.info.agent_info.llm_args,
            }
            task = next(t for t in self.tasks if t.id == sim.task_id)
            row.update(get_task_metrics(task))
            rows.append(row)
        return pd.DataFrame(rows)
