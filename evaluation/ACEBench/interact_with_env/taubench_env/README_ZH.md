# TauBench 在 EnvScaler 中的运行教程

本文档面向第一次接触 TauBench 的使用者，说明 TauBench 是什么、这个仓库如何组织 TauBench、数据与任务格式是什么、评测如何进行、本地 vLLM 如何部署、如何运行 retail/airline 两个环境，以及如何查看结果。

## 1. TauBench 是什么

TauBench 是一个面向 **工具调用 Agent** 的交互式评测基准。它不是简单的单轮问答，而是让模型扮演客服 Agent，在一个有状态的业务环境中和用户多轮对话、查询数据库、调用工具修改状态，最后判断任务是否真的完成。

本仓库把 TauBench 官方逻辑整理成类似 Gym 的环境接口：

```python
observation, info = env.reset(task_index=0)
while True:
    action = agent.step(observation)
    observation, reward, terminated, truncated, info = env.step(action)
    if terminated or truncated:
        break
```

这里的关键角色有三个：

| 角色 | 在代码里的位置 | 作用 |
| --- | --- | --- |
| Agent LLM | `agent/task_solve_agent.py` | 被评测的模型，负责理解用户需求、决定问用户还是调用工具 |
| Env | `taubench_env/base_env.py`、`retail_env.py`、`airline_env.py` | 业务环境，维护数据库状态、执行工具、计算奖励 |
| User Simulator | `taubench_env/envs/user.py` | 模拟用户，根据隐藏 instruction 和 Agent 对话 |

所以 TauBench 测的是：模型能否在多轮对话中收集必要信息、遵守业务规则、正确调用工具，并把后端数据库改成和标准答案一致的状态。

## 2. 本仓库支持的 TauBench 环境

本目录支持两个环境名：

| 环境名 | 领域 | 任务数 | 默认任务来源 |
| --- | --- | ---: | --- |
| `tau_bench_retail` | 在线零售客服 | 115 | `envs/retail/tasks_test.py` |
| `tau_bench_airline` | 航空订票客服 | 50 | `envs/airline/tasks_test.py` |

在 `run_main.py` 里，二者的默认配置如下：

```python
env_config = {
    "mode": "eval",
    "user_model": "gpt-4.1-2025-04-14",
    "user_strategy": "llm_react",
    "user_provider": "openai",
}
infer_mode = "fc"
```

如果你本地部署 LLM，必须把 `user_model` 改成本地 vLLM 暴露的模型名，否则模拟用户会请求本地服务里不存在的 `gpt-4.1-2025-04-14`。

## 3. 目录结构

```text
taubench_env/
├── __init__.py
├── base_env.py                  # TauBench 环境通用逻辑：reset/step/reward
├── retail_env.py                # retail 环境：加载零售数据、工具、任务、规则
├── airline_env.py               # airline 环境：加载航空数据、工具、任务、规则
├── tau_bench_types.py           # Task、Action、RewardResult 等数据结构
├── utils/
│   ├── parse_util.py            # 解析 prompt / FC 模式下的模型输出
│   ├── hash_util.py             # 对数据库状态做 hash，用于奖励计算
│   └── user_llm_inference.py    # 模拟用户的 OpenAI-compatible 调用
└── envs/
    ├── user.py                  # human / llm / llm_react 用户模拟器
    ├── tool.py                  # 工具基类
    ├── retail/
    │   ├── data/                # users/orders/products
    │   ├── tools/               # 零售工具 API
    │   ├── tasks_test.py        # retail eval 任务
    │   ├── tasks_dev.py
    │   ├── tasks_train.py
    │   ├── rules.py             # 零售业务规则
    │   └── wiki.md              # 给 Agent 的领域说明
    └── airline/
        ├── data/                # users/reservations/flights
        ├── tools/               # 航空工具 API
        ├── tasks_test.py        # airline eval 任务
        ├── rules.py
        └── wiki.md
```

## 4. 数据格式

### 4.1 Task 格式

任务由 `tau_bench_types.py` 中的 `Task` 表示，核心字段是：

```python
class Task(BaseModel):
    user_id: str
    actions: List[Action]
    instruction: str
    outputs: List[str]
```

