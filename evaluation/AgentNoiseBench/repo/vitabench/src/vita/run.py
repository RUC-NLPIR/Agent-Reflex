# temperature设置为0
# 评估部分：success表示运行过程中是否出现过错误，一般是编程上的错误
# 
import json
import multiprocessing
import os
import random
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional
from datetime import datetime

from loguru import logger

from vita.agent.llm_agent import LLMAgent, LLMSoloAgent
from vita.data_model.simulation import (
    AgentInfo,
    Info,
    Results,
    RewardInfo,
    RunConfig,
    SimulationRun,
    TerminationReason,
    UserInfo,
)

from vita.config import DEFAULT_MAX_RETRIES, models
from vita.data_model.tasks import Task
from vita.data_model.simulation import EvaluationType
from vita.environment.environment import get_cross_environment, EnvironmentInfo
from vita.evaluator.evaluator import evaluate_simulation
from vita.metrics.agent_metrics import compute_metrics
from vita.orchestrator.orchestrator import Orchestrator
from vita.registry import RegistryInfo, registry
from vita.user.user_simulator import get_global_user_sim_guidelines
from vita.utils.display import ConsoleDisplay
from vita.utils.pydantic_utils import get_pydantic_hash
from vita.utils.utils import DATA_DIR, get_commit_hash, get_now, show_dict_diff, global_time
from vita.utils.csv_utils import save_results_to_csv
from vita.utils.task_deadline import (
    TaskTimeout,
    elapsed_seconds,
    start_task_deadline,
    task_timeout_seconds,
)
import uuid


def confirm_resume(prompt: str) -> str:
    if os.environ.get("VITA_AUTO_RESUME", "1") == "1" or not sys.stdin.isatty():
        ConsoleDisplay.console.print(f"{prompt} [auto-yes]")
        return "y"
    return ConsoleDisplay.console.input(prompt).lower().strip()


def get_options() -> RegistryInfo:
    """
    Returns options for the simulator.
    """
    return registry.get_info()


def get_environment_info(
    domain_name: str, include_tool_info: bool = False
) -> EnvironmentInfo:
    """Get information about the environment for a registered Domain"""
    return EnvironmentInfo(
            domain_name=domain_name,
            tool_defs=None
        )


def load_tasks(task_set_name: str, language: str = None) -> list[Task]:
    """
    Loads the tasks for the given domain.
    """
    global registry
    if ',' in task_set_name:
        task_loader = registry.get_tasks_loader("cross_domain")
    else:
        task_loader = registry.get_tasks_loader(task_set_name)
    tasks = task_loader(language)
    return tasks


def get_tasks(
    task_set_name: str,
    task_ids: Optional[list[str]] = None,
    num_tasks: Optional[int] = None,
    language: str = None,
) -> list[Task]:
    """
    Loads the tasks for the given domain.
    """
    if task_ids is None and num_tasks is None:
        return load_tasks(task_set_name=task_set_name, language=language)
    tasks = []
    if task_ids is not None:
        tasks = [
            task for task in load_tasks(task_set_name=task_set_name, language=language) if task.id in task_ids
        ]
        if len(tasks) != len(task_ids):
            missing_tasks = set(task_ids) - set([task.id for task in tasks])
            raise ValueError(
                f"Not all tasks were found for task set {task_set_name}: {missing_tasks}"
            )
    if num_tasks is not None:
        tasks = load_tasks(task_set_name=task_set_name, language=language)[:num_tasks]
    return tasks


def make_run_name(config: RunConfig) -> str:
    """
    Make a run name from the run config
    """
    clean_llm_agent_name = config.llm_agent.split("/")[-1]
    agent_name = f"{config.agent}_{clean_llm_agent_name}"

    clean_llm_user_name = config.llm_user.split("/")[-1]
    user_name = f"{config.user}_{clean_llm_user_name}"

    # Add think mode indicator to the filename if enable_think is True
    think_suffix = "_think" if config.enable_think else ""
    
    return f"{get_now()}_{config.domain}_{agent_name}_{user_name}{think_suffix}"


