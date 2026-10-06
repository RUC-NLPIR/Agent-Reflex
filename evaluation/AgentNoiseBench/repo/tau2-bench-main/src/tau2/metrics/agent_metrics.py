import math
import re

import pandas as pd
from loguru import logger
from pydantic import BaseModel

from tau2.data_model.simulation import Results


def is_successful(reward: float) -> bool:
    """
    Check if the reward is successful.
    """
    return (1 - 1e-6) <= reward <= (1 + 1e-6)

def extract_all_assistant_tokens(simulation_results):
    """提取所有AssistantMessage的输出token数，返回平均值"""
    
    all_simulations_data = []
    
    for simulation in simulation_results.simulations:
        simulation_tokens = 0
        simulation_messages = []
        
        for message in simulation.messages:
            if message.role == 'assistant':
                completion_tokens = 0
                
                if hasattr(message, 'usage') and message.usage:
                    usage = message.usage
                    if isinstance(usage, dict):
                        completion_tokens = usage.get('completion_tokens', 0)
                    elif isinstance(usage, list):
                        for u in usage:
                            completion_tokens += u.get('completion_tokens', 0)
                
                simulation_tokens += completion_tokens
                simulation_messages.append({
                    'turn_idx': message.turn_idx,
                    'has_tool_calls': hasattr(message, 'tool_calls') and message.tool_calls is not None,
                    'completion_tokens': completion_tokens
                })
        
        all_simulations_data.append({
            'simulation_id': simulation.id,
            'total_tokens': simulation_tokens,
            'message_count': len(simulation_messages),
            'messages': simulation_messages
        })
    
    # 计算平均值
    print('len(all_simulations_data):',len(all_simulations_data))
    if all_simulations_data:
        total_tokens_all = sum(sim['total_tokens'] for sim in all_simulations_data)
        total_messages_all = sum(sim['message_count'] for sim in all_simulations_data)
        avg_tokens_per_sim = total_tokens_all / len(all_simulations_data)
        avg_messages_per_sim = total_messages_all / len(all_simulations_data)
    else:
        avg_tokens_per_sim = 0
        avg_messages_per_sim = 0
    
    return {
        'average_tokens_per_simulation': avg_tokens_per_sim,
        'average_messages_per_simulation': avg_messages_per_sim,
        'total_simulations': len(all_simulations_data),
        'simulations_details': all_simulations_data,
        'summary': {
            'total_tokens_all_simulations': total_tokens_all,
            'total_messages_all_simulations': total_messages_all
        }
    }


class AgentMetrics(BaseModel):
    avg_reward: float
    pass_hat_ks: dict[int, float]
    avg_agent_cost: float
    avg_nl_success_rate: float
    avg_turn_idx: float
    avg_tokens: float
    avg_nl_success_rate_add: float

    def as_dict(self) -> dict:
        data = {
            "avg_reward": self.avg_reward,
            "avg_agent_cost": self.avg_agent_cost,
            "avg_nl_success_rate": self.avg_nl_success_rate,
        }
        for k, v in self.pass_hat_ks.items():
            data[f"pass_hat_{k}"] = v
        return data


def pass_hat_k(num_trials: int, success_count: int, k: int) -> float:
    """
    Compute the pass^k metric for the given number of trials, success count, and k.
    from https://arxiv.org/pdf/2406.12045
    Args:
        num_trials: The number of trials.
        success_count: The number of successful trials.
        k: The number of trials to consider.
    Returns:
        The pass^k metric.
    """
    if num_trials < k:
        raise ValueError(f"Number of trials {num_trials} is less than k {k}.")
    return math.comb(success_count, k) / math.comb(num_trials, k)


def get_metrics_df(results: Results) -> tuple[pd.DataFrame, int]:
    """
    Convert the results to a dataframe and add a column for success.
    Checks that all simulations have the same number of trials.
    Returns the maximum number of trials that can be used for pass^k metrics.
    """
    df = results.to_df()
    df["success"] = df.reward.apply(is_successful)
    if len(df.info_num_trials.unique()) > 1:
        logger.warning(
            f"All simulations must have the same number of trials. Found {df.info_num_trials.unique()}"
        )
    max_k = df.info_num_trials.max()

    task_ids_counts = [(tid, count) for tid, count in df.task_id.value_counts().items()]
    task_ids_counts.sort(key=lambda x: x[1])
    min_k = task_ids_counts[0][1]
    if min_k < max_k:
        logger.warning(
            f"The minimum number of trials for a task is {min_k}, which is less than the expected number of trials {max_k}. Setting max k to {min_k}."
        )
        max_k = min_k
    return df, max_k


