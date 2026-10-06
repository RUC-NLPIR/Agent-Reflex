# Agent-Reflex Evaluation

Six agent benchmarks, one directory each, all driven against a local vLLM
server that hosts the model under test:

| Directory | Benchmark | Tasks | Metric |
| --- | --- | --- | --- |
| [`Tau2/`](Tau2) | τ²-bench (airline, retail, telecom) | 50 + 114 + 114 = 278 | average reward × 100 |
| [`BFCL-v4/`](BFCL-v4) | BFCL v4 `all_scoring` | 5,217 | official overall accuracy |
| [`ACEBench/`](ACEBench) | ACEBench agent (multi-step, multi-turn) | 20 + 30 = 50 | average reward × 100 |
| [`VitaBench/`](VitaBench) | VitaBench (delivery, instore, ota, cross-domain) | 4 × 100 | trajectory pass@1 × 100 |
| [`AgentNoiseBench/`](AgentNoiseBench) | AgentNoiseBench on τ²-bench and VitaBench | see below | clean / tool-noise / user-noise reward |
| [`ToolSandbox/`](ToolSandbox) | ToolSandbox, offline scenarios | 200 | mean milestone similarity × 100 |

## 1. Fill in the API key first

Every benchmark except BFCL needs an external LLM (user simulator, judge or
noise generator). All of them go through the **Boyue API**, an
OpenAI-compatible gateway, with a single key:

1. Register at [api.boyuerichdata.opensphereai.com](https://api.boyuerichdata.opensphereai.com)
   (docs: [boyuerichdata.apifox.cn](https://boyuerichdata.apifox.cn/)).
2. On the **API令牌 (API tokens)** page, create a token in the `auto` group.
   The key is a string like `sk-xxxxxxxx`.
3. Put it in `evaluation/.env` (git-ignored), the only file the scripts read
   credentials from:

```bash
cp .env.example .env
# then edit .env:
BOYUE_API_KEY=sk-xxxxxxxx
BOYUE_API_BASE_URL=http://35.220.164.252:3888/v1   # outside CN/HK: https://api.boyuerichdata.opensphereai.com/v1
SERPER_API_KEY=<key from serper.dev>               # BFCL-v4 web-search category only
```

To keep the key outside the repository, point `ENV_FILE` at any other file:
`ENV_FILE=/secure/eval.env bash Tau2/run.sh`. The gateway must serve
`gpt-4.1` (it resolves to `gpt-4.1-2025-04-14`) and `claude-sonnet-4-6`. If you
use OpenAI or Anthropic directly, set `BOYUE_API_BASE_URL` to an
OpenAI-compatible endpoint that serves both model names.

If GitHub, PyPI or the gateway needs a proxy, export `HTTP_PROXY` /
`HTTPS_PROXY`. The local vLLM is always reached directly (`NO_PROXY` is set
for you); add any internal PyPI mirror to `NO_PROXY` as well.

## 2. Build the environments

```bash
bash shared/setup_vllm.sh        # vLLM 0.27.1 serving env (Python 3.12)
bash Tau2/setup.sh
bash BFCL-v4/setup.sh
bash ACEBench/setup.sh
bash VitaBench/setup.sh
bash AgentNoiseBench/setup.sh
bash ToolSandbox/setup.sh
```

Every environment is pinned: each bench installs its own `<Bench>/requirements.txt`
(vLLM: `shared/requirements-vllm.txt`), the exact package set used for the
paper numbers, then adds the bench source with `--no-deps`.

Everything is installed under `evaluation/.runtime/` (venvs, uv-managed
Python and upstream checkouts at pinned commits) and every result is written
under `evaluation/outputs/`. Both paths can be moved with `RUNTIME=` and
`OUTPUT_ROOT=`. The benchmarks that wrap an upstream harness clone it at a
fixed commit and apply a small patch from their directory:

| Bench | Upstream | Commit |
| --- | --- | --- |
| Tau2 | [sierra-research/tau2-bench](https://github.com/sierra-research/tau2-bench) | `672227c` |
| BFCL-v4 | [ShishirPatil/gorilla](https://github.com/ShishirPatil/gorilla) (`berkeley-function-call-leaderboard`) | `6ea5797` |
| VitaBench | [meituan-longcat/vitabench](https://github.com/meituan-longcat/vitabench) | `742e240` |
| ToolSandbox | [apple/ToolSandbox](https://github.com/apple/ToolSandbox) | `c8571d7` |
| ACEBench | EnvScaler's [`evaluation/interact_with_env`](https://github.com/RUC-NLPIR/EnvScaler/tree/main/evaluation), vendored | — |
| AgentNoiseBench | AgentNoiseBench forks of τ²-bench and VitaBench, vendored in `AgentNoiseBench/repo/` | — |

## 3. Serve the model

```bash
MODEL_PATH=/path/to/checkpoint bash shared/serve_vllm.sh
```

The server uses tensor parallel 8, bf16, Qwen3-8B's native 40,960-token
context, the `hermes` tool parser, the `deepseek_r1` reasoning parser and
[`shared/configs/qwen3_force_thinking_chat_template.jinja`](shared/configs/qwen3_force_thinking_chat_template.jinja),
which keeps Qwen3 thinking on for every turn. Do not raise `MAX_MODEL_LEN`:
Qwen3's rotary table ends at 40,960 positions. The checkpoint is always served
as `Qwen/Qwen3-8B`; to make sure a run hits the intended weights, every bench
checks that `/v1/models` reports `MODEL_PATH` as its root before it starts.
Keep `MODEL_PATH` exported in the shell that runs the benches.

## 4. Run

All six benchmarks on their full task sets, serving the model first:

```bash
MODEL_PATH=/path/to/checkpoint RUN_NAME=my-model bash run_all.sh
```

Or one at a time against a running server:

```bash
RUN_NAME=my-model bash Tau2/run.sh
RUN_NAME=my-model bash ACEBench/run.sh
RUN_NAME=my-model bash VitaBench/run.sh
RUN_NAME=my-model bash AgentNoiseBench/run.sh
RUN_NAME=my-model bash ToolSandbox/run.sh
RUN_NAME=my-model bash BFCL-v4/run.sh
```

Each run ends with a `summary.json` in `outputs/<bench>/<RUN_NAME>-<tag>/`.
A run whose score is exactly zero is reported as `FAIL`: on these benches
that means the harness, not the model, is broken (wrong endpoint, empty
responses, judge unreachable).

## Protocol

All benches use native function calling with thinking enabled and follow the
official harness settings; the EnvScaler evaluation
([RUC-NLPIR/EnvScaler](https://github.com/RUC-NLPIR/EnvScaler/tree/main/evaluation))
is the reference for ACEBench.

| Bench | Agent sampling | User simulator / judge | Other settings |
| --- | --- | --- | --- |
| Tau2 | temperature 0.0 (tau2 default) | user gpt-4.1, temperature 0.0; NL-assertion judge gpt-4.1 | base split, 1 trial, seed 300 |
| BFCL-v4 | temperature 0.001 (BFCL default) | — (web search through Serper) | `all_scoring` |
| ACEBench | temperature 0.7 | user gpt-4.1 | 20 truncated steps (EnvScaler) |
| VitaBench | temperature 0.0 | user gpt-4.1; judge claude-sonnet-4-6 | Chinese tasks, 300 max steps, 1 trial |
| AgentNoiseBench | as Tau2 / VitaBench | user gpt-4.1; noise generator gpt-4.1; Vita judge claude-sonnet-4-6 | priority level 5 |
| ToolSandbox | temperature 0.6, top-p 0.95, top-k 20 (Qwen3 thinking defaults) | user gpt-4.1 | 200 offline scenarios |

Shared settings live in [`shared/env.sh`](shared/env.sh): 120 concurrent
tasks (`NUM_WORKERS`), 10 retries of the *same* request on transport errors
(`RETRY`) and a 30-minute read timeout for long thinking turns. There is no
per-task time limit, no switch to another model when a request fails, and no
context truncation. The only repair step is BFCL-v4 and ToolSandbox
re-running the cases whose generation crashed on a transport error (the
official scorers would count a crash placeholder as a wrong answer); the
re-run uses the same model and settings.

### Overall scores

* **Tau2**: micro-average over the 278 tasks.
* **BFCL-v4**: 10% Non-Live + 10% Live + 10% Irrelevance + 30% Multi-Turn +
  40% Agentic, with Agentic = (Web Search + Memory) / 2 (official formula).
* **ACEBench**: (multi-step + multi-turn reward) / 50.
* **VitaBench**: pass@1 over all 400 tasks; tasks that crashed count as 0.
* **AgentNoiseBench**: for each of τ²-bench and VitaBench, Tool = mean over
  the five tool noises (fault, incomplete, induce, redundant, wrong) with the
  original user, User = mean over the user noises with clean tools, and
  Avg = (Tool + User) / 2. Overall is the mean of the two Avg values.
* **ToolSandbox**: mean similarity over the 200 scenarios.

## Data

| Bench | Where | Size |
| --- | --- | --- |
| Tau2 | shipped: `Tau2/data/tau2/` (domains + user simulator, voice / audio assets excluded) | 39 MB |
| ACEBench | shipped: `ACEBench/interact_with_env/acebench_env/data/` | 13 MB |
| VitaBench | shipped: `VitaBench/data/vita/domains/` (Chinese task files) | 26 MB |
| AgentNoiseBench | shipped: τ²-bench snapshot in `AgentNoiseBench/data/tau2/`; Vita shares `VitaBench/data` | 33 MB |
| BFCL-v4 | shipped: `BFCL-v4/data/` (the `bfcl_eval/data` test set and answers of gorilla commit `6ea5797`); `setup.sh` installs `bfcl_eval` with this copy | 12 MB |
| ToolSandbox | not shipped: scenarios are Python code in the upstream repository, cloned by `ToolSandbox/setup.sh` at commit `c8571d7` | — |

`Tau2/expected_ids.json` and `ACEBench/validate.py` check that a run
covers exactly the expected task ids before a score is reported.