def run_domain(config: RunConfig) -> Results:
    """
    Run simulations for a domain
    Returns:
        Results: The simulation results
    """
    config.validate()
    ConsoleDisplay.display_run_config(config)
    # Check if this is a re-evaluation mode with optional re-run
    if hasattr(config, 're_evaluate_file') and config.re_evaluate_file:
        results = re_evaluate_simulation(config)
        return results
    
    if config.task_set_name is None:
        task_set_name = config.domain
    else:
        task_set_name = config.task_set_name
    tasks = get_tasks(task_set_name, config.task_ids, config.num_tasks, config.language)
    # ConsoleDisplay.console.print(f"\n💾 [bold red]tasks: {tasks}[/bold red]") # 这里的task就是根据终端输入的命令提取的task集合，如果输入的是一个id的话，那么一个task
    # ConsoleDisplay.console.print(f"\n💾 [bold green]tasks: {type(tasks)}[/bold green]") # list类型
    num_trials = config.num_trials
    save_to = config.save_to
    if save_to is None:
        save_to = f"{make_run_name(config)}.json"
    save_to = DATA_DIR / "simulations" / save_to
    config.save_to = save_to
    print('config.llm_args_agent:',config.llm_args_agent)
    # Run simulations with the specified evaluation type
    # print('config.evaluation_type:',config.evaluation_type)
    simulation_results = run_tasks(
        domain=config.domain,
        tasks=tasks,
        agent=config.agent,
        user=config.user,
        llm_agent=config.llm_agent,
        llm_args_agent=config.llm_args_agent,
        llm_user=config.llm_user,
        llm_args_user=config.llm_args_user,
        num_trials=num_trials,
        max_steps=config.max_steps,
        max_errors=config.max_errors,
        save_to=save_to,
        console_display=True,
        evaluation_type=config.evaluation_type,
        max_concurrency=config.max_concurrency,
        seed=config.seed,
        log_level=config.log_level,
        enable_think=config.enable_think,
        llm_evaluator=config.llm_evaluator,
        llm_args_evaluator=config.llm_args_evaluator,
        language=config.language,
        noise_category=config.noise_category,  # 新增参数
        priority_level=config.priority_level,
        noise_nums=config.noise_nums, # 新增参数
        max_single_tool_noise=config.max_single_tool_noise,
        user_noise=config.user_noise,
    )
    print('###\n')
    metrics = compute_metrics(simulation_results)
    print('\n###\n')
    ConsoleDisplay.display_agent_metrics(metrics, config.noise_category)
    # 结果导出
    if config.csv_output_file and simulation_results.simulations:
        try:
            csv_output = config.csv_output_file
            save_results_to_csv(simulation_results, csv_output, config, metrics)
            ConsoleDisplay.console.print(f"\n💾 [bold green]Results appended to CSV: {csv_output}[/bold green]")
        except Exception as e:
            ConsoleDisplay.console.print(f"\n[bold red]Error saving to CSV: {e}[/bold red]")

    return simulation_results


