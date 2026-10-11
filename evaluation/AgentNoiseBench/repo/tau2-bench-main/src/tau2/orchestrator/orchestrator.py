import time
import uuid
from copy import deepcopy
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional
from loguru import logger
from tau2.agent.base import BaseAgent, is_valid_agent_history_message
from tau2.agent.llm_agent import LLMSoloAgent
from tau2.config import Config_API, DEFAULT_MAX_RETRIES
from tau2.data_model.message import (
    AssistantMessage,
    Message,
    MultiToolMessage,
    ToolMessage,
    UserMessage,
)
from tau2.noise.system_prompt import en_add_wrong, en_add_redundant, en_add_induce_airline, en_add_induce_retail, en_add_induce_telecom, en_add_incomplete, en_add_redundant_primary, en_add_induce_primary
from tau2.noise.make_noisy import tool_noise_bench
# from tau2.noise.tools import delivery_tool, instore_tool, ota_tool
from tau2.data_model.simulation import NoiseInjection, SimulationRun, TerminationReason
from tau2.data_model.tasks import EnvFunctionCall, InitializationData, Task
from tau2.environment.environment import Environment, EnvironmentInfo
from tau2.user.base import BaseUser, is_valid_user_history_message
from tau2.user.user_simulator import DummyUser, UserSimulator, UserState
from tau2.utils.llm_utils import get_cost
from tau2.utils.task_deadline import check_deadline
from tau2.utils.utils import format_time, get_now

GREEN = '\033[32m'
RED = '\033[31m'
BLUE = '\033[94m'
RESET = '\033[0m'

class Role(str, Enum):
    AGENT = "agent"
    USER = "user"
    ENV = "env"


