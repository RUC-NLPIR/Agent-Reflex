---
name: reproduce-orpo
description: Reproduce Agent-Reflex ORPO (noisy agentic RL + reflection OPD) on Qwen3-8B with verl. Use when training or debugging the ORPO stage.
---

# Reproduce ORPO

## Steps

1. **Environment** (CPU node is fine):
   `bash setup_env.sh` → `.venv` with Python 3.10, torch 2.7.1+cu128, SGLang,
   flash-attn. Behind a proxy export `HTTP_PROXY`/`HTTPS_PROXY` first.
2. **Initial checkpoint**: ReSFT `checkpoint-5127` from `../LLaMA-Factory`.
   Run `python scripts/prepare_init_checkpoint.py <ckpt> --apply` once.
3. **Paper run**: `MODEL_PATH=<ckpt> bash scripts/run_orpo_qwen3_8b.sh`
   (200 updates, batch 64 × 8 rollouts, ν = 0.25, noise rate 0.2,
   λ_opd = 0.01, β_opd = 5.0, lr 1e-6, KL 0.01).
4. **Export**: `python -m verl.model_merger merge --backend fsdp --local_dir <ckpt>/global_step_N/actor --target_dir <hf_dir>`,
   then evaluate with `../evaluation`.

## Pitfalls

- A transformers-5 checkpoint loaded without step 2 silently gets
  `rope_theta=10000` and the policy collapses; `preflight.py` blocks this.
- Build the venv on storage that compute nodes mount. `setup_env.sh` puts
  the uv-managed interpreter next to the venv for that reason; a venv that
  links to `/usr/bin/python3.x` of the build machine fails on the node.
- `data.truncation=error` is intentional: a prompt over
  `MAX_PROMPT_LENGTH` (8192) is a data bug, not something to truncate.
- `OPD_LOSS_COEF=0` gives the noisy-RL-only ablation;
  `NOISE_ROLLOUT_FRACTION=0` gives the OPD-only ablation; both 0 is GRPO.
- Validation (`TEST_FREQ`) runs the 128 BFCL tasks greedily (temperature 0,
  one sample) and reports `val-core/.../reward/mean@1`.
- Resume with `trainer.resume_mode=auto` and the same `EXP_NAME`.