含义如下：

| 字段 | 含义 |
| --- | --- |
| `user_id` | 当前任务对应的真实用户 id。Agent 不一定一开始知道，需要通过对话/工具确认 |
| `instruction` | 给模拟用户看的隐藏任务说明。Agent 不能直接看到完整 instruction，只能和用户对话逐步获取信息 |
| `actions` | 标准答案动作序列，主要用于计算最终数据库状态是否正确 |
| `outputs` | 如果任务还要求 Agent 在自然语言回复中给出某些结果，例如金额、数量，这里会列出必须出现的字符串 |

一个 retail 任务大致长这样：

```python
Task(
    user_id="yusuf_rossi_9620",
    instruction="You are Yusuf Rossi ... wish to exchange ...",
    actions=[
        Action(name="find_user_id_by_name_zip", kwargs={...}),
        Action(name="get_order_details", kwargs={...}),
        Action(name="exchange_delivered_order_items", kwargs={...}),
    ],
    outputs=[],
)
```

一个 airline 任务大致长这样：

```python
Task(
    user_id="mia_li_3668",
    instruction="Your user id is mia_li_3668. You want to fly ...",
    actions=[
        Action(
            name="book_reservation",
            kwargs={
                "user_id": "mia_li_3668",
                "origin": "JFK",
                "destination": "SEA",
                "flight_type": "one_way",
                "cabin": "economy",
                "flights": [...],
                "payment_methods": [...],
            },
        )
    ],
    outputs=[],
)
```

### 4.2 Action 格式

`Action` 是工具调用或对用户回复的统一表示：

```python
class Action(BaseModel):
    name: str
    kwargs: Dict[str, Any]
```

如果 `name` 是工具名，环境会执行对应工具；如果 `name == "chat_with_user"`，表示 Agent 直接对用户说话。

例如：

```python
Action(
    name="get_order_details",
    kwargs={"order_id": "#W2378156"},
)
```

或者：

```python
Action(
    name="chat_with_user",
    kwargs={"content": "I found your order. Do you want me to proceed with the exchange?"},
)
```

### 4.3 Tool 格式

每个工具都是一个 Python 类，继承 `envs/tool.py` 里的 `Tool`，至少实现两个静态方法：

```python
class Tool:
    @staticmethod
    def invoke(*args, **kwargs):
        raise NotImplementedError

    @staticmethod
    def get_info() -> dict:
        raise NotImplementedError
```

`get_info()` 返回 OpenAI Function Calling 格式的工具 schema。例如 `get_order_details`：

```python
{
    "type": "function",
    "function": {
        "name": "get_order_details",
        "description": "Get the status and details of an order.",
        "parameters": {
            "type": "object",
            "properties": {
                "order_id": {
                    "type": "string",
                    "description": "The order id, such as '#W0000000'.",
                },
            },
            "required": ["order_id"],
        },
    },
}
```

在 `infer_mode="fc"` 时，这些 schema 会传给 OpenAI-compatible Chat Completions 的 `tools` 参数，模型需要返回结构化 `tool_calls`。

### 4.4 Retail 数据

路径：

```text
envs/retail/data/
├── users.json
├── orders.json
└── products.json
```

含义：

| 文件 | 内容 |
| --- | --- |
| `users.json` | 用户资料、邮箱、地址、支付方式、订单列表 |
| `orders.json` | 订单状态、商品 item、支付、收货、退换货相关信息 |
| `products.json` | 商品库，每个商品有不同变体，例如颜色、尺寸、兼容性等 |

Retail 工具包括：

```text
calculate
cancel_pending_order
exchange_delivered_order_items
find_user_id_by_email
find_user_id_by_name_zip
get_order_details
get_product_details
get_user_details
list_all_product_types
modify_pending_order_address
modify_pending_order_items
modify_pending_order_payment
modify_user_address
return_delivered_order_items
think
transfer_to_human_agents
```

Retail 规则在 `envs/retail/rules.py`，例如：

- Agent 要先通过 email 或 name+zip 确认用户身份。
- 涉及数据库修改时，必须先向用户确认交易细节并获得明确授权。
- 每次最多调用一个工具。
- 不应编造工具和用户没有提供的信息。
- 不应把任务转人工，除非无法解决。