def run_tasks(

    domain: str,
    tasks: list[Task],
    agent: str,
    user: str,
    llm_agent: Optional[str] = None,
    llm_args_agent: Optional[dict] = None,
    llm_user: Optional[str] = None,
    llm_args_user: Optional[dict] = None,
    num_trials: int = 1,
    max_steps: int = 100,
    max_errors: int = 10,
    save_to: Optional[str | Path] = None,
    console_display: bool = True,
    evaluation_type: EvaluationType = "trajectory",
    max_concurrency: int = 1,
    seed: Optional[int] = 300,
    log_level: Optional[str] = "INFO",
    enable_think: bool = False,
    llm_evaluator: Optional[str] = None,
    llm_args_evaluator: Optional[dict] = None,
    language: str = None,
    noise_category: str = None,  # 新增参数
    priority_level: int = 1,    
    noise_nums: int = 1,  # 新增参数
    max_single_tool_noise: int = 2,
    user_noise: str=None,

) -> Results:
    """
    Runs tasks for a given domain.
    If llm_as_judge is True, the LLM will be used to annotate the simulation run.
    Calculates the reward for the simulation run.
    Args:
        domain (str): The domain to run the simulation on.
        tasks (list[Task]): The tasks to run.
        agent (str): The agent to run the simulation on.
        user (str): The user to run the simulation on.
        llm_agent (str): The model to use for the agent.
        llm_args_agent (dict): The arguments to pass to the LLM for the agent.
        llm_user (str): The model to use for the user.
        llm_args_user (dict): The arguments to pass to the LLM for the user.
        num_trials (int): The number of trials to run the simulation on.
        max_steps (int): The maximum number of steps to run the simulation.
        max_errors (int): The maximum number of errors to allow in the simulation.
        save_to (str | Path): The path to json file where to save the simulation results. If the file already exists, it will try to resume the run.
        console_display (bool): Whether to display the simulation results in the console.
        evaluation_type (EvaluationType): The type of evaluation to use.
        max_concurrency (int): The maximum number of concurrent simulations to run.
        seed (int): The seed to use for the simulation.
        log_level (str): The log level to use.
        enable_think (bool): Whether to enable think mode for the agent LLM.
    Returns:
        The simulation results and the annotations (if llm_review is True).
    """
    if isinstance(save_to, str):
        save_to = Path(save_to)
    # Set log level from config
    logger.remove()
    logger.add(lambda msg: print(msg), level=log_level)
    if len(tasks) == 0:
        raise ValueError("No tasks to run")
    if num_trials <= 0:
        raise ValueError("Number of trials must be greater than 0")
    if max_steps <= 0:
        raise ValueError("Max steps must be greater than 0")
    if max_errors <= 0:
        raise ValueError("Max errors must be greater than 0")

    random.seed(seed)

    seeds = [random.randint(0, 1000000) for _ in range(num_trials)]
    if "seed" in llm_args_agent:
        logger.warning("Each trial will modify the seed for the agent")

    if "seed" in llm_args_user:
        logger.warning("Each trial will modify the seed for the user")

    lock = threading.Lock()

    info = get_info(
        domain=domain,
        agent=agent,
        user=user,
        llm_agent=llm_agent,
        llm_args_agent=llm_args_agent,
        llm_user=llm_user,
        llm_args_user=llm_args_user,
        num_trials=num_trials,
        max_steps=max_steps,
        max_errors=max_errors,
        seed=seed,
        language=language,
        user_noise=user_noise,
    )
    simulation_results = Results( # 应该是属于结果的初始化
        info=info,
        tasks=tasks,
        simulations=[],
    )
    done_runs = set()
    if save_to is not None:
        # If save_to already exists, check if the user wants to resume the run.
        if save_to.exists():
            response = confirm_resume(
                "[yellow]File [bold]{}[/bold] already exists. Do you want to resume the run? (y/n)[/yellow] ".format(
                    save_to
                )
            )
            if response != "y":
                raise FileExistsError(
                    f"File {save_to} already exists. Please delete it or use a different save_to name."
                )
            with open(save_to, "r") as fp:
                prev_simulation_results = Results.model_validate_json(fp.read())
                # Check if the run config has changed
                if get_pydantic_hash(prev_simulation_results.info) != get_pydantic_hash(
                    simulation_results.info
                ):
                    diff = show_dict_diff(
                        prev_simulation_results.info.model_dump(),
                        simulation_results.info.model_dump(),
                    )
                    ConsoleDisplay.console.print(
                        f"The run config has changed.\n\n{diff}\n\nDo you want to resume the run? (y/n)"
                    )
                    response = confirm_resume(
                        "[yellow]File [bold]{}[/bold] already exists. Do you want to resume the run? (y/n)[/yellow] ".format(
                            save_to
                        )
                    )
                    if response != "y":
                        raise ValueError(
                            "The run config has changed. Please delete the existing file or use a different save_to name."
                        )
                # Check if the task set has changed
                if not all(
                    get_pydantic_hash(task) == get_pydantic_hash(prev_task)
                    for task, prev_task in zip(
                        sorted(simulation_results.tasks, key=lambda x: x.id),
                        sorted(prev_simulation_results.tasks, key=lambda x: x.id),
                    )
                ):
                    raise ValueError(
                        "The task set has changed. Please delete the existing file or use a different save_to name."
                    )
                # Check which of the runs have already been done
                done_runs = set(
                    [
                        (sim.trial, sim.task_id, sim.seed)
                        for sim in prev_simulation_results.simulations
                    ]
                )
                simulation_results = prev_simulation_results
                ConsoleDisplay.console.print(
                    f"[bold yellow]Resuming run from {len(done_runs)} runs. {len(tasks) * num_trials - len(done_runs)} runs remaining.[/bold yellow]"
                )
        # Create new save file
        else:
            # Check if save_to exists and create parent directories if needed
            if not save_to.parent.exists():
                save_to.parent.mkdir(parents=True, exist_ok=True)
            logger.info(f"Saving simulation batch to {save_to}")
            with open(save_to, "w") as fp:
                fp.write(simulation_results.model_dump_json(indent=2))

    def _save(simulation: SimulationRun):
        def serialize_datetime(obj):
            if isinstance(obj, datetime):
                return obj.isoformat()
            raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
        if save_to is None:
            return
        with lock:
            with open(save_to, "r") as fp:
                ckpt = json.load(fp)
            
            simulation_dict = simulation.model_dump()
            
            ckpt["simulations"].append(simulation_dict)
            with open(save_to, "w", encoding="utf-8") as fp:
                json.dump(ckpt, fp, indent=2, ensure_ascii=False, default=serialize_datetime)

    def _zero_sim(task: Task, trial: int, seed: int, started: str) -> SimulationRun:
        return SimulationRun(
            id=str(uuid.uuid4()),
            task_id=task.id,
            start_time=started,
            end_time=get_now(),
            duration=elapsed_seconds(),
            termination_reason=TerminationReason.TASK_TIMEOUT,
            messages=[],
            trial=trial,
            seed=seed,
            reward_info=RewardInfo(reward=0.0),
        )

    def _run(task: Task, trial: int, seed: int, progress_str: str) -> dict:
        ConsoleDisplay.console.print(
            f"[bold green]{progress_str} Running task {task.id}, trial {trial + 1}[/bold green]"
        )
        started = get_now()
        start_task_deadline()
        try:
            simulation = run_task(
                domain=domain,
                task=task,
                agent=agent,
                user=user,
                llm_agent=llm_agent,
                llm_args_agent=llm_args_agent,
                llm_user=llm_user,
                llm_args_user=llm_args_user,
                max_steps=max_steps,
                max_errors=max_errors,
                evaluation_type=evaluation_type,
                seed=seed,
                max_retries=int(os.environ.get("TASK_MAX_RETRIES", "2")),
                enable_think=enable_think,
                llm_evaluator=llm_evaluator,
                llm_args_evaluator=llm_args_evaluator,
                language=language,
                noise_category=noise_category,  # 新增参数
                priority_level=priority_level,
                noise_nums=noise_nums,  # 新增参数
                max_single_tool_noise=max_single_tool_noise,
                user_noise=user_noise,
            )
            simulation.trial = trial
            if console_display:
                ConsoleDisplay.display_simulation(simulation, show_details=False)
            _save(simulation)
            return {"status": "success", "simulation": simulation}
        except TaskTimeout as e:
            logger.warning(
                f"Task {task.id}, trial {trial} timed out after {task_timeout_seconds():.0f}s; counting as incorrect"
            )
            simulation = _zero_sim(task, trial, seed, started)
            _save(simulation)
            if console_display:
                ConsoleDisplay.console.print(
                    f"[bold yellow]Task {task.id}, trial {trial} timed out ({e}); scored 0[/bold yellow]"
                )
            return {"status": "success", "simulation": simulation}
        except Exception as e:
            logger.error(f"Error running task {task.id}, trial {trial}: {e}")
            logger.warning(f"Task {task.id}, trial {trial} failed but continuing with other tasks")
            if console_display:
                ConsoleDisplay.console.print(f"[bold red]Task {task.id}, trial {trial} failed: {e}[/bold red]")
            return {"status": "failed", "task_id": task.id, "trial": trial, "error": str(e)}

    args = []
    for i, task in enumerate(tasks):
        # ConsoleDisplay.console.print(f"\n💾 [bold red]**task**: {task}[/bold red]")
        # ConsoleDisplay.console.print(f"\n💾 [bold green]**task_length**: {len(tasks)}[/bold green]")
        for trial in range(num_trials):
            if (trial, task.id, seeds[trial]) in done_runs:
                ConsoleDisplay.console.print(
                    f"[bold yellow]Skipping task {task.id}, trial {trial} because it has already been run.[/bold yellow]"
                )
                continue
            progress_str = f"{i}/{len(tasks)} (trial {trial + 1}/{num_trials})"
            args.append((task, trial, seeds[trial], progress_str))
    # 并行运行任务
    with ThreadPoolExecutor(max_workers=max_concurrency) as executor:
        if not args:
            res = []
        else:
            res = list(executor.map(_run, *zip(*args)))
        # Separate successful and failed tasks
        successful_sims = []
        failed_sims = []
        # for sim_result in res:
        #     # print('sim_result:',sim_result)
        #     simulation = sim_result["simulation"]
        #     noise_index = simulation.__dict__.get('_noise_index', 0)
        #     noise_category = simulation.__dict__.get('_noise_category', 0)
        #     # print('###########################noise:',noise_index)
        #     # 加噪情况下 and 不加噪情况下
        #     if (sim_result["status"] == "success" and noise_index>=1 and noise_category != 'others') or (sim_result["status"] == "success" and noise_index<1 and noise_category == 'others') or user_noise!='original':
        #         successful_sims.append(sim_result["simulation"])
        #     else:
        #         failed_sims.append(sim_result)
        for sim_result in res:
            if sim_result["status"] == "success":
                successful_sims.append(sim_result["simulation"])
            else:
                failed_sims.append(sim_result)
        
        # Only add successful tasks to results
        simulation_results.simulations.extend(successful_sims)

    # Count successful and failed tasks
    ConsoleDisplay.console.print(
        f"\n✨ [bold green]Successfully completed all simulations![/bold green]\n"
        f"📊 [bold blue]Statistics:[/bold blue]\n"
        f"  ✅ Successful tasks: {len(successful_sims)}\n"
        f"  ❌ Failed tasks: {len(failed_sims)}\n"
        f"  📝 Total tasks: {len(res)}\n"
        f"To review the simulations, run: [bold blue]vita view[/bold blue]"
    )
    
    if failed_sims:
        ConsoleDisplay.console.print(f"\n[bold red]Failed tasks:[/bold red]")
        for failed_result in failed_sims:
            task_id = failed_result.get('task_id', 'Unknown')
            trial = failed_result.get('trial', 'Unknown')
            error = failed_result.get('error', 'No error message')
            noise_index = failed_result.get('noise_index', failed_result.get('_noise_index', 'N/A'))
            # A failed entry only carries task_id/trial/error (see the except above);
            # it has no 'simulation', because a task that raised never produced one.
            # Reading that key here turned every task failure into KeyError, which
            # killed the run and hid the actual error this line is meant to report.
            ConsoleDisplay.console.print(f"  - Task {task_id}, Trial {trial} (noise {noise_index}): {error}")
        
        # Display all failed task IDs
        failed_task_ids = sorted({str(failed_result.get('task_id', 'Unknown')) for failed_result in failed_sims})
        ConsoleDisplay.console.print(f"\n[bold red]Failed task IDs:[/bold red] {', '.join(failed_task_ids)}")
    
    return simulation_results


