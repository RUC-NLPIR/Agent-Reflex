---
name: reproduce-resft
description: Reproduce the Agent-Reflex ReSFT checkpoint (Qwen3-8B full SFT, 5127 steps) with LLaMA-Factory. Use when training, smoke-testing or checking the SFT stage.
---

# Reproduce ReSFT

## Steps

1. **Environment**: `bash setup_env.sh` → `.venv` (Python 3.12, torch 2.6.0,
   transformers 5.8, DeepSpeed 0.19, flash-attn 2.7.4, Liger 0.8).
   If the flash-attn wheel cannot be downloaded, set `FLASH_ATTN_WHEEL` to a
   local copy.
2. **Data**: already in `data/agent_reflex_resft/train/` (54,663 rows,
   registered as `agent_reflex_resft` in `data/dataset_info.json`).
3. **Smoke test** (1 × 8 GPUs, ~15 min including tokenization):
   `MODEL_PATH=<Qwen3-8B> bash scripts/run_resft_smoke.sh`.
   Pass criterion: 5 logged steps with a finite, decreasing `loss`.
4. **Paper run** (2 × 8 GPUs): on each node
   `NNODES=2 NODE_RANK=<0|1> MASTER_ADDR=<node0> MODEL_PATH=<Qwen3-8B> bash scripts/run_resft_qwen3_8b.sh`.
   It must report `Total optimization steps = 5,127`.
5. Hand `saves/qwen3-8b-agent-reflex-resft/checkpoint-5127` to ORPO after
   `../ORPO/scripts/prepare_init_checkpoint.py --apply`.

## Pitfalls

- Keep the global batch at 32 (GPUs × per-device batch × gradient
  accumulation); otherwise the step count and the learning-rate schedule change.
- Overrides use OmegaConf syntax and YAML typing: write `"save_strategy='no'"`,
  not `save_strategy=no` (that becomes the boolean `False`).
- Tokenizing 54k rows at 32k context takes a while; it is cached under
  `~/.cache/huggingface/datasets` unless `overwrite_cache: true` (the recipe
  default, so a changed dataset is never silently reused).
- Build the venv on storage the compute nodes mount (the uv-managed Python
  is placed next to it by `setup_env.sh`).
