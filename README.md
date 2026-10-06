# Agent-Reflex: Teaching Language Agents to Act Reflectively

Agent-Reflex is a training framework that teaches tool-using LLM agents to
notice failures (noisy tool returns, user corrections) and recover from them.
It treats reflection as a learnable meta-skill: skills are mined from
execution failures in executable environments (RSD) and then internalized
into the policy in two training stages (ReSFT, then ORPO).

1. **Environment Reflection Skill Discovery (RSD, data).** 500 database-backed
   executable environments with tool-return perturbations derived from real
   tool errors. Trajectories from a diverse LLM pool are paired into matched
   success / failure contrasts and summarized into 1,170 reflection
   meta-skills.
2. **Reflective Supervised Fine-Tuning (ReSFT).** The skills are turned into
   verifier-validated Self-Reflection, Skill-Recovery and User-Centric
   Reflection data (54,663 trajectories), then distilled into Qwen3-8B by
   full fine-tuning.
3. **On-Policy Reflective Policy Optimization (ORPO).** GRPO on mixed groups
   of clean and fault-injected rollouts, plus a reflection on-policy
   distillation term: the same sampled tokens are re-scored with the
   environment's skill card in context, and a confidence-weighted objective
   pulls the policy towards the skill-endorsed tokens.

This repository ships the RSD skill library, both training stages and the
evaluation suite:

```
Agent-Reflex/
├── RSD/             # Stage 1 output: 1,170 reflection meta-skills of the MCP-anchored environments
├── LLaMA-Factory/   # Stage 2: ReSFT recipe, data and launch scripts
├── ORPO/            # Stage 3: verl-based ORPO training, data and launch scripts
└── evaluation/      # τ²-bench, BFCL v4, ACEBench, VitaBench, AgentNoiseBench, ToolSandbox
```

Each directory has its own `README.md`; the training and evaluation
directories also have a `reproduce_skills.md` with step-by-step reproduction
notes and known pitfalls.

## Reflection skill library

[`RSD/environment_skills.jsonl`](RSD/environment_skills.jsonl) releases the
**1,170 reflection meta-skills** mined by RSD. They cover 557 environments
anchored on real MCP servers (537 of them have skills; 8,856 tools in total).
Each environment lists the bad patterns observed in failed rollouts and the
skills that repair them:

> **Logseq Tools** · *bad pattern*: treats the summary returned by
> `getAllPages` as the final answer without reading details or further
> pages, so matches are missed.
> *skills*: (1) narrow the query, then call `getAllPages`; (2) read details,
> pages or counts and check IDs, timestamps and status; (3) do not take a hit
> count or summary as the full result.

Schema, statistics and a loading snippet: [RSD/README.md](RSD/README.md).

## Quick start