### 4.5 Airline 数据

路径：

```text
envs/airline/data/
├── users.json
├── reservations.json
└── flights.json
```

含义：

| 文件 | 内容 |
| --- | --- |
| `users.json` | 用户资料、支付方式、证书/礼品卡、已有预订 |
| `reservations.json` | 已有机票预订、乘客、航段、舱位、支付历史、行李、保险 |
| `flights.json` | 航班号、起降机场、日期、价格、座位余量、航班状态 |

Airline 工具包括：

```text
book_reservation
calculate
cancel_reservation
get_reservation_details
get_user_details
list_all_airports
search_direct_flight
search_onestop_flight
send_certificate
think
transfer_to_human_agents
update_reservation_baggages
update_reservation_flights
update_reservation_passengers
```

当前 `TauBenchAirlineEnv` 只支持 `mode="eval"`。

## 5. 评测流程

### 5.1 reset 阶段

`TauBenchBaseEnv.reset(task_index=...)` 会做这些事：

1. 重新加载数据库。这样每个任务都从干净初始状态开始。
2. 根据 `task_index` 选择任务。
3. 用任务的 `instruction` 初始化模拟用户。
4. 返回模拟用户第一句话，以及环境信息：

```python
observation = initial_user_message
info = {
    "env_introduction": wiki,
    "tools": tools_info,
    "task": task,
}
```

Agent 会看到：

- 系统提示词。
- `wiki.md` 里的领域说明。
- 可用工具 schema。
- 用户第一句话。

Agent 不会直接看到完整标准答案 `actions`。

### 5.2 step 阶段

每一步中：

1. `TaskSolveAgent` 把历史消息、工具 schema 发给 LLM。
2. LLM 返回自然语言回复或工具调用。
3. `TauBenchBaseEnv.step(action)` 解析并执行动作。
4. 如果是工具调用，环境返回工具结果。
5. 如果是 `chat_with_user`，环境把 Agent 的话交给模拟用户，再返回用户下一句话。
6. 如果用户返回 `###STOP###` 或调用了终止工具，任务结束并计算 reward。

在 `fc` 模式下，模型应该返回类似 OpenAI 的结构化工具调用：

```json
{
  "tool_calls": [
    {
      "id": "call_xxx",
      "type": "function",
      "function": {
        "name": "get_order_details",
        "arguments": "{\"order_id\":\"#W2378156\"}"
      }
    }
  ],
  "content": ""
}
```

在 `prompt` 模式下，模型需要在文本里输出：

```text
<tool_call>
{"name": "get_order_details", "arguments": {"order_id": "#W2378156"}}
</tool_call>
```

本仓库对 TauBench 默认使用 `fc`。

### 5.3 终止条件

任务会在以下情况下结束：

| 情况 | 含义 |
| --- | --- |
| 用户模拟器返回 `###STOP###` | 用户认为任务完成 |
| Agent 调用 `transfer_to_human_agents` | 终止工具 |
| 达到最大步数 | `tau_bench_retail` 和 `tau_bench_airline` 都是 30 步 |
| 解析失败 | 例如模型输出无法转成合法 action |

如果达到最大步数仍未完成，结果里的 `terminated` 通常为 `false`，`truncated` 可能体现异常/截断情况，最终分数通常不会高。

## 6. 奖励如何计算

TauBench 的核心不是看工具调用序列是否逐字一致，而是看 **最终状态和必要输出是否正确**。

`calculate_reward()` 的逻辑在 `base_env.py`：

1. 对 Agent 实际执行后的数据库状态做 hash。
2. 重新加载初始数据库。
3. 执行任务标准答案里的 `actions`，得到标准最终数据库状态。
4. 对标准最终状态做 hash。
5. 比较两个 hash：
   - 相同：数据库修改正确。
   - 不同：数据库修改错误，reward 变成 0。
6. 如果 `outputs` 非空，还会检查 Agent 对用户说过的话里是否包含每个必要输出字符串。

最终每个任务的 `total_reward` 通常是二值：