def run_task(
    domain: str,
    task: Task,
    agent: str,
    user: str,
    llm_agent: Optional[str] = None,
    llm_args_agent: Optional[dict] = None,
    llm_user: Optional[str] = None,
    llm_args_user: Optional[dict] = None,
    max_steps: int = 100,
    max_errors: int = 10,
    evaluation_type: EvaluationType = "trajectory",
    seed: Optional[int] = None,
    max_retries: int = DEFAULT_MAX_RETRIES,
    enable_think: bool = False,
    llm_evaluator: Optional[str] = None,
    llm_args_evaluator: Optional[dict] = None,
    language: str = None,
    noise_category: str = None,  # 新增参数
    priority_level: int = 1,
    noise_nums: int = 1,  # 新增参数
    max_single_tool_noise: int = 2,
    user_noise: str=None,
) -> SimulationRun:
    """
    Runs tasks for a given domain.
     If llm_as_judge is True, the LLM will be used to annotate the simulation run.
     Calculates the reward for the simulation run.
     Args:
         domain (str): The domain to run the simulation on.
         task (Task): The task to run.
         agent (str): The agent to run the simulation on.
         user (str): The user to run the simulation on.
         llm_agent (str): The model to use for the agent.
         llm_args_agent (dict): The arguments to pass to the LLM for the agent.
         llm_user (str): The model to use for the user.
         llm_args_user (dict): The arguments to pass to the LLM for the user.
         max_steps (int): The maximum number of steps to run the simulation.
         max_errors (int): The maximum number of errors to allow in the simulation.
         evaluation_type (EvaluationType): The type of evaluation to use.
         seed (int): The seed to use for the simulation.
         max_retries (int): The maximum number of retries if an error occurs.
     Returns:
         The simulation run.
    """

    if max_steps <= 0:
        raise ValueError("Max steps must be greater than 0")
    if max_errors <= 0:
        raise ValueError("Max errors must be greater than 0")

    for attempt in range(max_retries + 1):  # +1 because the first attempt is not counted as a retry
        try:
            return _run_task_internal(
                domain=domain,
                task=task,
                agent=agent,
                user=user,
                llm_agent=llm_agent,
                llm_args_agent=llm_args_agent,
                llm_user=llm_user,
                llm_args_user=llm_args_user,
                max_steps=max_steps,
                max_errors=max_errors,
                evaluation_type=evaluation_type,
                seed=seed,
                enable_think=enable_think,
                llm_evaluator=llm_evaluator,
                llm_args_evaluator=llm_args_evaluator,
                language=language,
                noise_category=noise_category,
                priority_level=priority_level,
                noise_nums=noise_nums,  # 新增参数  
                max_single_tool_noise=max_single_tool_noise,
                user_noise=user_noise,              
            )
        except TaskTimeout:
            raise
        except Exception as e:
            if attempt < max_retries:
                logger.warning(f"Task {task.id} failed on attempt {attempt + 1}/{max_retries + 1}: {e}. Retrying...")
                # Clear global state, prepare for retry
                _clear_global_state()
                continue
            else:
                logger.error(f"Task {task.id} failed after {max_retries + 1} attempts. Last error: {e}")
                raise e