The three parts have separate environments, built with
[uv](https://github.com/astral-sh/uv) (`pip install uv`):

| Part | Python | Main stack |
| --- | --- | --- |
| `LLaMA-Factory/` | 3.12 | torch 2.6.0, transformers 5.8, DeepSpeed 0.19 |
| `ORPO/` | 3.10 | torch 2.7.1, verl 0.5, SGLang |
| `evaluation/` | 3.12 (vLLM), per-bench venvs | vLLM 0.27.1 |

Build them on storage that your GPU nodes mount; each setup script also puts
a uv-managed Python interpreter there, so the environments work on nodes
without a system Python.

### 1. ReSFT (LLaMA-Factory)

```bash
cd LLaMA-Factory
bash setup_env.sh
# Paper run: 2 nodes x 8 GPUs, 3 epochs, 5,127 steps. Run on each node:
NNODES=2 NODE_RANK=<0|1> MASTER_ADDR=<node0> MODEL_PATH=/path/to/Qwen3-8B \
  bash scripts/run_resft_qwen3_8b.sh
# Smoke test on one node: 5 steps.
MODEL_PATH=/path/to/Qwen3-8B bash scripts/run_resft_smoke.sh
```

Details: [LLaMA-Factory/README.md](LLaMA-Factory/README.md).

### 2. ORPO (verl)

```bash
cd ORPO
bash setup_env.sh
python scripts/prepare_init_checkpoint.py /path/to/resft/checkpoint-5127 --apply
# Paper run: 1 node x 8 GPUs, 200 updates.
MODEL_PATH=/path/to/resft/checkpoint-5127 bash scripts/run_orpo_qwen3_8b.sh
# Smoke test: 2 updates.
MODEL_PATH=/path/to/resft/checkpoint-5127 bash scripts/run_orpo_smoke.sh
```

Details: [ORPO/README.md](ORPO/README.md).

### 3. Evaluation

```bash
cd evaluation
cp .env.example .env     # fill in BOYUE_API_KEY (user simulator / judge) and SERPER_API_KEY (BFCL web search)
bash shared/setup_vllm.sh && bash Tau2/setup.sh     # and the other <Bench>/setup.sh
MODEL_PATH=/path/to/checkpoint bash shared/serve_vllm.sh
RUN_NAME=agent-reflex bash Tau2/run.sh
```

The one key in `evaluation/.env` serves every external model the benches
need (`gpt-4.1` user simulator, `claude-sonnet-4-6` VitaBench judge, the
AgentNoiseBench noise generator). Protocol, per-bench settings and data
sources: [evaluation/README.md](evaluation/README.md).

## Training recipes at a glance

| Stage | Base | Data | Hardware | Key settings |
| --- | --- | --- | --- | --- |
| ReSFT | Qwen3-8B | 54,663 RSD trajectories | 2 × 8 GPUs | full FT, ZeRO-3, lr 7e-6, global batch 32, 3 epochs, 32k context |
| ORPO | ReSFT ckpt-5127 | 2,550 EnvScaler RL tasks + 51 environment skills | 1 × 8 GPUs | GRPO, 64 × 8 rollouts, ν = 0.25, fault rate 0.2, λ_opd = 0.01, β_opd = 5, lr 1e-6, 200 updates |

## Evaluation suite

| Benchmark | Tasks | Metric | Agent temperature |
| --- | --- | --- | --- |
| τ²-bench | 278 (airline, retail, telecom) | average reward | 0.0 |
| BFCL v4 | 5,217 (`all_scoring`) | official overall accuracy | 0.001 |
| ACEBench (agent) | 50 | average reward | 0.7 |
| VitaBench | 400 (4 domains) | pass@1 | 0.0 |
| AgentNoiseBench | τ²-bench and VitaBench under tool and user noise | clean / tool / user reward | as the base bench |
| ToolSandbox | 200 offline scenarios | milestone similarity | 0.6 (top-p 0.95, top-k 20) |

All benches run against a local vLLM server (tensor parallel 8, native
function calling, thinking on, 40,960-token context) with `gpt-4.1` as the
user simulator, under each harness's official settings.

## Verified

Every launcher in this repository was run end to end on one 8 × H200 node:

* **ReSFT smoke**: 5 steps on 256 samples, loss 1.29 → 1.24.
* **ORPO smoke**: 2 updates with noisy rollouts (ν = 0.25) and OPD active.
* **Evaluation smoke** (Qwen3-8B, 5 tasks per bench, BFCL `simple_python` +
  `multi_turn_base`): all six benches report `PASS`.

These checks confirm that the pipelines run; reproducing the paper numbers
needs the full runs above.

## Acknowledgements

This project builds on [verl](https://github.com/volcengine/verl),
[LLaMA-Factory](https://github.com/hiyouga/LLaMA-Factory),
[EnvScaler](https://github.com/RUC-NLPIR/EnvScaler) (RL environments and
the ACEBench harness),
[tau2-bench](https://github.com/sierra-research/tau2-bench),
[BFCL](https://github.com/ShishirPatil/gorilla),
[VitaBench](https://github.com/meituan-longcat/vitabench),
[ToolSandbox](https://github.com/apple/ToolSandbox) and AgentNoiseBench. The
layout follows [ARPO](https://github.com/RUC-NLPIR/ARPO).

## License

Agent-Reflex code and the RSD skill library are released under the
[MIT License](LICENSE). Vendored components keep their original licenses:
`ORPO/` (verl) and `LLaMA-Factory/` are Apache-2.0, see the `LICENSE` file
in each directory.

## Citation

```bibtex
@article{agentreflex2026,
  title  = {Agent-Reflex: Teaching Language Agents to Act Reflectively},
  author = {Anonymous},
  year   = {2026}
}
```
