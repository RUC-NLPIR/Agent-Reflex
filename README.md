<div align="center">

<img src="assets/cover.gif" alt="Agent-Reflex" width="100%">

# 🪞 Agent-Reflex

### Teaching Language Agents to Act Reflectively

##### If you like our project, please give us a star ⭐ on GitHub for the latest update.

[![Paper](https://img.shields.io/badge/Paper-arXiv-b5212f.svg?logo=arxiv)](https://arxiv.org/abs/XXXX.XXXXX)
[![Model](https://img.shields.io/badge/🤗%20Model-Agent--Reflex--8B-ffc107.svg)](https://huggingface.co/dongguanting/Agent-Reflex-8B)
[![SFT Data](https://img.shields.io/badge/🤗%20SFT%20Data-54K-ffc107.svg)](https://huggingface.co/datasets/dongguanting/Agent-Reflex-SFT-54K)
[![RL Data](https://img.shields.io/badge/🤗%20RL%20Data-2K-ffc107.svg)](https://huggingface.co/datasets/dongguanting/Agent-Reflex-RL-2K)
[![Skills](https://img.shields.io/badge/RSD%20Skills-1%2C170-f7be50.svg)](RSD)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

*A training framework that elicits **proactive reflection** in tool-using LLM agents: noticing noisy tool feedback and user corrections, and recovering from them.*

[Overview](#-overview) · [Framework](#-agent-reflex-framework) · [Results](#-benchmarks--results) · [Installation](#-installation) · [Data](#-data) · [Quick Start](#-quick-start) · [Citation](#-citation)

</div>

## 📣 News

* **[2026-10]** 🚀 Released the full codebase (RSD skill library, ReSFT, ORPO, evaluation), the **Agent-Reflex-8B** checkpoint and the **SFT / RL datasets** on 🤗 Hugging Face.

## 💡 Overview

<p align="center"><img src="assets/motivation.jpg" width="100%"></p>

LLM agents are moving from single-turn chat to long-horizon tool use, but most scalable training environments assume **idealized interaction**: a fixed task and clean, deterministic tool feedback. Real deployment is different. Tool services time out, reject permissions or return malformed results, and users step in with corrections at any turn. Under noise, agents that look strong on clean benchmarks degrade sharply (panel c), and the recorded tool errors fall into a small set of recurring families (panel d).

**Agent-Reflex** is a general training framework that incentivizes **proactive reflective thinking** in agents. It mines reusable reflection meta-skills from noisy environments, distills them into supervised data, and reinforces them with noisy agentic RL, so that the agent learns to notice what went wrong and recover on its own. On Qwen3-8B it improves six challenging agent benchmarks and stays robust under noise, with stable training dynamics.

## ✨ Agent-Reflex Framework

<p align="center"><img src="assets/rsd_resft.jpg" width="100%"></p>
<p align="center"><img src="assets/orpo.jpg" width="100%"></p>

* **Stage 1 · Environment Reflection Skill Discovery (RSD).** RSD injects empirically grounded tool-return perturbations (eight failure families) into scaled executable environments, samples a capability-diverse LLM pool to mine matched success / failure pairs, and summarizes them into an offline library of **1,170 reusable reflection meta-skills** over 557 MCP-anchored environments.
* **Stage 2 · Reflective Supervised Fine-Tuning (ReSFT).** Each skill is turned into three kinds of supervision at complementary levels: self-reflection (local repair), skill-guided recovery (global restart) and user-centric correction. Only verifier-validated continuations are kept, giving **54,663** trajectories.
* **Stage 3 · On-Policy Reflective Policy Optimization (ORPO).** ORPO mixes clean and fault-injected rollouts in one GRPO group and adds reflection-guided on-policy distillation: the sampled tokens are re-scored with the environment's skill in context, and the policy is pulled towards skill-endorsed tokens, gated by confidence. Skills are used only during training; the deployed agent is skill-free.

## 📊 Benchmarks & Results

We evaluate on six agent benchmarks under each benchmark's official metric:

* **General Function Calling:**
  * [BFCL V4](https://gorilla.cs.berkeley.edu/leaderboard.html) ([paper](https://proceedings.mlr.press/v267/patil25a.html)): the Berkeley Function Calling Leaderboard extended to agentic evaluation (web search, memory, multi-turn, live / non-live, irrelevance); 5,217 tasks.
  * [ACEBench](https://arxiv.org/abs/2501.12851): normal, special and agentic tool use, emphasizing when to call a tool and how to handle underspecified requests.
  * [ToolSandbox](https://arxiv.org/abs/2408.04682): stateful, conversational tool use with implicit state dependencies, an LLM user simulator and deliberately unsolvable tasks; 200 offline scenarios.
* **Long-Horizon Interactive Workflows:**
  * [τ²-Bench](https://arxiv.org/abs/2506.07982): dual-control airline, retail and telecom domains where agent and user both act on shared state under a policy document.
  * [VitaBench](https://arxiv.org/abs/2509.26490): delivery, in-store and OTA domains plus cross-scenario tasks spanning domains within one episode.
* **Noisy Interaction:**
  * [AgentNoiseBench](https://arxiv.org/abs/2602.11348): tool-side and user-side perturbations injected into τ²-Bench and VitaBench environments.

On Qwen3-8B, Agent-Reflex reaches **55.8** Overall on the five long-horizon tool-use benchmarks (+15.6 over the backbone, +7.4 over EnvScaler-8B) and leads every 8B method on AgentNoiseBench:

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

## 🔧 Installation

### Environment Setup

Each part has its own environment, built by one script with [uv](https://github.com/astral-sh/uv) (`pip install uv`) from a pinned `requirements.txt`:

| Part | Python | Core packages | Setup |
| --- | :---: | --- | --- |
| ReSFT | 3.12 | torch 2.6.0 (cu124), transformers 5.8, DeepSpeed 0.19, flash-attn 2.7.4, Liger 0.8 | `bash LLaMA-Factory/setup_env.sh` |
| ORPO | 3.10 | torch 2.7.1 (cu128), verl 0.5, SGLang 0.4.10.post2, transformers 4.54.1, Ray 2.57, flash-attn 2.8.3 | `bash ORPO/setup_env.sh` |
| Model serving | 3.12 | vLLM 0.27.1 | `bash evaluation/shared/setup_vllm.sh` |
| Benchmarks | 3.10 / 3.12 | one venv per benchmark; upstream code cloned at pinned commits | `bash evaluation/<Bench>/setup.sh` |

* **Hardware**: NVIDIA 80 GB GPUs with a driver supporting CUDA 12.8. ReSFT uses 2 × 8 GPUs; ORPO and evaluation use 1 × 8.
* **Network**: the setup scripts need GitHub, PyPI and Hugging Face. Behind a proxy, export `HTTP_PROXY` / `HTTPS_PROXY` first.

### API Configuration

Training needs no API keys. Evaluation reads them from `evaluation/.env` (git-ignored):

```bash
cp evaluation/.env.example evaluation/.env
# then edit evaluation/.env:
BOYUE_API_KEY=sk-xxxxxxxx
BOYUE_API_BASE_URL=http://35.220.164.252:3888/v1   # outside CN/HK: https://api.boyuerichdata.opensphereai.com/v1
SERPER_API_KEY=xxxxxxxx
```

* `BOYUE_API_KEY`: the user simulator (`gpt-4.1`) and judge (`claude-sonnet-4-6`) for every benchmark except BFCL. Register at [Boyue API](https://api.boyuerichdata.opensphereai.com) ([docs](https://boyuerichdata.apifox.cn/)), open the **API令牌 (API tokens)** page and create a token in the `auto` group; the key starts with `sk-`.
* `SERPER_API_KEY`: BFCL V4 web search only, from [serper.dev](https://serper.dev).

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
| [`ORPO/`](ORPO) | ORPO from the ReSFT checkpoint on 1 × 8 GPUs | [README](ORPO/README.md) · [reproduce](ORPO/reproduce_skills.md) |
| [`evaluation/`](evaluation) | one folder per benchmark, official settings, vLLM serving | [README](evaluation/README.md) · [reproduce](evaluation/reproduce_skills.md) |

## 📦 Data

| **Resource** | **Size** | **Download** | **Put it at** |
| --- | --- | --- | --- |
| Agent-Reflex-8B (Qwen3-8B, ReSFT + ORPO) | 16 GB | [🤗 HuggingFace](https://huggingface.co/dongguanting/Agent-Reflex-8B) | any path, pass as `MODEL_PATH` |
| ReSFT data, 54,663 trajectories | 2.6 GB | [🤗 HuggingFace](https://huggingface.co/datasets/dongguanting/Agent-Reflex-SFT-54K) | `LLaMA-Factory/data/agent_reflex_resft/train/` |
| ORPO tasks, 2,550 with skills | 152 MB | [🤗 HuggingFace](https://huggingface.co/datasets/dongguanting/Agent-Reflex-RL-2K) | `ORPO/data/` |
| RSD skill library, 1,170 skills | 11 MB | this repo | [`RSD/environment_skills.jsonl`](RSD) |
| Evaluation data | 115 MB | this repo | `evaluation/<Bench>/data/` |

```bash
pip install -U huggingface_hub
hf download dongguanting/Agent-Reflex-SFT-54K --repo-type dataset --include "train/*" \
  --local-dir LLaMA-Factory/data/agent_reflex_resft
hf download dongguanting/Agent-Reflex-RL-2K train_envscaler_2550_with_skills.jsonl \
  --repo-type dataset --local-dir ORPO/data
hf download dongguanting/Agent-Reflex-8B --local-dir /path/to/Agent-Reflex-8B
```

## 🚀 Quick Start

### 1. ReSFT

```bash
cd LLaMA-Factory
NNODES=2 NODE_RANK=<0|1> MASTER_ADDR=<node0> MODEL_PATH=/path/to/Qwen3-8B \
  bash scripts/run_resft_qwen3_8b.sh
```

### 2. ORPO

Start from the ReSFT model checkpoint:

```bash
cd ORPO
python scripts/prepare_init_checkpoint.py /path/to/resft_checkpoint --apply
MODEL_PATH=/path/to/resft_checkpoint bash scripts/run_orpo_qwen3_8b.sh
```

### 3. Evaluation

Full task sets under the official settings (fill in `evaluation/.env` first):

```bash
cd evaluation
MODEL_PATH=/path/to/Agent-Reflex-8B RUN_NAME=agent-reflex bash run_all.sh
```

`run_all.sh` serves the model with vLLM and runs all six benchmarks; set `BENCHES="Tau2 BFCL-v4"` to run a subset. Per-benchmark details are in [`evaluation/README.md`](evaluation/README.md).

## 🙏 Acknowledgements

Agent-Reflex builds on [verl](https://github.com/volcengine/verl), [LLaMA-Factory](https://github.com/hiyouga/LLaMA-Factory), [EnvScaler](https://github.com/RUC-NLPIR/EnvScaler), [Agent-World](https://github.com/RUC-NLPIR/Agent-World), [tau2-bench](https://github.com/sierra-research/tau2-bench), [BFCL](https://github.com/ShishirPatil/gorilla), [VitaBench](https://github.com/meituan-longcat/vitabench), [ToolSandbox](https://github.com/apple/ToolSandbox) and [AgentNoiseBench](https://arxiv.org/abs/2602.11348). Thanks to their authors.

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
