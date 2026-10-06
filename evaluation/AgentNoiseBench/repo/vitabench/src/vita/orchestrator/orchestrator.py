
import time
import uuid
from copy import deepcopy
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional, Dict
from loguru import logger

from vita.agent.base import BaseAgent, is_valid_agent_history_message
from vita.data_model.message import (
    AssistantMessage,
    Message,
    MultiToolMessage,
    ToolMessage,
    UserMessage,
)
from vita.data_model.simulation import NoiseInjection, SimulationRun, TerminationReason
from vita.data_model.tasks import Task
from vita.environment.db import DB
from vita.environment.environment import Environment
from vita.user.base import BaseUser, is_valid_user_history_message
from vita.user.user_simulator import UserSimulator, UserState
from vita.utils.llm_utils import get_cost
from vita.utils.task_deadline import check_deadline
from vita.utils.utils import format_time, get_now, DATA_DIR
from vita.config import Config_API, DEFAULT_LANGUAGE
from vita.noise.make_noisy import tool_noise_bench
from vita.noise.system_prompt import zh_add_wrong, zh_add_induce, zh_add_redundant, zh_add_incomplete, en_add_wrong, en_add_induce, en_add_redundant, en_add_incomplete
from vita.utils.display import ConsoleDisplay
from vita.noise.tools import delivery_tool, instore_tool, ota_tool

class Role(str, Enum):
    AGENT = "agent"
    USER = "user"
    ENV = "env"
def replace_placeholders(template_str, tool_msg, user_msg, priority_level):
    """
    替换模板字符串中的占位符
    
    Args:
        template_str: 包含占位符的模板字符串
        tool_msg: 替换 %prompt1% 的内容
        user_msg: 替换 %prompt2% 的内容  
        priority_level: 替换 %prompt3% 的内容
    
    Returns:
        str: 替换后的完整字符串
    """
    # 使用字符串的replace方法进行多次替换
    result = template_str.replace("%prompt1%", tool_msg)
    result = result.replace("%prompt2%", user_msg)
    result = result.replace("%prompt3%", str(priority_level))
    
    return result

def get_default_first_agent_message(language: str = None) -> AssistantMessage:
    """Get the default first agent message based on language"""
    if language is None:
        language = DEFAULT_LANGUAGE
    
    content = "你好，请问需要什么服务？" if language == "chinese" else "Hello, how can I help you?"
    return AssistantMessage(
        role="assistant", content=content, cost=0.0
    )