# 单个任务的运行和评估，返回的是simulation里面有配置，reward等等
def _run_task_internal(
    domain: str,
    task: Task,
    agent: str,
    user: str,
    llm_agent: Optional[str] = None,
    llm_args_agent: Optional[dict] = None,
    llm_user: Optional[str] = None,
    llm_args_user: Optional[dict] = None,
    max_steps: int = 100,
    max_errors: int = 10,
    evaluation_type: EvaluationType = "trajectory",
    seed: Optional[int] = None,
    enable_think: bool = False,
    llm_evaluator: Optional[str] = None,
    llm_args_evaluator: Optional[dict] = None,
    language: str = None,
    noise_category: str = None,  # 新增参数
    priority_level: int = 1,
    noise_nums: int = 1, # 新增参数
    max_single_tool_noise: int = 2,
    user_noise: str=None,
) -> SimulationRun:
    """
    Internal implementation of run_task without retry logic.
    """
    _clear_global_state()
    
    global registry
    logger.info(
        f"STARTING SIMULATION: Domain: {domain}, Task: {task.id}, Agent: {agent}, User: {user}"
    )
    if "," in domain:
        environment = get_cross_environment(domain, task.environment, language)
    else:
        environment_constructor = registry.get_env_constructor(domain)
        environment = environment_constructor(task.environment, language)
    AgentConstructor = registry.get_agent_constructor(agent)
    # try:
    #     # print(f" @@@@@@@@{str(environment.tools.db)}\n")
    #     instance_attrs = vars(environment.tools)
    #     print("实例属性 (vars(environment)):")
    #     for key, value in instance_attrs.items():
    #         print(f"{key}: {value}\n")
    # except TypeError as e:
    #     print(f"该对象没有 __dict__ 属性，无法使用 vars(): {e}")
    solo_mode = False
    time = environment.tools.db.time
    global global_time
    global_time = time
    logger.info(f"|| Time Set To: {time}")

    if issubclass(AgentConstructor, LLMAgent):
        agent = AgentConstructor(
            tools=environment.get_tools(),
            domain_policy=environment.get_policy(),
            llm=llm_agent,
            llm_args=llm_args_agent,
            time=time,
            enable_think=enable_think,
            language=language,
        )
    elif issubclass(AgentConstructor, LLMSoloAgent):
        solo_mode = True
        agent = AgentConstructor(
            tools=environment.get_tools(),
            domain_policy=environment.get_policy(),
            llm=llm_agent,
            llm_args=llm_args_agent,
            time=time,
            enable_think=enable_think,
            language=language,
        )
    else:
        raise ValueError(
            f"Unknown agent type: {AgentConstructor}. Should be LLMAgent or LLMSoloAgent"
        )

    UserConstructor = registry.get_user_constructor(user)

    # user_agent的参数配置，llm agent不需要配置，直接作为run_task的输入参数
    # 用户画像：task.user_scenario.user_profile
    # 
    user = UserConstructor(
        persona=str(task.user_scenario.user_profile),
        instructions=str(task.instructions),
        llm=llm_user,
        llm_args=llm_args_user,
        language=language,
        user_noise=user_noise,
    )

    orchestrator = Orchestrator(
        domain=domain,
        agent=agent,
        user=user,
        environment=environment,
        task=task,
        max_steps=max_steps,# 修正为10
        max_errors=max_errors,
        seed=seed,
        solo_mode=solo_mode,
        language=language,
        noise_category=noise_category,
        priority_level=priority_level,
        noise_nums=noise_nums,
        max_single_tool_noise=max_single_tool_noise,
    )
    simulation = orchestrator.run()
    # 如何进行的评估呢
    reward_info = evaluate_simulation(
        domain=domain,
        task=task,
        simulation=simulation,
        evaluation_type=evaluation_type,
        llm_evaluator=llm_evaluator,
        llm_args_evaluator=llm_args_evaluator,
        language=language,
        category=noise_category,
    )
    simulation.reward_info = reward_info
    
    logger.info(
        f"FINISHED SIMULATION: Domain: {domain}, Task: {task.id}, Agent: {agent.__class__.__name__}, User: {user.__class__.__name__}. "
        f"Reward: {reward_info.reward} | {reward_info.reward_breakdown}"
    )

    # Results land under the repo's data dir, like the simulations above, so a
    # checkout without the original /NAS mount can still run; VITA_RESULTS_DIR
    # overrides it.
    base_dir = Path(os.environ.get("VITA_RESULTS_DIR") or (DATA_DIR / "results"))
    # timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")  
    filename = f"simulation_result_{agent}_{noise_category}.json"
    file_path = base_dir / filename

    # 3. 确保输出目录存在
    # exist_ok because simulations run through max_concurrency workers, and the
    # earlier exists()-then-makedirs() could lose that race.
    base_dir.mkdir(parents=True, exist_ok=True)
    reward_data = {
        'task.id': task.id,
        'reward_breakdown': reward_info.reward_breakdown,
    }

    try:
        with open(file_path, 'a') as f:  # 使用追加模式
            json.dump(reward_data, f)
            f.write('\n')  # 添加换行符分隔记录
        print("数据已追加到JSON文件（换行格式）")
        
    except Exception as e:
        print(f"写入文件时出错: {e}")
    return simulation