| 分数 | 含义 |
| --- | --- |
| `1.0` | 最终数据库状态正确，且必要自然语言输出也满足 |
| `0.0` | 状态修改错误、缺少必要输出、提前结束或其他失败 |

注意：中间过程是否和标准答案完全同序不一定重要，但如果违反业务规则导致状态不对，最终会失败。

## 7. 本地部署 vLLM

本仓库在 `interact_with_env/vllm_serve` 下提供了部署目录：

```text
../vllm_serve/
├── README_ZH.md
└── vllm_serve_taubench.sh
```

默认配置：

| 参数 | 默认值 |
| --- | --- |
| `MODEL_PATH` | `/fs/archive/share/u2024001049/train_models/EnvScaler/EnvScaler-Qwen3-8B` |
| `MODEL_NAME` | `EnvScaler-Qwen3-8B` |
| `PORTS` | `8000` |
| `GPU_IDS` | `0` |
| `ENABLE_TOOL_CALLING` | `true` |
| `TOOL_CALL_PARSER` | `hermes` |

启动：

```bash
cd /fs/archive/share/u2024001049/EnvScaler-main/interact_with_env/vllm_serve
bash vllm_serve_taubench.sh
```

启动后 API 地址是：

```text
http://127.0.0.1:8000/v1
```

模型名是：

```text
EnvScaler-Qwen3-8B
```

如果要换模型或端口：

```bash
MODEL_PATH=/path/to/model \
MODEL_NAME=my-model \
GPU_IDS="1" \
PORTS="8010" \
bash vllm_serve_taubench.sh
```

如果要开多个实例：

```bash
GPU_IDS="0 1 2 3" \
PORTS="8000 8001 8002 8003" \
bash vllm_serve_taubench.sh
```

当前 `run_main.py` 一次只接收一个 `--agent-base-url`，所以多实例更适合你自己在外层做负载均衡，或者分别开多个评测进程。

### 7.1 检查 vLLM 是否可用

另开一个终端：

```bash
curl http://127.0.0.1:8000/v1/models
```

应该能看到 `EnvScaler-Qwen3-8B`。

如果日志里提示 `--enable-auto-tool-choice` 或 `--tool-call-parser` 不支持，说明 vLLM 版本较旧或 parser 名称不同。可以先关掉脚本的工具解析启动项：

```bash
ENABLE_TOOL_CALLING=false bash vllm_serve_taubench.sh
```

但正式跑 TauBench 的 `fc` 模式时，仍建议把 vLLM 的工具调用解析配置好，否则模型可能不会返回 OpenAI 格式的 `tool_calls`。

## 8. 运行 TauBench

所有命令都建议从 `interact_with_env` 目录运行：

```bash
cd /fs/archive/share/u2024001049/EnvScaler-main/interact_with_env
```

先设置环境变量。TauBench 模拟用户只读取 `OPENAI_API_KEY` 和 `OPENAI_BASE_URL`：

```bash
export OPENAI_API_KEY=EMPTY
export OPENAI_BASE_URL=http://127.0.0.1:8000/v1
```

### 8.1 跑 retail 小样本

```bash
python run_main.py \
  --env-name tau_bench_retail \
  --agent-model EnvScaler-Qwen3-8B \
  --agent-model-provider openai \
  --agent-api-key EMPTY \
  --agent-base-url http://127.0.0.1:8000/v1 \
  --infer-mode fc \
  --enable-thinking false \
  --num-workers 1 \
  --task-start 0 \
  --task-end 3 \
  --env-config-json '{"user_model":"EnvScaler-Qwen3-8B","user_provider":"openai","user_strategy":"llm_react"}'
```

### 8.2 跑 airline 小样本

```bash
python run_main.py \
  --env-name tau_bench_airline \
  --agent-model EnvScaler-Qwen3-8B \
  --agent-model-provider openai \
  --agent-api-key EMPTY \
  --agent-base-url http://127.0.0.1:8000/v1 \
  --infer-mode fc \
  --enable-thinking false \
  --num-workers 1 \
  --task-start 0 \
  --task-end 3 \
  --env-config-json '{"user_model":"EnvScaler-Qwen3-8B","user_provider":"openai","user_strategy":"llm_react"}'
```

### 8.3 跑全量

Retail：