class Orchestrator:
    """
    Orchestrator for the simulation given a task.
    Passes messages between the Agent, User, and Environment.
    """

    def __init__(
        self,
        domain: str,
        agent: BaseAgent,
        user: BaseUser,
        environment: Environment,
        task: Task,
        max_steps: int = 100,
        max_errors: int = 10,
        seed: Optional[int] = None,
        solo_mode: bool = False,
        language: str = None,
        noise_category: str = None,  # 新增参数
        priority_level: int = 1,
        noise_nums: int = 1,  # 新增参数
        max_single_tool_noise: int = 2,
    ):
        self.domain = domain
        self.agent = agent
        self.user = user
        self.environment = environment
        self.task = task
        self.seed = seed
        self.solo_mode = solo_mode
        self.language = language
        self.agent_state: Optional[Any] = None
        self.user_state: Optional[UserState] = None
        self.trajectory: list[Message] = []
        self.max_steps = max_steps
        self.max_errors = max_errors
        self.step_count = 0
        self.done = False
        self.termination_reason: Optional[TerminationReason] = None
        self.num_errors = 0
        self.from_role: Optional[Role] = None
        self.to_role: Optional[Role] = None
        self.message: Optional[Message] = None
        self.latest_user_msg: Optional[UserMessage] = None
        self.noise_category = noise_category
        self.index = 0
        # Ground truth for the deviation audit: the injector is the only place that
        # still knows the pre-injection payload, so record the pair as it happens.
        self.noise_injections: list[NoiseInjection] = []
        self.priority_level = priority_level
        self.noise_nums = noise_nums
        self.max_single_tool_noise = max_single_tool_noise
        tool_attributes = [attr for attr in dir(environment.tools) if not attr.startswith('_')]

        self.tools_dict = {tool: 0 for tool in tool_attributes}
        self.prompt_optimization_count = 0
        self.max_prompt_optimizations = 26
        self.pre_tool_call_state = {}

        self.complish = False
        # 为了优化
        self.current_sysprompt = zh_add_induce
        self.update_sysprompt = zh_add_induce
    def initialize(self):
        """
        Initialize the orchestrator.
        - If the tasks specifies an initial state, use it to initialize the environment.
        - Initialize the agent and user states.
        - Send the first message (default message from the agent to the user).
        """
        message_history = (
            deepcopy(self.task.message_history)
            if self.task is not None and self.task.message_history is not None
            else []
        )
        for msg in message_history:
            msg.turn_idx = None

        message_history = self._add_timestamps(message_history)

        if self.seed is not None:
            self.agent.set_seed(self.seed)
            self.user.set_seed(self.seed)

        if len(message_history) > 0:
            self.validate_message_history(message_history)

            last_message = message_history[-1]
            if isinstance(last_message, AssistantMessage):
                self.from_role = Role.AGENT
                if not last_message.is_tool_call():
                    self.to_role = Role.USER
                else:
                    self.to_role = Role.ENV
                self.agent_state = self.agent.get_init_state(
                    message_history=[
                        msg
                        for msg in message_history
                        if is_valid_agent_history_message(msg)
                    ]
                )
                self.user_state = self.user.get_init_state(
                    message_history=[
                        msg
                        for msg in message_history[:-1]
                        if is_valid_user_history_message(msg)
                    ]
                )
                self.message = last_message
                if self.agent.is_stop(last_message):
                    self.done = True
                    self.termination_reason = TerminationReason.AGENT_STOP
            elif isinstance(last_message, UserMessage):
                self.from_role = Role.USER
                if not last_message.is_tool_call():
                    self.to_role = Role.AGENT
                else:
                    self.to_role = Role.ENV
                self.user_state = self.user.get_init_state(
                    message_history=[
                        msg
                        for msg in message_history
                        if is_valid_user_history_message(msg)
                    ]
                )
                self.agent_state = self.agent.get_init_state(
                    message_history=[
                        msg
                        for msg in message_history[:-1]
                        if is_valid_agent_history_message(msg)
                    ]
                )
                self.message = last_message
                self.done = UserSimulator.is_stop(last_message)
                if self.done:
                    self.termination_reason = TerminationReason.USER_STOP
            elif isinstance(last_message, ToolMessage):
                self.from_role = Role.ENV
                if last_message.requestor == "assistant":
                    self.to_role = Role.AGENT
                    self.agent_state = self.agent.get_init_state(
                        message_history=[
                            msg
                            for msg in message_history[:-1]
                            if is_valid_agent_history_message(msg)
                        ]
                    )
                    self.user_state = self.user.get_init_state(
                        message_history=[
                            msg
                            for msg in message_history
                            if is_valid_user_history_message(msg)
                        ]
                    )
                else:
                    self.to_role = Role.USER
                    self.agent_state = self.agent.get_init_state(
                        message_history=[
                            msg
                            for msg in message_history
                            if is_valid_agent_history_message(msg)
                        ]
                    )
                    self.user_state = self.user.get_init_state(
                        message_history=[
                            msg
                            for msg in message_history[:-1]
                            if is_valid_user_history_message(msg)
                        ]
                    )
                self.message = last_message
            else:
                raise ValueError(
                    f"Last message should be of type AssistantMessage, UserMessage, or ToolMessage, got {type(last_message)}"
                )
            self.trajectory = message_history

        else:
            self.agent_state = self.agent.get_init_state()
            self.user_state = self.user.get_init_state()
            first_message = deepcopy(get_default_first_agent_message(self.language))
            first_message.timestamp = get_now()
            self.trajectory = [first_message]
            self.message = first_message
            self.from_role = Role.AGENT
            self.to_role = Role.USER

    def run(self) -> SimulationRun:
        """
        Run the simulation.

        Returns:
            SimulationRun: The simulation run.
        """
        start_time = get_now()
        start = time.perf_counter()
        self.initialize()
        while not self.done:
            self.step()
            if self.step_count >= self.max_steps:
                self.done = True
                self.termination_reason = TerminationReason.MAX_STEPS
            if self.num_errors >= self.max_errors:
                self.done = True
                self.termination_reason = TerminationReason.TOO_MANY_ERRORS
        duration = time.perf_counter() - start
        messages = self.get_trajectory()
        # turn_idx is only assigned once the trajectory is finalised, i.e. after the
        # injections were recorded, so backfill it here via the tool call id.
        turn_by_tool_id = {
            msg.id: msg.turn_idx for msg in messages if isinstance(msg, ToolMessage)
        }
        for injection in self.noise_injections:
            injection.turn_idx = turn_by_tool_id.get(injection.tool_id)
        res = get_cost(messages)
        if res is None:
            agent_cost, user_cost = None, None
        else:
            agent_cost, user_cost = res

        simulation_run = SimulationRun(
            id=str(uuid.uuid4()),
            task_id=self.task.id,
            start_time=start_time,
            end_time=get_now(),
            duration=duration,
            termination_reason=self.termination_reason.value,
            reward_info=None,
            user_cost=user_cost,
            agent_cost=agent_cost,
            messages=messages,
            seed=self.seed,
            states=self.get_states(self.environment.tools.db, self.environment.tools.db.time),
            noise_injections=self.noise_injections or None,
        )
        simulation_run.__dict__['_noise_index'] = self.index
        simulation_run.__dict__['_noise_category'] = self.noise_category
        return simulation_run

    def step(self):
        """
        Perform one step of the simulation.
        Sends self.message from self.from_role to self.to_role
        This can either be a message from agent to user/environment, environment to agent, or user to agent
        Updates self.trajectory
        """
        if self.done:
            raise ValueError("Simulation is done")
        check_deadline()
        logger.debug(
            f"Step {self.step_count}. Sending message from {self.from_role} to {self.to_role}"
        )
        logger.debug(
            f"Step {self.step_count}.\nFrom role: {self.from_role}\nTo role: {self.to_role}\n"
        )
        if self.from_role in [Role.AGENT, Role.ENV] and self.to_role == Role.USER:
            user_msg, self.user_state = self.user.generate_next_message(
                self.message, self.user_state
            )
            user_msg.validate()
            self.latest_user_msg = user_msg
            if UserSimulator.is_stop(user_msg):
                self.done = True
                self.termination_reason = TerminationReason.USER_STOP
            self.trajectory.append(user_msg)
            self.message = user_msg
            self.from_role = Role.USER
            if user_msg.is_tool_call():
                self.to_role = Role.ENV
            else:
                self.to_role = Role.AGENT
        elif (
            self.from_role == Role.USER or self.from_role == Role.ENV
        ) and self.to_role == Role.AGENT:
            # Retry up to 3 times if agent generates invalid message
            
            max_retries = 10
            retry_count = 0
            agent_msg = None
            original_agent_state = deepcopy(self.agent_state)  # Save original state
            
            while retry_count < max_retries:
                # Use a copy of the original state for each retry
                current_agent_state = deepcopy(original_agent_state)
                agent_msg, updated_agent_state = self.agent.generate_next_message(
                    self.message, current_agent_state
                )

                if agent_msg.has_text_content() or agent_msg.is_tool_call():
                    # Only update the actual agent state if we get a valid message
                    self.agent_state = updated_agent_state
                    break
                
                retry_count += 1
                logger.warning(f"Agent generated invalid message (attempt {retry_count}/{max_retries}): {agent_msg}")
            
            # If all retries failed, terminate with INVALID_AGENT_MESSAGE
            if retry_count >= max_retries:
                self.done = True
                self.termination_reason = TerminationReason.INVALID_AGENT_MESSAGE
                return
            
            agent_msg.validate()
            if self.agent.is_stop(agent_msg):
                self.done = True
                self.termination_reason = TerminationReason.AGENT_STOP
            self.trajectory.append(agent_msg)
            self.message = agent_msg
            self.from_role = Role.AGENT
            if agent_msg.is_tool_call():
                self.to_role = Role.ENV
            else:
                self.to_role = Role.USER
            
        elif self.from_role in [Role.AGENT, Role.USER] and self.to_role == Role.ENV:
            
            if not self.message.is_tool_call():
                raise ValueError("Agent or User should send tool call to environment")
            tool_msgs = []
            for i, tool_call in enumerate(self.message.tool_calls):

                tool_msg = self.environment.get_response(tool_call)

                if tool_call.name == 'repair_default':
                    pre_tool_call = tool_call.arguments['pre_tool_name']
                    self.tools_dict[pre_tool_call] = self.max_single_tool_noise + 1
                if_add_noise = False # 初始化
                if tool_call.name == 'repair_default' or (self.index < self.noise_nums and self.tools_dict.get(tool_call.name, 0) < self.max_single_tool_noise):

                    noise_category_sysprompt_dict = {
                        'wrong': {
                            'chinese': zh_add_wrong,    # 中文提示词
                            'english': en_add_wrong     # 英文提示词
                        },
                        'redundant': {
                            'chinese': zh_add_redundant,
                            'english': en_add_redundant
                        },
                        'induce': {
                            'chinese': zh_add_induce,
                            'english': en_add_induce
                        },
                        'incomplete': {
                            'chinese': zh_add_incomplete,
                            'english': en_add_incomplete
                        },
                        'fault': {
                            'chinese': '',
                            'english': ''
                        },
                        'others': {
                            'chinese': '',
                            'english': ''
                        }
                    }
                    print('tool_call.name:',tool_call.name)
                    noise_machine = tool_noise_bench(
                        messages=tool_msg.content, 
                        llm=Config_API.EVAL, 
                        API_key=Config_API.API_KEY,  # 替换为实际的API key
                        Base_url=Config_API.BASE_URL,  # 替换为实际的Base URL
                        sys_prompt=noise_category_sysprompt_dict[self.noise_category][self.language],
                        user_msg=self.latest_user_msg.content if self.latest_user_msg is not None else "",
                        Category=self.noise_category,  # 噪声类别
                        priority_level=self.priority_level,
                        nums=self.noise_nums,
                        environment=self.environment,
                        tool_call=tool_call,
                        instructions=self.task.instructions,
                        language=self.language,
                    )
                    original_tool_content = tool_msg.content
                    if_add_noise, noisy_tool_msg = noise_machine.Add_Noise()
                    tool_msg.content = noisy_tool_msg  # 替换为添加噪声后的内容
                    print('tool_msg:',tool_msg)
                    # 目前这里是就算调用多个也只出现一次错误
                    if if_add_noise:
                        self.tools_dict[tool_call.name] = self.tools_dict.get(tool_call.name, 0) + 1
                        self.index += 1
                        self.noise_injections.append(
                            NoiseInjection(
                                tool_id=tool_msg.id,
                                tool_name=tool_call.name,
                                category=self.noise_category,
                                turn_idx=tool_msg.turn_idx,
                                original=original_tool_content,
                                injected=noisy_tool_msg,
                            )
                        )
                tool_msgs.append(tool_msg)
            assert len(self.message.tool_calls) == len(tool_msgs), (
                "Number of tool calls and tool messages should be the same"
            )
            self.trajectory.extend(tool_msgs)
            if (
                len(tool_msgs) > 1
            ):
                self.message = MultiToolMessage(
                    role="tool",
                    tool_messages=tool_msgs,
                )
            else:
                self.message = tool_msgs[0]
            self.to_role = self.from_role
            self.from_role = Role.ENV
        else:
            raise ValueError(
                f"Invalid role combination. From role: {self.from_role}, To role: {self.to_role}"
            )
        self.step_count += 1

    def get_trajectory(self) -> list[Message]:
        """
        Get the trajectory of the simulation.
        The trajectory is sorted by timestamp, turn_idx are added to messages, trajectory is returned.
        """
        messages: list[Message] = sorted(
            deepcopy(self.trajectory),
            key=lambda x: x.timestamp,
        )
        trajectory = []
        for i, msg in enumerate(messages):
            msg = deepcopy(msg)
            msg.turn_idx = i
            trajectory.append(msg)
        return trajectory
    
    def get_states(self, db: DB, env_time: str) -> Dict[str, Any]:
        """
        Split the states into a dictionary.
        """
        from vita.utils import str_to_datetime

        states = []
        if hasattr(db, "orders"):
            states += list(db.orders.values())
        if hasattr(db, "books"):
            states += list(db.books.values())
        if hasattr(db, "reservations"):
            states += list(db.reservations.values())

        states_dict = {"old_states": [], "new_states": []}
        for state in states:
            if str_to_datetime(state.update_time) < str_to_datetime(env_time):
                states_dict["old_states"].append(state)
            else:
                states_dict["new_states"].append(state)
        return states_dict

    @classmethod
    def validate_message_history(cls, message_history: list[Message]):
        """
        Validate a message history.
            - Should only contain AssistantMessage, UserMessage, ToolMessage
            - All assistant/user messages should be either to user or tool call, not both.
            - If n tool calls are made by a participant, exactly n tool messages should follow with requestor matching the participant.
        """
        num_expected_tool_messages = 0
        requestor = None
        for msg in message_history:
            if isinstance(msg, AssistantMessage) or isinstance(msg, UserMessage):
                msg.validate()
                if msg.is_tool_call():
                    if num_expected_tool_messages > 0:
                        raise ValueError(
                            f"{num_expected_tool_messages} tool messages are missing. Got {msg.role} message."
                        )
                    num_expected_tool_messages = len(msg.tool_calls)
                    requestor = msg.role
                else:
                    num_expected_tool_messages == 0
                    requestor = None
            elif isinstance(msg, ToolMessage):
                if num_expected_tool_messages == 0 or requestor is None:
                    raise ValueError("No tool messages expected.")
                if requestor != msg.requestor:
                    raise ValueError(
                        f"Got tool message from {msg.requestor}, expected {requestor}."
                    )
                num_expected_tool_messages -= 1
            else:
                raise ValueError(f"Invalid message type: {type(msg)}")

    def _add_timestamps(
        self, message_history: list[Message]
    ) -> list[tuple[str, Message]]:
        """
        Add timestamps to the message history.
        This is used to sort the messages by timestamp.
        """
        time_offset = datetime.now() - timedelta(seconds=len(message_history))
        for i, msg in enumerate(message_history):
            msg.timestamp = format_time(time_offset + timedelta(seconds=i))
        return message_history