def get_info(
    domain: str,
    agent: str,
    user: str,
    llm_agent: Optional[str] = None,
    llm_args_agent: Optional[dict] = None,
    llm_user: Optional[str] = None,
    llm_args_user: Optional[dict] = None,
    num_trials: int = 1,
    max_steps: int = 100,
    max_errors: int = 10,
    seed: Optional[int] = None,
    language: str = None,
    user_noise: str = None,
) -> Info:
    def clean_llm_args(llm_args: Optional[dict]) -> Optional[dict]:
        """Clean LLM arguments to make them JSON serializable"""
        if llm_args is None:
            return None
        
        cleaned = {}
        for key, value in llm_args.items():
            if hasattr(value, '__class__') and value.__class__.__name__ == 'type':
                # Replace type objects with their class name
                cleaned[key] = value.__name__
            else:
                cleaned[key] = value
        return cleaned
    
    user_info = UserInfo(
        implementation=user,
        llm=llm_user,
        llm_args=clean_llm_args(llm_args_user),
        global_simulation_guidelines=get_global_user_sim_guidelines(language, user_noise),
    )
    agent_info = AgentInfo(
        implementation=agent,
        llm=llm_agent,
        llm_args=clean_llm_args(llm_args_agent),
    )
    environment_info = get_environment_info(
        domain, include_tool_info=False
    )
    return Info(
        git_commit=get_commit_hash(),
        num_trials=num_trials,
        max_steps=max_steps,
        max_errors=max_errors,
        user_info=user_info,
        agent_info=agent_info,
        environment_info=environment_info,
        seed=seed,
    )