DEFAULT_FIRST_AGENT_MESSAGE = AssistantMessage(
    role="assistant", content="Hi! How can I help you today?", cost=0.0
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
        # 如何获取所有的tool的名称呢, 这里的tools应该是list的形式,里面的item都是
        self.tools=self.environment.get_tools()
        self.tool_names = [tool.name for tool in self.tools]
        self.tool_short_descs = [tool.short_desc for tool in self.tools]
        self.tool_long_descs = [tool.long_desc for tool in self.tools]
        self.tool_name_description = dict(zip(self.tool_names, self.tool_long_descs))
        # print('self.tools:',self.tool_names)
        self.tools_dict = {tool_name: 0 for tool_name in self.tool_names}
        self.prompt_optimization_count = 0
        self.max_prompt_optimizations = 66
        self.pre_tool_call_state = {}
        self.complish = False
        # 自动化迭代prompt
        # self.current_sysprompt = en_add_redundant_airline
        # self.update_sysprompt = en_add_redundant_airline
        # self.is_modifies = []
        # self.sum_sysyprompt = []
        # self.sum_agent_msg = []
        # with open(self.file_path, 'w', encoding='utf-8') as f:
        #     f.write("🔄 开始：\n")
        #     f.flush()         

    def initialize(self):
        """
        Initialize the orchestrator.
        - If the tasks specifies an initial state, use it to initialize the environment.
        - Initialize the agent and user states.
        - Send the first message (default message from the agent to the user).
        """
        initial_state = self.task.initial_state
        initialization_data = (
            initial_state.initialization_data if initial_state is not None else None
        )
        initialization_actions = (
            initial_state.initialization_actions if initial_state is not None else None
        )
        message_history = (
            deepcopy(initial_state.message_history)
            if initial_state is not None and initial_state.message_history is not None
            else []
        )
        for msg in message_history:
            msg.turn_idx = None

        # Add timestamps to the message history
        message_history = self._add_timestamps(message_history)

        if self.solo_mode:
            assert self.environment.solo_mode, "Environment should be in solo mode"
            assert isinstance(self.agent, LLMSoloAgent), (
                "Agent must be a LLMSoloAgent in solo mode"
            )
            assert isinstance(self.user, DummyUser), (
                "User must be a DummyUser in solo mode"
            )

        # Initialize Environment state
        self._initialize_environment(
            initialization_data=initialization_data,
            initialization_actions=initialization_actions,
            message_history=message_history,
        )

        # Set seeds for the agent, user
        if self.seed is not None:
            self.agent.set_seed(self.seed)
            self.user.set_seed(self.seed)

        # Initialize the agent and user states
        if len(message_history) > 0:
            self.validate_message_history(message_history)

            last_message = message_history[-1]
            # Last message is an assistant message
            if isinstance(last_message, AssistantMessage):
                self.from_role = Role.AGENT
                if not last_message.is_tool_call():  # Last message is for the user
                    self.to_role = Role.USER
                else:  # Last message is for the environment
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
            # Last message is a user message
            elif isinstance(last_message, UserMessage):
                self.from_role = Role.USER
                if not last_message.is_tool_call():  # Last message is for the agent
                    self.to_role = Role.AGENT
                else:  # Last message is for the environment
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
            # Last message is a tool message
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
            # 
            self.agent_state = self.agent.get_init_state()
            self.user_state = self.user.get_init_state()
            if not self.solo_mode:
                first_message = deepcopy(DEFAULT_FIRST_AGENT_MESSAGE)
                first_message.timestamp = get_now()
                self.trajectory = [first_message]
                self.message = first_message
                self.from_role = Role.AGENT
                self.to_role = Role.USER
            else:
                first_message, agent_state = self.agent.generate_next_message(
                    None, self.agent_state
                )
                self.trajectory = [first_message]
                self.message = first_message
                self.from_role = Role.AGENT
                self.to_role = Role.ENV
                self.done = self.agent.is_stop(first_message)
                if self.done:
                    self.termination_reason = TerminationReason.AGENT_STOP

        self.environment.sync_tools()

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
            noise_injections=self.noise_injections or None,
        )
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
            f"Step {self.step_count}. \nSending message from {self.from_role} to {self.to_role}"
        )
        print(f"{GREEN}Step {self.step_count}. Sending message from {self.from_role} to {self.to_role}{RESET}")
        logger.debug(
            f"Step {self.step_count}.\nFrom role: {self.from_role}\nTo role: {self.to_role}\n"
        )
        print(f"{RED}Step {self.step_count}.\nFrom role: {self.from_role}\nTo role: {self.to_role} {self.message}\n")
        # AGENT/ENV -> USER
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
        # USER/ENV -> AGENT
        elif (
            self.from_role == Role.USER or self.from_role == Role.ENV
        ) and self.to_role == Role.AGENT:
            max_retries = DEFAULT_MAX_RETRIES
            retry_count = 0
            agent_msg = None
            original_agent_state = deepcopy(self.agent_state)
            while retry_count < max_retries:
                current_agent_state = deepcopy(original_agent_state)
                try:
                    agent_msg, updated_agent_state = self.agent.generate_next_message(
                        self.message, current_agent_state
                    )
                except Exception as e:
                    retry_count += 1
                    logger.warning(
                        f"Agent generate_next_message failed (attempt {retry_count}/{max_retries}): {e}"
                    )
                    agent_msg = None
                    continue
                if agent_msg is not None and (agent_msg.has_text_content() or agent_msg.is_tool_call()):
                    self.agent_state = updated_agent_state
                    break
                retry_count += 1
                logger.warning(f"Agent generated invalid message (attempt {retry_count}/{max_retries}): {agent_msg}")
            valid = agent_msg is not None and (
                agent_msg.has_text_content() or agent_msg.is_tool_call()
            )
            if not valid:
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
        # AGENT/USER -> ENV
        elif self.from_role in [Role.AGENT, Role.USER] and self.to_role == Role.ENV:
            if not self.message.is_tool_call():
                raise ValueError("Agent or User should send tool call to environment")
            tool_msgs = []
            for tool_call in self.message.tool_calls:
                tool_msg = self.environment.get_response(tool_call)

                # if tool_call.name == 'repair_default':
                #     pre_tool_call = tool_call.arguments['pre_tool_name']
                #     self.tools_dict[pre_tool_call] = self.max_single_tool_noise + 1
                if tool_call.name == 'repair_default':
                    pre_tool_call = tool_call.arguments['pre_tool_name']
                    self.tools_dict[pre_tool_call] = self.max_single_tool_noise + 1
                if self.from_role == Role.AGENT:
                    if_add_noise = False # 初始化
                    if tool_call.name == 'repair_default' or (self.index < self.noise_nums and self.tools_dict.get(tool_call.name, 0) < self.max_single_tool_noise):
                        # 新建一个prompt对应的字典
                        print('tool_call.name:',tool_call.name)
                        noise_category_sysprompt_dict = {
                            'wrong':{'airline':en_add_wrong,'retail':en_add_wrong,'telecom':en_add_wrong}, 
                            'redundant':{'airline':en_add_redundant,'retail':en_add_redundant,'telecom':en_add_redundant}, 
                            'induce':{'airline':en_add_induce_airline,'retail':en_add_induce_retail,'telecom':en_add_induce_telecom}, 
                            'incomplete':{'airline':en_add_incomplete,'retail':en_add_incomplete,'telecom':en_add_incomplete}, 
                            'fault':{'airline':None,'retail':None,'telecom':None}, 
                            'others':{'airline':None,'retail':None,'telecom':None}}
                        # print(f"\n💾Results appended to CSV: {type(tool_call)}")
                        print('tool_msg_1:',tool_msg)
                        noise_machine = tool_noise_bench(
                            domain=self.domain,
                            messages=tool_msg.content, 
                            llm=Config_API.EVAL, 
                            API_key=Config_API.API_KEY,  # 替换为实际的API key
                            Base_url=Config_API.BASE_URL,  # 替换为实际的Base URL
                            sys_prompt=noise_category_sysprompt_dict[self.noise_category][self.domain],
                            user_msg=self.latest_user_msg.content if self.latest_user_msg is not None else "",
                            Category=self.noise_category,  # 噪声类别
                            priority_level=self.priority_level,
                            nums=self.noise_nums,
                            environment=self.environment,
                            tool_call=tool_call,
                            instructions=self.task.user_scenario,
                            tools_description=self.tool_name_description, 
                      
                        )
                        # print('noise_category_sysprompt_dict[self.noise_category][self.domain]:',noise_category_sysprompt_dict[self.noise_category][self.domain])
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
            # print(f"{BLUE}tool_msg: {tool_msgs}{RESET}")
            assert len(self.message.tool_calls) == len(tool_msgs), (
                "Number of tool calls and tool messages should be the same"
            )
            self.trajectory.extend(tool_msgs)
            if (
                len(tool_msgs) > 1
            ):  # Packaging multiple tool messages into a MultiToolMessage
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
        self.environment.sync_tools()

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

    def _initialize_environment(
        self,
        initialization_data: Optional[InitializationData],
        initialization_actions: Optional[list[EnvFunctionCall]],
        message_history: list[Message],
    ):
        """
        Initialize the environment.
        """
        # 初始化环境
        self.environment.set_state(
            initialization_data=initialization_data,
            initialization_actions=initialization_actions,
            message_history=message_history,
        )

    def _get_environment_info(self) -> EnvironmentInfo:
        """
        Get the environment info.
        """
        return self.environment.get_info()

    def _count_errors(self, message_history: list[Message]) -> int:
        """
        Count the number of errors in the message history.
        """
        return sum(
            1 for msg in message_history if isinstance(msg, ToolMessage) and msg.error
        )

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