```bash
python run_main.py \
  --env-name tau_bench_retail \
  --agent-model EnvScaler-Qwen3-8B \
  --agent-model-provider openai \
  --agent-api-key EMPTY \
  --agent-base-url http://127.0.0.1:8000/v1 \
  --infer-mode fc \
  --enable-thinking false \
  --num-workers 3 \
  --task-start 0 \
  --task-end 115 \
  --env-config-json '{"user_model":"EnvScaler-Qwen3-8B","user_provider":"openai","user_strategy":"llm_react"}'
```

Airline：

```bash
python run_main.py \
  --env-name tau_bench_airline \
  --agent-model EnvScaler-Qwen3-8B \
  --agent-model-provider openai \
  --agent-api-key EMPTY \
  --agent-base-url http://127.0.0.1:8000/v1 \
  --infer-mode fc \
  --enable-thinking false \
  --num-workers 3 \
  --task-start 0 \
  --task-end 50 \
  --env-config-json '{"user_model":"EnvScaler-Qwen3-8B","user_provider":"openai","user_strategy":"llm_react"}'
```

### 8.4 指定任务 id

```bash
python run_main.py \
  --env-name tau_bench_retail \
  --agent-model EnvScaler-Qwen3-8B \
  --agent-model-provider openai \
  --agent-api-key EMPTY \
  --agent-base-url http://127.0.0.1:8000/v1 \
  --infer-mode fc \
  --enable-thinking false \
  --num-workers 1 \
  --task-ids 0,1,2 \
  --env-config-json '{"user_model":"EnvScaler-Qwen3-8B","user_provider":"openai","user_strategy":"llm_react"}'
```

## 9. 关键参数解释

| 参数 | 说明 |
| --- | --- |
| `--env-name` | 选环境：`tau_bench_retail` 或 `tau_bench_airline` |
| `--agent-model` | 被评测 Agent 的模型名，必须等于 vLLM 的 `--served-model-name` |
| `--agent-model-provider` | 当前应使用 `openai`，表示走 OpenAI-compatible 接口 |
| `--agent-api-key` | 本地 vLLM 可以填 `EMPTY`，但不能为空 |
| `--agent-base-url` | Agent 模型服务地址，例如 `http://127.0.0.1:8000/v1` |
| `--infer-mode` | TauBench 默认 `fc`；`prompt` 是文本标签解析模式 |
| `--enable-thinking` | Qwen3 类模板可用；如果后端报 `extra_body` 相关错误，先设为 `false` |
| `--num-workers` | 并发任务数；本地评测先用 `1`，稳定后再调大 |
| `--task-start` / `--task-end` | 按连续范围选择任务，`task-end` 是开区间 |
| `--task-ids` | 直接指定任务列表，会覆盖 start/end |
| `--env-config-json` | 覆盖环境配置，最常用来改 `user_model` |
| `--save-file-path` | 指定结果 JSON 保存路径 |
| `--single-process` | 强制串行运行，调试问题时更方便 |

## 10. 结果文件怎么看

默认结果路径：

```text
result/<env_name>/<agent_model>-<infer_mode>_<user_model>_<user_strategy>_<timestamp>.json
```

例如：

```text
result/tau_bench_retail/EnvScaler-Qwen3-8B-fc_EnvScaler-Qwen3-8B_llm_react_2026-05-13-15-30-00.json
```

结果文件是一个 list，每个元素对应一个任务。单个任务包含：

```json
{
  "task_info": {
    "user_id": "yusuf_rossi_9620",
    "instruction": "..."
  },
  "tools": [],
  "messages": [],
  "user_messages": [],
  "trajectory": [],
  "total_reward": 1.0,
  "terminated": true,
  "truncated": false,
  "final_observation": {},
  "final_info": {},
  "steps": 12
}
```

核心字段：

| 字段 | 含义 |
| --- | --- |
| `task_info` | 当前任务的用户 id 和隐藏 instruction，用于事后分析 |
| `tools` | 本任务给 Agent 的工具 schema |
| `messages` | Agent 侧完整对话历史，包括 system、user、assistant、tool |
| `user_messages` | 模拟用户内部的对话历史，包含用户模拟器的 thought/response 原始输出 |
| `trajectory` | 每一步的 action、observation、reward、terminated、truncated |
| `total_reward` | 单任务最终分数，通常是 0 或 1 |
| `terminated` | 是否正常结束 |
| `truncated` | 是否因为解析失败、截断等异常提前结束 |
| `final_info.action` | 最后一步解析后的动作 |
| `steps` | 交互步数 |

