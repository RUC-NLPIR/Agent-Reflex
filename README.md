<div align="center">

<img src="assets/cover.gif" alt="Agent-Reflex" width="100%">

# 🪞 Agent-Reflex

### Teaching Language Agents to Act Reflectively

[![Paper](https://img.shields.io/badge/Paper-arXiv-b5212f.svg?logo=arxiv)](https://arxiv.org/abs/XXXX.XXXXX)
[![Skills](https://img.shields.io/badge/RSD%20Skills-1%2C170-f7be50.svg)](RSD)
[![Data](https://img.shields.io/badge/Data-ReSFT%20%7C%20ORPO-7b61c4.svg)](#-data)
[![Model](https://img.shields.io/badge/Backbone-Qwen3--8B-40bac0.svg)](https://huggingface.co/Qwen/Qwen3-8B)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

*A training framework that elicits **proactive reflection** in tool-using LLM agents: noticing noisy tool feedback and user corrections, and recovering from them.*

</div>

## 💡 Highlights

* **Reflection as a learnable meta-skill.** RSD mines **1,170 reflection meta-skills** from success / failure contrasts in MCP-anchored environments with real tool-error perturbations.
* **Reflective SFT.** ReSFT turns the skills into self-reflection, skill-recovery and user-centric correction data: **54,663** verified trajectories.
* **Reflective RL.** ORPO mixes clean and fault-injected rollouts in one GRPO group and adds a confidence-gated, skill-guided on-policy distillation term. Skills are used only during training; deployment is skill-free.
* **Strong 8B agent.** On Qwen3-8B, Agent-Reflex reaches **55.8** Overall on five long-horizon tool-use benchmarks (+15.6 over the backbone, +7.4 over EnvScaler-8B) and leads every 8B method on AgentNoiseBench.

## 🔧 Dependencies

Set these up before running anything.

| What | Needed for | Details |
| --- | --- | --- |
| NVIDIA GPUs (80 GB) | all | ReSFT 2 × 8 GPUs, ORPO 1 × 8, evaluation 1 × 8. Driver must support CUDA 12.8 (ORPO uses cu128 wheels). |
| [uv](https://github.com/astral-sh/uv) + git | all | `pip install uv`. Each part's `setup_env.sh` / `setup.sh` builds its own venv and Python (3.10 for ORPO, 3.12 for ReSFT and vLLM) from a pinned `requirements.txt`. |
| Network access | setup | GitHub, PyPI and Hugging Face. The evaluation setup clones the upstream benchmarks at pinned commits. Export `HTTP_PROXY` / `HTTPS_PROXY` if you are behind a proxy. |
| [Qwen3-8B](https://huggingface.co/Qwen/Qwen3-8B) | ReSFT | Base model; pass its local path as `MODEL_PATH`. |
| Agent-Reflex-data | ReSFT, ORPO | Training data, see [Data](#-data). |
| **Boyue API key** | evaluation | User simulator (`gpt-4.1`) and judge (`claude-sonnet-4-6`) for every benchmark except BFCL. See below. |
| **Serper API key** | evaluation | BFCL V4 web-search category only. Register at [serper.dev](https://serper.dev) and copy the API key from the dashboard. |

**Getting the Boyue key.** Boyue is an OpenAI-compatible API gateway. Register at [api.boyuerichdata.opensphereai.com](https://api.boyuerichdata.opensphereai.com) (docs: [boyuerichdata.apifox.cn](https://boyuerichdata.apifox.cn/)), open the **API令牌 (API tokens)** page and create a token in the `auto` group. The key is a string that starts with `sk-`. Paste it into `evaluation/.env`, the only file the evaluation scripts read credentials from:

```bash
cd evaluation && cp .env.example .env
# edit evaluation/.env:
BOYUE_API_KEY=sk-xxxxxxxx
BOYUE_API_BASE_URL=http://35.220.164.252:3888/v1   # outside CN/HK: https://api.boyuerichdata.opensphereai.com/v1
SERPER_API_KEY=xxxxxxxx
```

`.env` is git-ignored. Training needs no API keys.

## 🧩 Framework

Real interaction is not clean: tools time out, permissions fail, and users correct the agent mid-task. Agent-Reflex trains the agent for that regime in three stages.

<p align="center"><img src="assets/rsd_resft.jpg" width="100%"></p>

**Stage 1 · RSD** perturbs tool returns of executable environments with mined failure families, samples a capability-diverse LLM pool, and summarizes matched success / failure pairs into an offline skill library.
**Stage 2 · ReSFT** samples local-repair, global-restart and user-correction continuations from failed trajectories and keeps only verifier-validated ones.

<p align="center"><img src="assets/orpo.jpg" width="100%"></p>

**Stage 3 · ORPO** re-scores the same sampled tokens with the environment's skill in context and pulls the policy towards skill-endorsed tokens, gated by confidence, alongside the outcome-based RL objective.

## 📊 Results

Benchmark averages on Qwen3-8B (full breakdown in the paper):

| Method | VitaBench | τ²-Bench | BFCL V4 | ACEBench | ToolSandbox | **Overall** | AgentNoiseBench |
| --- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| Qwen3-8B | 11.4 | 26.2 | 40.4 | 54.0 | 69.1 | 40.2 | 12.3 |
| Reflexion | 6.8 | 34.5 | 42.7 | 64.0 | 75.4 | 44.7 | 13.7 |
| EnvScaler-8B | 15.8 | 37.9 | 47.6 | 60.0 | 80.5 | 48.4 | 17.6 |
| **Agent-Reflex** | **17.5** | **54.9** | **48.9** | **76.0** | **81.8** | **55.8** | **21.4** |

<details>
<summary><b>Full tables and the RL algorithm comparison</b></summary>

<p align="center"><img src="assets/main_results.png" width="100%"></p>
<p align="center"><img src="assets/agentnoisebench.png" width="100%"></p>
<p align="center"><img src="assets/orpo_vs_rl.png" width="100%"></p>

</details>

## 🗂️ Repository

```
Agent-Reflex/
├── RSD/             🪞 Stage 1 · the reflection meta-skill library (1,170 skills)
├── LLaMA-Factory/   📘 Stage 2 · ReSFT recipe and launch scripts
├── ORPO/            🎯 Stage 3 · verl-based ORPO: noisy rollouts + skill-guided OPD
├── evaluation/      📊 τ²-Bench, BFCL V4, ACEBench, VitaBench, AgentNoiseBench, ToolSandbox
└── assets/          🖼️ figures used in this README
```

| Folder | What you get | Start here |
| --- | --- | --- |
| [`RSD/`](RSD) | 557 MCP-anchored environments with tools, bad patterns and 1,170 reflection meta-skills | [README](RSD/README.md) |
| [`LLaMA-Factory/`](LLaMA-Factory) | ReSFT on Qwen3-8B: full fine-tuning, ZeRO-3, 3 epochs, 5,127 steps | [README](LLaMA-Factory/README.md) · [reproduce](LLaMA-Factory/reproduce_skills.md) |
| [`ORPO/`](ORPO) | ORPO from the ReSFT checkpoint: 1 × 8 GPUs, 200 updates | [README](ORPO/README.md) · [reproduce](ORPO/reproduce_skills.md) |
| [`evaluation/`](evaluation) | one folder per benchmark, official settings, vLLM serving | [README](evaluation/README.md) · [reproduce](evaluation/reproduce_skills.md) |

## 🚀 Quick Start

Each part has its own environment, built with [uv](https://github.com/astral-sh/uv) (`pip install uv`). Download the training data first (see [Data](#-data)).

**ReSFT**

```bash
cd LLaMA-Factory && bash setup_env.sh
NNODES=2 NODE_RANK=<0|1> MASTER_ADDR=<node0> MODEL_PATH=/path/to/Qwen3-8B \
  bash scripts/run_resft_qwen3_8b.sh
```

**ORPO**

```bash
cd ORPO && bash setup_env.sh
python scripts/prepare_init_checkpoint.py /path/to/checkpoint-5127 --apply
MODEL_PATH=/path/to/checkpoint-5127 bash scripts/run_orpo_qwen3_8b.sh
```

**Evaluation** (full task sets, official settings; fill in `evaluation/.env` first, see [Dependencies](#-dependencies))

```bash
cd evaluation
bash shared/setup_vllm.sh
for b in Tau2 BFCL-v4 ACEBench VitaBench AgentNoiseBench ToolSandbox; do bash $b/setup.sh; done
MODEL_PATH=/path/to/checkpoint RUN_NAME=agent-reflex bash run_all.sh
```

## 📦 Data

| Resource | Size | Where | Put it at |
| --- | --- | --- | --- |
| RSD skill library | 11 MB | this repo | `RSD/environment_skills.jsonl` |
| ReSFT data (54,663 trajectories) | 2.6 GB | **Agent-Reflex-data** · *link coming soon* | `LLaMA-Factory/data/agent_reflex_resft/` |
| ORPO training tasks (2,550, with skills) | 152 MB | **Agent-Reflex-data** · *link coming soon* | `ORPO/data/` |
| Evaluation data | 115 MB | this repo | each `evaluation/<Bench>/data/` |

## 🙏 Acknowledgements

Agent-Reflex builds on [verl](https://github.com/volcengine/verl), [LLaMA-Factory](https://github.com/hiyouga/LLaMA-Factory), [EnvScaler](https://github.com/RUC-NLPIR/EnvScaler), [Agent-World](https://github.com/RUC-NLPIR/Agent-World), [tau2-bench](https://github.com/sierra-research/tau2-bench), [BFCL](https://github.com/ShishirPatil/gorilla), [VitaBench](https://github.com/meituan-longcat/vitabench), [ToolSandbox](https://github.com/apple/ToolSandbox) and AgentNoiseBench. Thanks to their authors.

## 📄 License

Agent-Reflex code and the RSD skill library are released under the [MIT License](LICENSE). Vendored components keep their own licenses: `ORPO/` (verl) and `LLaMA-Factory/` are Apache-2.0.

## 📚 Citation

```bibtex
@article{agentreflex2026,
  title  = {Agent-Reflex: Teaching Language Agents to Act Reflectively},
  author = {Anonymous},
  year   = {2026}
}
```