def get_tasks_pass_hat_k(results: Results) -> pd.DataFrame:
    """
    Compute the pass^k for each k from 1 to the maximum number of trials.
    """
    df, max_k = get_metrics_df(results)
    dfs = []
    for k in range(1, max_k + 1):
        res = df.groupby("task_id")["success"].apply(
            lambda df: pass_hat_k(len(df), df.sum(), k)
        )
        res.name = f"pass^{k}"
        dfs.append(res)
    df_pass_hat_k = pd.concat(dfs, axis=1)
    task_columns = [
        "task_num_agent_actions",
        "task_num_user_actions",
        "task_num_actions",
    ]
    df_task_infos = df.groupby("task_id").first()[task_columns]
    df_pass_hat_k = df_task_infos.join(df_pass_hat_k)
    return df_pass_hat_k


def prepare_dfs(results: Results) -> tuple[pd.DataFrame, pd.DataFrame]:
    df, max_k = get_metrics_df(results)
    df_pass_hat_k = get_tasks_pass_hat_k(results)
    df_pass_hat_k["num_actions"] = df.groupby("task_id").first()["task_num_actions"]
    df_pass_hat_k = df_pass_hat_k.sort_values(by="num_actions")
    return df, df_pass_hat_k


def compute_metrics(results: Results) -> AgentMetrics:
    """
    Compute metrics for the agent.
    - average reward
    - pass^k
    """
    df, df_pass_hat_k = prepare_dfs(results)
    # print('results:',results)
    # print('df:',df)
    avg_reward = df.reward.mean()

    pass_hat_ks = {}
    for column in df_pass_hat_k.columns:
        if match := re.match(r"pass\^(\d+)", column):
            k = int(match.group(1))
            pass_hat_ks[k] = df_pass_hat_k[column].mean()
    avg_agent_cost = df.agent_cost.mean()
    # 计算turn_idx的平均值
    last_turn_idx = []
    for simulation in results.simulations:
        if simulation.messages:
            last_turn = simulation.messages[-1].turn_idx  # 获取最后一条消息的 turn_idx
            last_turn_idx.append(last_turn)
    # 计算平均值
    avg_turn_idx = sum(last_turn_idx) / len(last_turn_idx) if last_turn_idx else 0.0
    # 计算NL断言通过率
    nl_rewards = []
    nl_rewards_add = []
    print('simulation.reward_info.nl_assertions:',simulation.reward_info.nl_assertions)
    for simulation in results.simulations:
        if simulation.reward_info and simulation.reward_info.nl_assertions:
            nl_rubrics_count = len(simulation.reward_info.nl_assertions)
            # print('simulation.reward_info.nl_assertions:',simulation.reward_info.nl_assertions)
            nl_rewards.append(simulation.reward_info.average_nl_reward)
            nl_rewards_add.append((simulation.reward_info.average_nl_reward * nl_rubrics_count + 1)/(nl_rubrics_count + 1))
            # print(f"Simulation {simulation.id} - NL断言通过率: {nl_success_rate:.2f} ({passed_count}/{total_count})")
    
    # 计算所有模拟的平均NL断言通过率
    avg_nl_success_rate = sum(nl_rewards) / len(nl_rewards) if nl_rewards else 0.0
    avg_nl_success_rate_add = sum(nl_rewards_add) / len(nl_rewards_add) if nl_rewards else 0.0
    # print(f"平均NL断言通过率: {avg_nl_success_rate:.2f}")
    # 平均token
    completion_tokens = extract_all_assistant_tokens(results)
    return AgentMetrics(
        avg_reward=avg_reward,
        pass_hat_ks=pass_hat_ks,
        avg_agent_cost=avg_agent_cost,
        avg_nl_success_rate=avg_nl_success_rate,
        avg_nl_success_rate_add=avg_nl_success_rate_add,
        avg_turn_idx=avg_turn_idx,
        avg_tokens=completion_tokens['average_tokens_per_simulation']
    )


def display_metrics(metrics: AgentMetrics) -> None:
    print(f"🏆 Average reward: {metrics.avg_reward}")
    print("📈 Pass^k")
    for k, pass_hat_k in metrics.pass_hat_ks.items():
        print(f"  k={k}: {pass_hat_k}")
    print(f"💰 Average agent cost: {metrics.avg_agent_cost}")


if __name__ == "__main__":
    import argparse
    from pathlib import Path

    parser = argparse.ArgumentParser()
    parser.add_argument("--results", type=str, required=True)
    args = parser.parse_args()
    results = Results.load(Path(args.results))
    metrics = compute_metrics(results)
    display_metrics(metrics)
