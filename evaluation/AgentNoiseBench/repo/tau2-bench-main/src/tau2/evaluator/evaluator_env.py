from typing import Callable

from loguru import logger

from tau2.data_model.message import AssistantMessage, Message, ToolCall, UserMessage
from tau2.data_model.simulation import DBCheck, EnvAssertionCheck, RewardInfo
from tau2.data_model.tasks import RewardType, Task
from tau2.environment.environment import Environment
from tau2.evaluator.evaluator_base import EvaluatorBase


# 它的核心思想是不关心智能体具体是如何一步步执行的，而只关注任务执行完毕后环境最终状态是否正确。
class EnvironmentEvaluator(EvaluatorBase):
    """
    Evaluator focuses on endstate of the simulation environment.
    """

    @classmethod
    def calculate_reward(
        cls,
        environment_constructor: Callable[[], Environment],
        task: Task,
        full_trajectory: list[
            Message
        ],  # FIXME: It would be better to be able to get only the messages that are after the initial state
        solo_mode: bool = False,
    ) -> RewardInfo:
        """
        Calculate the reward for the simulation.
        Args:
            environment_constructor: Callable[[], Environment]
            task: Task
            full_trajectory: list[Message] (Must include the message history from task initial state)
            solo_mode: bool
        Returns:
            RewardInfo
        """
        # 是否存在有效的评估标准。如果没有评估标准（evaluation_criteria为None），或者既没有预期动作（expected_actions）也没有环境断言（env_assertions），则直接返回满分奖励。
        if task.evaluation_criteria is None:
            return RewardInfo(
                reward=1.0,
                average_nl_reward=1.0,
                info={"note": "No evaluation criteria"},
            )
        # 
        expected_actions = task.evaluation_criteria.actions
        env_assertions = task.evaluation_criteria.env_assertions
        # # 检查是否有具体的评估内容
        if expected_actions is None and env_assertions is None:
            return RewardInfo(
                reward=1.0,
                average_nl_reward=1.0,
                db_check=DBCheck(db_match=True, db_reward=1.0),
                info={"note": "No expected actions or env assertions"},
            )
        # 这是该评估器的核心创新点：通过比较两个环境副本来评估智能体表现。
        initialization_data = None
        if (
            task.initial_state is not None
            and task.initial_state.initialization_data is not None
        ):
            initialization_data = task.initial_state.initialization_data

        initialization_actions = None
        if (
            task.initial_state is not None
            and task.initial_state.initialization_actions is not None
        ):
            initialization_actions = task.initial_state.initialization_actions

        message_history = []
        if (
            task.initial_state is not None
            and task.initial_state.message_history is not None
        ):


            message_history = task.initial_state.message_history
        # 预测环境重现了智能体的实际执行过程，通过载入完整的交互轨迹来模拟智能体的行为结果。
        predicted_environment = environment_constructor(solo_mode=solo_mode)
        # 评估的时候这种设置会导致错误，这里强调的是工具的调用必须要有对应的返回值，其实完全可以去掉
        # print('full_trajectory:',full_trajectory)
        predicted_environment.set_state(
            initialization_data=initialization_data,
            initialization_actions=initialization_actions,
            message_history=full_trajectory,
        )
        predicted_tool_calls: list[ToolCall] = []
        for message in full_trajectory:
            if (
                isinstance(message, AssistantMessage)
                or isinstance(message, UserMessage)
            ) and message.is_tool_call():
                predicted_tool_calls.extend(message.tool_calls)

        # Setting up gold environment.黄金环境执行任务定义中预设的理想动作序列，代表完成任务的最优路径。

        gold_environment = environment_constructor()
        gold_environment.set_state(
            initialization_data=initialization_data,
            initialization_actions=initialization_actions,
            message_history=message_history,
        )
        golden_actions = task.evaluation_criteria.actions or []
        for action in golden_actions:
            try:
                gold_environment.make_tool_call(
                    tool_name=action.name,
                    requestor=action.requestor,
                    **action.arguments,
                )
            except Exception as e:
                logger.warning(
                    f"Error in golden actions {action.name}({action.arguments}): {e}"
                )

        # Comparing the environments
        # 评估器通过多个维度来比较两个环境的差异：
        # 计算数据库哈希值进行比较
        agent_db_hash = gold_environment.get_db_hash()
        user_db_hash = gold_environment.get_user_db_hash()
        predicted_agent_db_hash = predicted_environment.get_db_hash()
        predicted_user_db_hash = predicted_environment.get_user_db_hash()
        agent_db_match = agent_db_hash == predicted_agent_db_hash
        user_db_match = user_db_hash == predicted_user_db_hash
        #  完全匹配得满分
        if agent_db_match and user_db_match:
            db_reward = 1.0
            db_match = True
        else:
            db_reward = 0.0
            db_match = False

        db_check = DBCheck(db_match=db_match, db_reward=db_reward)

        # Run env assertions,环境断言验证
        # 定义了如何通过检查环境状态来评估一个智能体（如LLM Agent）是否成功完成了任务
        env_assertions = task.evaluation_criteria.env_assertions or [] # 准则不为空
        env_assertion_checks = [] # 初始化
        env_assertion_reward = 1.0 # 初始化
        for env_assertion in env_assertions: 
            # 关键是这个
            success = predicted_environment.run_env_assertion(
                env_assertion,
                raise_assertion_error=False,
            )
            res = EnvAssertionCheck(
                env_assertion=env_assertion,
                met=success,
                reward=1.0 if success else 0.0,
            )
            env_assertion_checks.append(res)
            env_assertion_reward *= res.reward

        reward = 1.0
        reward_breakdown = {}
        if RewardType.DB in task.evaluation_criteria.reward_basis:
            reward_breakdown[RewardType.DB] = db_reward
            reward *= db_reward
        if RewardType.ENV_ASSERTION in task.evaluation_criteria.reward_basis:
            reward_breakdown[RewardType.ENV_ASSERTION] = env_assertion_reward
            reward *= env_assertion_reward

        return RewardInfo(
            reward=reward,
            average_nl_reward=reward,
            db_check=db_check,
            env_assertions=env_assertion_checks,
            reward_basis=task.evaluation_criteria.reward_basis,
            reward_breakdown=reward_breakdown,
        )