def _clear_global_state():
    from vita.data_model.tasks import (
        StoreBaseModel, ProductBaseModel
    )

    base_classes = [
        StoreBaseModel, ProductBaseModel
    ]
    
    for base_class in base_classes:
        try:
            if hasattr(base_class, 'clear_thread_data'):
                base_class.clear_thread_data()
        except Exception:
            pass


def re_evaluate_simulation(config: RunConfig) -> Results:
    """
    Re-evaluate simulations from a saved simulation file, with optional re-running of specific tasks.
    
    Args:
        config (RunConfig): The run configuration containing:
            - re_evaluate_file (str): Path to the simulation file to load
            - evaluation_type (EvaluationType): The type of evaluation to use
            - save_to (Optional[str | Path]): Path to save the re-evaluation results
            - re_run (bool): Whether to re-run tasks specified by task_ids
            - task_ids (Optional[list[str]]): Task IDs to re-run (only used if re_run is True)

    Returns:
        Results: The re-evaluation results
    """
    re_evaluate_file = config.re_evaluate_file
    evaluation_type = config.evaluation_type
    save_to = config.save_to
    re_run = getattr(config, 're_run', False)
    task_ids_to_rerun = config.task_ids if re_run else None
    
    # Load the original simulation results
    simulation_path = Path(re_evaluate_file)
    if not simulation_path.exists():
        raise FileNotFoundError(f"Simulation file not found: {re_evaluate_file}")
    
    # Load the original results
    with open(simulation_path, "r") as fp:
        original_results = Results.model_validate_json(fp.read())
    
    logger.info(f"Loaded simulation file: {re_evaluate_file}")
    logger.info(f"Found {len(original_results.simulations)} simulations")
    
    # Handle re-running specific tasks if requested
    if re_run and task_ids_to_rerun:
        logger.info(f"Re-running tasks: {task_ids_to_rerun}")
        
        # Get tasks to re-run
        if config.task_set_name is None:
            task_set_name = config.domain
        else:
            task_set_name = config.task_set_name
        
        tasks_to_rerun = get_tasks(task_set_name, task_ids_to_rerun, None, config.language)
        
        # Run the specific tasks
        rerun_results = run_tasks(
            domain=config.domain,
            tasks=tasks_to_rerun,
            agent=config.agent,
            user=config.user,
            llm_agent=config.llm_agent,
            llm_args_agent=config.llm_args_agent,
            llm_user=config.llm_user,
            llm_args_user=config.llm_args_user,
            num_trials=config.num_trials,
            max_steps=config.max_steps,
            max_errors=config.max_errors,
            save_to=None,  # Don't save intermediate results
            console_display=True,
            evaluation_type=evaluation_type,
            max_concurrency=config.max_concurrency,
            seed=config.seed,
            log_level=config.log_level,
            enable_think=config.enable_think,
            llm_evaluator=config.llm_evaluator,
            llm_args_evaluator=config.llm_args_evaluator,
            language=config.language,
            noise_category=config.noise_category,
            priority_level=config.priority_level,
            noise_nums=config.noise_nums, # 新增参数 
            max_single_tool_noise=config.max_single_tool_noise
                       
        )
        
        # Remove old simulations for the re-run task IDs
        original_simulations = [
            sim for sim in original_results.simulations 
            if sim.task_id not in task_ids_to_rerun
        ]
        
        # Combine original simulations (excluding re-run tasks) with new simulations
        combined_simulations = original_simulations + rerun_results.simulations
        
        # Update original_results with combined simulations
        original_results.simulations = combined_simulations
        
        logger.info(f"Combined {len(original_simulations)} existing simulations with {len(rerun_results.simulations)} re-run simulations")
    
    logger.info(f"Total simulations to re-evaluate: {len(original_results.simulations)}")
    
    # Update tasks list if we re-ran any tasks (to ensure we have the latest task definitions)
    final_tasks = original_results.tasks
    if re_run and task_ids_to_rerun:
        # Create a mapping of task_id to task for efficient lookup
        existing_task_ids = {task.id for task in original_results.tasks}
        new_tasks = [task for task in tasks_to_rerun if task.id not in existing_task_ids]
        if new_tasks:
            final_tasks = original_results.tasks + new_tasks
            logger.info(f"Added {len(new_tasks)} new tasks to the task list")
    
    # Create new results object for re-evaluation
    re_eval_results = Results(
        timestamp=get_now(),
        info=original_results.info,
        tasks=final_tasks,
        simulations=[],
    )
    
    # Asynchronously re-evaluate each simulation
    def _re_evaluate_single(simulation, task_dict, domain_name, progress_str):
        """Function to re-evaluate a single simulation"""
        logger.info(f"{progress_str} Re-evaluating simulation: {simulation.task_id}")
        
        task = task_dict.get(simulation.task_id)
        if task is None:
            logger.warning(f"Task {simulation.task_id} not found, skipping simulation")
            return {"status": "skipped", "simulation": simulation, "reason": "task_not_found"}
        
        try:
            reward_info = evaluate_simulation(
                simulation=simulation,
                task=task,
                evaluation_type=evaluation_type,
                domain=domain_name,
                llm_evaluator=config.llm_evaluator,
                llm_args_evaluator=config.llm_args_evaluator,
                language=config.language,
                # 不传 category 时偏离审计会被门控关掉，重评估出来的 induce/redundant
                # 分数会和新跑一次的结果不一致。
                category=config.noise_category,
            )
            
            # Create a new simulation run with updated reward info
            re_eval_simulation = SimulationRun(
                id=simulation.id,
                task_id=simulation.task_id,
                timestamp=simulation.timestamp,
                start_time=simulation.start_time,
                end_time=simulation.end_time,
                duration=simulation.duration,
                termination_reason=simulation.termination_reason,
                agent_cost=simulation.agent_cost,
                user_cost=simulation.user_cost,
                reward_info=reward_info,  # Updated reward info
                messages=simulation.messages,  # Keep original messages
                states=simulation.states,  # Keep original states
                trial=simulation.trial,
                seed=simulation.seed,
                # 注入留档是评测端的 ground truth，重建时必须带上，否则重评估产出的
                # 文件里就没有噪声落点，后续再评估或跨档位对比都无从下手。
                noise_injections=simulation.noise_injections,
            )
            
            logger.info(f"Re-evaluation completed for {simulation.task_id}: reward = {reward_info.reward}")
            return {"status": "success", "simulation": re_eval_simulation}
            
        except Exception as e:
            logger.error(f"Error re-evaluating simulation {simulation.task_id}: {e}")
            return {"status": "failed", "simulation": simulation, "error": str(e)}
    
    # Create task dictionary for quick lookup
    task_dict = {task.id: task for task in final_tasks}
    domain_name = original_results.info.environment_info.domain_name
    
    # Prepare parameters for asynchronous execution
    args = []
    for i, simulation in enumerate(original_results.simulations):
        progress_str = f"({i + 1}/{len(original_results.simulations)})"
        args.append((simulation, task_dict, domain_name, progress_str))
    
    # Use thread pool for asynchronous re-evaluation execution
    max_concurrency = getattr(config, 'max_concurrency', 4)  # Default concurrency is 4
    with ThreadPoolExecutor(max_workers=max_concurrency) as executor:
        results = list(executor.map(_re_evaluate_single, *zip(*args)))
    
    # Process results
    successful_count = 0
    failed_count = 0
    skipped_count = 0
    
    for result in results:
        if result["status"] == "success":
            re_eval_results.simulations.append(result["simulation"])
            successful_count += 1
        elif result["status"] == "failed":
            # For failed cases, add original simulation but throw error
            re_eval_results.simulations.append(result["simulation"])
            failed_count += 1
            print(f"Error of {result['simulation'].task_id} trial {result['simulation'].trial} re-evaluate: {result['error']}")
        elif result["status"] == "skipped":
            # For skipped cases, add original simulation
            re_eval_results.simulations.append(result["simulation"])
            skipped_count += 1
    
    # Output statistics
    ConsoleDisplay.console.print(
        f"\n✨ [bold green]Re-evaluation completed![/bold green]\n"
        f"📊 [bold blue]Statistics:[/bold blue]\n"
        f"  ✅ Successfully re-evaluated: {successful_count}\n"
        f"  ❌ Failed: {failed_count}\n"
        f"  ⏭️  Skipped: {skipped_count}\n"
        f"  📝 Total: {len(results)}"
    )
    
    metrics = compute_metrics(re_eval_results)
    ConsoleDisplay.display_agent_metrics(metrics, config.noise_category)

    if config.csv_output_file and re_eval_results.simulations:
        try:
            csv_output = config.csv_output_file
            save_results_to_csv(re_eval_results, csv_output, config, metrics)
            ConsoleDisplay.console.print(f"\n💾 [bold green]Results appended to CSV: {csv_output}[/bold green]")
        except Exception as e:
            ConsoleDisplay.console.print(f"\n[bold red]Error saving to CSV: {e}[/bold red]")

    # Save results if save_to is specified
    if save_to is not None:
        if isinstance(save_to, str):
            save_to = Path(save_to)
        
        # Create parent directories if needed
        if not save_to.parent.exists():
            save_to.parent.mkdir(parents=True, exist_ok=True)
        
        # Generate filename if not provided
        if save_to.is_dir() or save_to.name == "":
            original_name = simulation_path.stem
            save_to = save_to / f"{original_name}_re_eval_{evaluation_type}.json"
        
        logger.info(f"Saving re-evaluation results to: {save_to}")
        re_eval_results.save(save_to)
    
    return re_eval_results