### 10.1 看平均分

`calc_avg_score.py` 可以计算平均 reward。直接运行：

```bash
python - <<'PY'
from calc_avg_score import calc_avg_score
calc_avg_score("result/tau_bench_retail/你的结果文件.json")
PY
```

输出中的 `avg_score` 是百分制：

```text
all_num: 115 avg_score: 42.61
```

意思是 115 个任务里平均 reward 为 0.4261。

### 10.2 分析失败任务

如果某个任务 `total_reward == 0.0`，优先看：

1. `trajectory` 最后一两步：模型是否调用了错误工具、参数错、或者没拿到用户授权。
2. `final_info.action`：最后一步实际被环境解析成什么动作。
3. `messages`：模型是否返回了空 `tool_calls`、多个工具调用、格式不合法。
4. `user_messages`：模拟用户是否已经给过必要信息，还是 Agent 没有问出来。
5. `terminated` / `truncated`：是否达到结束条件或异常结束。

常见失败类型：

| 现象 | 可能原因 |
| --- | --- |
| `Message to Action Failed` | FC 返回结构不符合预期，或 prompt 模式标签不合法 |
| `tool_calls` 为空 | vLLM 工具调用解析没配置好，或模型没学会用工具 |
| 工具返回 `Error: ... not found` | 工具参数错，例如订单号漏了 `#` |
| 用户一直不 `###STOP###` | Agent 没完成任务，或没有向用户确认结束 |
| reward 为 0 但对话看似合理 | 最终数据库状态和标准答案 hash 不一致，通常是工具调用参数/金额/商品 id 错 |

## 11. 调试建议

第一次跑时不要直接全量并发，建议顺序是：

1. 启动 vLLM。
2. `curl /v1/models` 确认模型名。
3. `--num-workers 1 --task-start 0 --task-end 1` 跑一个任务。
4. 查看结果 JSON 的 `trajectory`。
5. 确认 FC 能返回结构化 `tool_calls`。
6. 再扩大到 3 个任务。
7. 最后跑全量。

如果要调具体某个任务：

```bash
python run_main.py \
  --env-name tau_bench_retail \
  --agent-model EnvScaler-Qwen3-8B \
  --agent-model-provider openai \
  --agent-api-key EMPTY \
  --agent-base-url http://127.0.0.1:8000/v1 \
  --infer-mode fc \
  --enable-thinking false \
  --single-process \
  --task-ids 7 \
  --save-file-path result_debug/tau_bench_retail_task7.json \
  --env-config-json '{"user_model":"EnvScaler-Qwen3-8B","user_provider":"openai","user_strategy":"llm_react"}'
```

## 12. 重要注意事项

- 一定要从 `interact_with_env` 目录运行命令，避免相对路径和结果目录混乱。
- `--agent-model` 和 `env_config.user_model` 都应等于 vLLM 的 `MODEL_NAME`。
- `OPENAI_BASE_URL` 对模拟用户生效；`--agent-base-url` 对 Agent 生效。
- 如果只设置了 `--agent-base-url`，但没设置 `OPENAI_BASE_URL`，模拟用户可能走不到本地服务。
- 如果只改了 Agent 模型，没有用 `--env-config-json` 改 `user_model`，模拟用户会继续请求默认 GPT 模型名。
- 本地服务并发压力约等于 `num_workers` 乘以每个任务中的 Agent/用户多轮调用，显存不足时先降 `num_workers`。
- `enable_thinking` 对 Qwen3 有用；如果本地服务不接受 `extra_body.chat_template_kwargs.enable_thinking`，先用 `--enable-thinking false`。
- Airline 只支持 `mode="eval"`；Retail 支持 `eval/dev/train`，但默认评测用 `eval`。
- TauBench 的分数严格看最终状态，不要只看自然语言对话是否“像完成了”。

