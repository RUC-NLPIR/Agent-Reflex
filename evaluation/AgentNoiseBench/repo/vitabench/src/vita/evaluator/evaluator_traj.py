import json
import copy
from typing import List

from vita.config import Config_API, DEFAULT_LLM_EVALUATOR, models
from vita.data_model.message import UserMessage, SystemMessage, Message
from vita.evaluator.evaluator_base import EvaluatorBase
from vita.data_model.simulation import NLRubricCheck, NoiseInjection, RewardInfo
from vita.data_model.tasks import RewardType, Task, EvaluationCriteria
from vita.utils.llm_utils import generate
from vita.utils import evaluator_extracter, get_weekday
from vita.prompts import get_prompts
from vita.evaluator.deviation_audit import AUDITED_CATEGORIES, audit_trajectory

class TrajectoryEvaluator(EvaluatorBase):
    """
    Judge that evaluates whether a trajectory adheres to all the natural-language rubrics using sliding window approach.
    """

    @classmethod
    def calculate_reward(
        cls,
        task: Task,                      # 任务
        full_trajectory: List[Message],  # 完整的对话消息序列
        final_state: dict,               # 模拟结束时的最终状态
        window_size: int = 10,           # 每个评估窗口包含10条消息
        overlap: int = 2,                # 相邻窗口重叠2条消息，确保连续性
        llm_evaluator: str = None,       # 可选的大语言模型评估器名称
        llm_args_evaluator: dict = None, 
        language: str = None,            # 语言设置，用于时间格式本地化
        category: str = None,
        noise_injections: List[NoiseInjection] = None,  # 注入时留档的 ground truth
    ) -> RewardInfo:
        """
        Calculate the reward for the simulation by using sliding window evaluation on the full trajectory

        Args:
            task: The task containing evaluation criteria
            full_trajectory: Complete list of messages in the conversation
            final_state: Final state of the simulation
            window_size: Number of messages per window (default: 10)
            overlap: Number of messages to overlap between windows (default: 2)
        """
        # 如果没有评估标准，默认给予满分奖励（1.0），避免因配置缺失导致评估失败。
        if task.evaluation_criteria is None:
            return RewardInfo(
                reward=1.0,
                nl_rubrics=[],
                info={"note": "No evaluation criteria"},
                reward_breakdown={RewardType.NL_ASSERTION: 1.0},
            )
        # 检查评估标准是否包含具体的状态期望或整体规则，如果都为空，同样返回满分。
        evaluation_criteria = task.evaluation_criteria
        if not evaluation_criteria.expected_states and not evaluation_criteria.overall_rubrics:
            return RewardInfo(
                reward=1.0,
                nl_rubrics=[],
                info={"note": "No rubric to evaluate"},
                reward_breakdown={RewardType.NL_ASSERTION: 1.0},
            )
        # 提取任务环境信息，特别是系统时间
        env_info = {
            "system_time": "",
            "database": []
        }
        if hasattr(task, 'environment') and task.environment:
            time_str = task.environment.get("time", "")
            if time_str:
                weekday = get_weekday(time_str, language)
                env_info["system_time"] = f"{time_str} {weekday or ''}"
        # 初始化所有评估标准的状态跟踪器。每个标准都会有一个状态对象，用于记录在当前对话位置是否已被满足。
        # 这里应该对应的是显示的几个小点，看看是否满足
        current_rubric_states = cls._initialize_rubric_states(evaluation_criteria)
        # 将完整的对话轨迹分割成多个重叠的窗口
        windows = cls._create_sliding_windows(full_trajectory, window_size, overlap)
        # 计算窗口移动步长：例如：10-2=8
        step = window_size - overlap
        # 存储每个窗口的评估结果
        window_evaluations = [] 
        # 滑动窗口评估循环
        # current_rubric_states在窗口间传递，保持评估标准的连续性，更新状态，看看对应的标准有没有满足
        for i, window in enumerate(windows):
            print(f"Processing window {i+1}/{len(windows)} with {len(window)} messages")
            window_start_idx = i * step
            current_rubric_states, window_eval_info = cls._evaluate_window(
                env_info, task, window, current_rubric_states, i+1, len(windows), window_start_idx,
                llm_evaluator, llm_args_evaluator, language
            )
            window_evaluations.append(window_eval_info)
        # 二进制奖励​​：只有​​所有​​标准都满足时才给1.0分，否则0分
        # 细则分数​​：计算满足标准的比例（0.0到1.0之间）
        final_nl_rubric_checks = cls._convert_states_to_checks(current_rubric_states)
        all_expectations_met = all(result.met for result in final_nl_rubric_checks) and len(final_nl_rubric_checks) > 0
        rubric_score = sum(1.0 if result.met else 0.0 for result in final_nl_rubric_checks) / len(final_nl_rubric_checks)
        reward = 1.0 if all_expectations_met else 0.0

        # origin 档位（others）不注入噪声，用的是上面 sum/N 的分母；下面的 induce/redundant
        # 分支会把分母改成 N+1，于是两者不在同一把尺子上。所以在分支改写之前，先把与
        # origin 同尺的 I_task 和 rubric 比例留出来，供跨档位对比。
        task_success = 1.0 if all_expectations_met else 0.0
        task_rubric_score = rubric_score

        # 修正induce 和 redundant的分数
        # 判定基于注入时留档的 ground truth（simulation.noise_injections），逐条注入单独出
        # 判决：traj_ok 为 True 表示无一条把 agent 带偏，False 表示至少一条带偏，
        # None 表示裁判不可达 —— 三者必须区分，否则一次 API 抖动就白送或白扣一分。
        traj_ok, step_deviations = audit_trajectory(
            messages=full_trajectory,
            injections=noise_injections,
            category=category,
            user_goal=str(task.instructions) if task.instructions else "",
            api_key=Config_API.API_KEY,
            base_url=Config_API.BASE_URL,
            model=Config_API.MODEL,
        )

        # 折算方式与原先一致，只是分支挂到了正确的判决上：traj_ok=True 才是「未被带偏」。
        # 判决缺失（None）时两个公式都不套用，因为「无法确认干净」不等于「干净」。
        if category in AUDITED_CATEGORIES and traj_ok is True:
            reward = 1.0 if rubric_score>=1.0 else 0.0
            rubric_score = (sum(1.0 if result.met else 0.0 for result in final_nl_rubric_checks) + 1) / (len(final_nl_rubric_checks) + 1)
        elif category in AUDITED_CATEGORIES and traj_ok is False:
            reward = 0.0
            rubric_score = (sum(1.0 if result.met else 0.0 for result in final_nl_rubric_checks)) / (len(final_nl_rubric_checks) + 1)

        # SGA = I_traj * I_task，其中 I_task 取上面与 origin 同尺的那个，而不是被分支
        # 改写过的 reward —— 否则被诱导时 I_task 会被连带清零，SGA 就退化成只反映 I_traj。
        sga = None if traj_ok is None else task_success * (1.0 if traj_ok else 0.0)

        return RewardInfo(
            reward=reward,
            task_success=task_success,
            task_rubric_score=task_rubric_score,
            traj_ok=traj_ok,
            sga=sga,
            step_deviations=step_deviations or None,
            nl_rubrics=final_nl_rubric_checks,
            reward_breakdown={RewardType.NL_ASSERTION: rubric_score},
            info={"evaluation_method": "sliding_window", "num_windows": len(windows), "window_size": window_size},
            window_evaluations=window_evaluations
        )

    @classmethod
    def _initialize_rubric_states(cls, evaluation_criteria: EvaluationCriteria) -> dict:
        """
        Initialize rubric states - all start as False (not met)
        """
        rubric_states = {}
        rubric_idx = 0
        seen_rubrics = set()

        if evaluation_criteria.expected_states:
            for expected_state in evaluation_criteria.expected_states:
                if hasattr(expected_state, 'state_rubrics') and expected_state.state_rubrics:
                    for rubric in expected_state.state_rubrics:
                        if rubric in seen_rubrics:
                            continue
                        seen_rubrics.add(rubric)

                        key = f"rubric_{rubric_idx}"
                        rubric_states[key] = {
                            "rubric": rubric,
                            "justification": "Not evaluated yet",
                            "meetExpectation": False
                        }
                        rubric_idx += 1

        if evaluation_criteria.overall_rubrics:
            for rubric in evaluation_criteria.overall_rubrics:
                if rubric in seen_rubrics:
                    continue
                seen_rubrics.add(rubric)

                key = f"rubric_{rubric_idx}"
                rubric_states[key] = {
                    "rubric": rubric,
                    "justification": "Not evaluated yet",
                    "meetExpectation": False
                }
                rubric_idx += 1

        return rubric_states

    @classmethod
    def _create_sliding_windows(cls, messages: List[Message], window_size: int, overlap: int = 2) -> List[List[Message]]:
        """
        Create sliding windows from the message list with overlap

        Args:
            messages: List of messages to create windows from
            window_size: Size of each window
            overlap: Number of messages to overlap between windows
        """
        if len(messages) <= window_size:
            return [messages]

        windows = []
        step = window_size - overlap

        i = 0
        while i < len(messages):
            window = messages[i:i + window_size]
            if len(window) > 0:
                windows.append(window)

            if i + window_size >= len(messages):
                break

            i += step

        return windows

    @classmethod
    def _evaluate_window(
        cls,
        env_info: dict,
        task: Task,
        window: List[Message],
        current_states: dict,
        window_idx: int,
        total_windows: int,
        window_start_idx: int = 0,
        llm_evaluator: str = None,
        llm_args_evaluator: dict = None,
        language: str = None,
    ) -> tuple[dict, dict]:
        """
        Evaluate a single window and update rubric states
        
        Returns:
            tuple: (updated_states, window_evaluation_info)
        """
        if llm_evaluator is None:
            llm_evaluator = DEFAULT_LLM_EVALUATOR
        if llm_args_evaluator is None:
            llm_args_evaluator = models[DEFAULT_LLM_EVALUATOR]
            
        window_content = cls._format_window_content(window, window_start_idx)

        current_rubrics_str = cls._format_current_rubrics(current_states)

        prompts = get_prompts(language)
        system_prompt = prompts.sliding_window_eval_template.format(
            env_info=env_info,
            user_instruction=task.instructions,
            window_idx=window_idx,
            total_windows=total_windows
        )

        user_prompt = f"""
# Input
<window_content>
{window_content}
</window_content>

<current_rubrics>
{current_rubrics_str}
</current_rubrics>
"""

        messages = [
            SystemMessage(role="system", content=system_prompt),
            UserMessage(role="user", content=user_prompt),
        ]

        assistant_message = generate(
            model=llm_evaluator,
            messages=messages,
            **llm_args_evaluator,
        )

        window_evaluation_info = {
            "window_idx": window_idx,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "assistant_message_content": assistant_message.content,
            "assistent_message_usage": assistant_message.usage
        }

        updated_states = copy.deepcopy(current_states)
        result_data = evaluator_extracter(assistant_message.content)

        if result_data:
            for result in result_data:
                rubric_idx = result.get("rubric_idx")
                if rubric_idx and rubric_idx in updated_states:
                    updated_states[rubric_idx]["justification"] = result.get("justification", "No justification provided")
                    updated_states[rubric_idx]["meetExpectation"] = result.get("meetExpectation", updated_states[rubric_idx]["meetExpectation"])
        else:
            print(f"Warning: Failed to parse LLM response for window {window_idx}, keeping current states")

        return updated_states, window_evaluation_info

    @classmethod
    def _format_window_content(cls, window: List[Message], window_start_idx: int = 0) -> str:
        """
        Format window messages into a readable string with global message indices

        Args:
            window: List of messages in the current window
            window_start_idx: Global index of the first message in this window
        """
        content_lines = []
        for i, message in enumerate(window):
            role = getattr(message, 'role', 'unknown')
            content = getattr(message, 'content', '')

            full_content = content

            if role == 'assistant' and hasattr(message, 'tool_calls') and message.tool_calls:
                tool_calls_str = []
                for tool_call in message.tool_calls:
                    if hasattr(tool_call, 'name'):
                        tool_name = tool_call.name
                    elif isinstance(tool_call, dict):
                        tool_name = tool_call.get('name', 'unknown_tool')
                    else:
                        tool_name = 'unknown_tool'

                    if hasattr(tool_call, 'arguments'):
                        tool_args = tool_call.arguments
                    elif isinstance(tool_call, dict):
                        tool_args = tool_call.get('arguments', {})
                    else:
                        tool_args = {}

                    if isinstance(tool_args, dict):
                        args_str = ', '.join([f"{k}={repr(v)}" for k, v in tool_args.items()])
                    else:
                        args_str = str(tool_args)
                    tool_calls_str.append(f"{tool_name}({args_str})")

                if tool_calls_str:
                    if full_content:
                        full_content += " " + ".".join(tool_calls_str)
                    else:
                        full_content = ".".join(tool_calls_str)

            if full_content:
                global_idx = window_start_idx + i + 1
                content_lines.append(f"[{global_idx}] {role}: {full_content}")

        return "\n".join(content_lines)

    @classmethod
    def _format_current_rubrics(cls, current_states: dict) -> str:
        """
        Format current rubric states for LLM input
        """
        rubrics_list = []
        for key, state in current_states.items():
            rubrics_list.append({
                "rubric_idx": key,
                "rubric": state["rubric"],
                "justification": state["justification"],
                "meetExpectation": state["meetExpectation"]
            })

        return json.dumps(rubrics_list, ensure_ascii=False, indent=2)

    @classmethod
    def _convert_states_to_checks(cls, final_states: dict) -> List[NLRubricCheck]:
        """
        Convert final rubric states to NLRubricCheck objects
        """
        checks = []
        for key, state in final_states.items():
            check = NLRubricCheck(
                nl_rubric=state["rubric"],
                met=state["meetExpectation"],
                justification=state["justification"]
            )
            checks.append(check)

        return checks

    @classmethod
    def calculate_reward_full_traj_rubric(
            cls,
            task: Task,
            full_trajectory: List[Message],
            final_state: dict,
            llm_evaluator: str = None,
            llm_args_evaluator: dict = None,
            language: str = None,
    ) -> RewardInfo:
        if task.evaluation_criteria is None:
            return RewardInfo(
                reward=1.0,
                nl_rubrics=[],
                info={"note": "No evaluation criteria"},
                reward_breakdown={RewardType.NL_ASSERTION: 1.0},
            )

        evaluation_criteria = task.evaluation_criteria
        if not evaluation_criteria.expected_states and not evaluation_criteria.overall_rubrics:
            return RewardInfo(
                reward=1.0,
                nl_rubrics=[],
                info={"note": "No rubric to evaluate"},
                reward_breakdown={RewardType.NL_ASSERTION: 1.0},
            )

        env_info = {
            "system_time": "",
            "database": []
        }

        if hasattr(task, 'environment') and task.environment:
            time_str = task.environment.get("time", "")
            if time_str:
                weekday = get_weekday(time_str, language)
                env_info["system_time"] = f"{time_str} {weekday or ''}"

        current_rubric_states = cls._initialize_rubric_states(evaluation_criteria)

        current_rubric_states, trajectory_eval_info = cls._evaluate_trajectory(
            env_info, task, full_trajectory, current_rubric_states, llm_evaluator, llm_args_evaluator, language
        )

        final_nl_rubric_checks = cls._convert_states_to_checks(current_rubric_states)

        all_expectations_met = all(result.met for result in final_nl_rubric_checks) and len(final_nl_rubric_checks) > 0
        rubric_score = sum(1.0 if result.met else 0.0 for result in final_nl_rubric_checks) / len(
            final_nl_rubric_checks)
        reward = 1.0 if all_expectations_met else 0.0

        return RewardInfo(
            reward=reward,
            nl_rubrics=final_nl_rubric_checks,
            reward_breakdown={RewardType.NL_ASSERTION: rubric_score},
            info={"evaluation_method": "full_trajectory_with_rubrics"}
        )

    @classmethod
    def _evaluate_trajectory(
            cls,
            env_info: dict,
            task: Task,
            trajectory: List[Message],
            current_states: dict,
            llm_evaluator: str = None,
            llm_args_evaluator: dict = None,
            language: str = None,
    ) -> tuple[dict, dict]:
        if llm_evaluator is None:
            llm_evaluator = DEFAULT_LLM_EVALUATOR
        if llm_args_evaluator is None:
            llm_args_evaluator = models[DEFAULT_LLM_EVALUATOR]

        trajectory_content = cls._format_window_content(trajectory)

        current_rubrics_str = cls._format_current_rubrics(current_states)

        prompts = get_prompts(language)
        system_prompt = prompts.full_trajectory_eval_template.format(
            env_info=env_info,
            user_instruction=task.instructions
        )

        user_prompt = f"""
    # Input
    <trajectory_content>
    {trajectory_content}
    </trajectory_content>

    <current_rubrics>
    {current_rubrics_str}
    </current_rubrics>
    """

        messages = [
            SystemMessage(role="system", content=system_prompt),
            UserMessage(role="user", content=user_prompt),
        ]

        assistant_message = generate(
            model=llm_evaluator,
            messages=messages,
            **llm_args_evaluator,
        )

        trajectory_evaluation_info = {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "assistant_message_content": assistant_message.content
        }

        updated_states = copy.deepcopy(current_states)
        result_data = evaluator_extracter(assistant_message.content)

        if result_data:
            for result in result_data:
                rubric_idx = result.get("rubric_idx")
                if rubric_idx and rubric_idx in updated_states:
                    updated_states[rubric_idx]["justification"] = result.get("justification",
                                                                             "No justification provided")
                    updated_states[rubric_idx]["meetExpectation"] = result.get("meetExpectation",
                                                                               updated_states[rubric_idx][
                                                                                   "meetExpectation"])
        else:
            print(f"Warning: Failed to parse LLM response for total trajectory, keeping current states")

        return updated_states, trajectory_evaluation_info

    @classmethod
    def calculate_reward_sliding_wo_rubric(
            cls,
            task: Task,
            full_trajectory: List[Message],
            final_state: dict,
            window_size: int = 10,
            overlap: int = 2,
            llm_evaluator: str = None,
            llm_args_evaluator: dict = None,
            language: str = None,
    ) -> RewardInfo:
        if task.evaluation_criteria is None:
            return RewardInfo(
                reward=1.0,
                nl_rubrics=[],
                info={"note": "No evaluation criteria"},
                reward_breakdown={RewardType.NL_ASSERTION: 1.0},
            )

        evaluation_criteria = task.evaluation_criteria
        if not evaluation_criteria.expected_states and not evaluation_criteria.overall_rubrics:
            return RewardInfo(
                reward=1.0,
                nl_rubrics=[],
                info={"note": "No rubric to evaluate"},
                reward_breakdown={RewardType.NL_ASSERTION: 1.0},
            )

        env_info = {
            "system_time": "",
            "database": []
        }

        if hasattr(task, 'environment') and task.environment:
            time_str = task.environment.get("time", "")
            if time_str:
                weekday = get_weekday(time_str, language)
                env_info["system_time"] = f"{time_str} {weekday or ''}"

        windows = cls._create_sliding_windows(full_trajectory, window_size, overlap)
        current_evaluation = {
            "justification": "Not evaluated yet",
            "meetExpectation": False
        }

        step = window_size - overlap
        window_evaluations = [] 

        memory = ""
        for i, window in enumerate(windows):
            print(f"Processing window {i + 1}/{len(windows)} with {len(window)} messages")
            window_start_idx = i * step
            current_evaluation, window_eval_info, memory = cls._evaluate_window_sliding_wo_rubric(
                env_info, task, memory, current_evaluation, window, i + 1, len(windows), window_start_idx,
                llm_evaluator, llm_args_evaluator, language
            )
            window_evaluations.append(window_eval_info)

        final_nl_rubric_checks = cls._convert_states_to_checks_no_rubric(current_evaluation)

        all_expectations_met = final_nl_rubric_checks.met
        reward = 1.0 if all_expectations_met else 0.0

        return RewardInfo(
            reward=reward,
            nl_rubrics=[final_nl_rubric_checks],
            info={"evaluation_method": "sliding_window_no_rubrics", "num_windows": len(windows), "window_size": window_size},
            window_evaluations=window_evaluations
        )

    @classmethod
    def _evaluate_window_sliding_wo_rubric(
            cls,
            env_info: dict,
            task: Task,
            memory: str,
            current_evaluation,
            window: List[Message],
            window_idx: int,
            total_windows: int,
            window_start_idx: int = 0,
            llm_evaluator: str = None,
            llm_args_evaluator: dict = None,
            language: str = None,
    ) -> tuple[dict, dict]:
        """
        Evaluate a single window and update rubric states

        Returns:
            tuple: (updated_states, window_evaluation_info)
        """
        if llm_evaluator is None:
            llm_evaluator = DEFAULT_LLM_EVALUATOR
        if llm_args_evaluator is None:
            llm_args_evaluator = models[DEFAULT_LLM_EVALUATOR]

        window_content = cls._format_window_content(window, window_start_idx)

        current_evaluation_str = json.dumps(current_evaluation, ensure_ascii=False, indent=2)

        prompts = get_prompts(language)
        system_prompt = prompts.sliding_window_eval_no_rubrics_eval_template.format(
            env_info=env_info,
            user_instruction=task.instructions,
            window_idx=window_idx,
            total_windows=total_windows
        )

        user_prompt = f"""
# Input
<window_content>
{window_content}
</window_content>
<memory>
{memory}
</memory>
<current_evaluation>
{current_evaluation_str}
</current_evaluation>
"""

        messages = [
            SystemMessage(role="system", content=system_prompt),
            UserMessage(role="user", content=user_prompt),
        ]

        assistant_message = generate(
            model=llm_evaluator,
            messages=messages,
            **llm_args_evaluator,
        )

        window_evaluation_info = {
            "window_idx": window_idx,
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "assistant_message_content": assistant_message.content
        }

        updated_states = current_evaluation
        result_data = evaluator_extracter(assistant_message.content)

        memory = result_data.pop("memory")
        if result_data:
            updated_states = result_data
        else:
            print(f"Warning: Failed to parse LLM response for window {window_idx}")

        return updated_states, window_evaluation_info, memory

    @classmethod
    def _convert_states_to_checks_no_rubric(cls, final_states: dict) -> NLRubricCheck:
        check = NLRubricCheck(
            met=final_states["meetExpectation"],
            justification=final_states["justification"]
        )

        return check

    @classmethod
    def calculate_reward_full_traj_wo_rubric(
            cls,
            task: Task,
            full_trajectory: List[Message],
            final_state: dict,
            llm_evaluator: str = None,
            llm_args_evaluator: dict = None,
            language: str = None,
    ) -> RewardInfo:
        if task.evaluation_criteria is None:
            return RewardInfo(
                reward=1.0,
                nl_rubrics=[],
                info={"note": "No evaluation criteria"},
                reward_breakdown={RewardType.NL_ASSERTION: 1.0},
            )

        evaluation_criteria = task.evaluation_criteria
        if not evaluation_criteria.expected_states and not evaluation_criteria.overall_rubrics:
            return RewardInfo(
                reward=1.0,
                nl_rubrics=[],
                info={"note": "No rubric to evaluate"},
                reward_breakdown={RewardType.NL_ASSERTION: 1.0},
            )

        env_info = {
            "system_time": "",
            "database": []
        }

        if hasattr(task, 'environment') and task.environment:
            time_str = task.environment.get("time", "")
            if time_str:
                weekday = get_weekday(time_str, language)
                env_info["system_time"] = f"{time_str} {weekday or ''}"

        final_evaluation, trajectory_eval_info = cls._evaluate_trajectory_full_traj_wo_rubric(
            env_info, task, full_trajectory, llm_evaluator, llm_args_evaluator, language
        )

        final_nl_rubric_checks = cls._convert_states_to_checks_no_rubric(final_evaluation)

        all_expectations_met = final_nl_rubric_checks.met
        reward = 1.0 if all_expectations_met else 0.0

        return RewardInfo(
            reward=reward,
            nl_rubrics=[final_nl_rubric_checks],
            info={"evaluation_method": "full_trajectory_no_rubrics"}
        )

    @classmethod
    def _evaluate_trajectory_full_traj_wo_rubric(
            cls,
            env_info: dict,
            task: Task,
            trajectory: List[Message],
            llm_evaluator: str = None,
            llm_args_evaluator: dict = None,
            language: str = None,
    ) -> tuple[dict, dict]:
        if llm_evaluator is None:
            llm_evaluator = DEFAULT_LLM_EVALUATOR
        if llm_args_evaluator is None:
            llm_args_evaluator = models[DEFAULT_LLM_EVALUATOR]

        trajectory_content = cls._format_window_content(trajectory)

        prompts = get_prompts(language)
        system_prompt = prompts.full_trajectory_no_rubrics_eval_template.format(
            env_info=env_info,
            user_instruction=task.instructions
        )

        user_prompt = f"""
    # Input
    <trajectory_content>
    {trajectory_content}
    </trajectory_content>
    """

        messages = [
            SystemMessage(role="system", content=system_prompt),
            UserMessage(role="user", content=user_prompt),
        ]

        assistant_message = generate(
            model=llm_evaluator,
            messages=messages,
            **llm_args_evaluator,
        )

        trajectory_evaluation_info = {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
            "assistant_message_content": assistant_message.content
        }

        result_data = evaluator_extracter(assistant_message.content)

        if result_data and isinstance(result_data, dict):
            updated_states = result_data
        elif result_data and isinstance(result_data, list) and len(result_data) > 0:
            # If result_data is a list, take the first element
            updated_states = result_data[0]
        else:
            print(f"Warning: Failed to parse LLM response for total trajectory, keeping current states")
            updated_states = {
                "justification": "Not evaluated yet",
                "meetExpectation": False
            }

        return updated_states, trajectory_evaluation_info