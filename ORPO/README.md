# ORPO: On-Policy Reflective Policy Optimization

ORPO is the reinforcement-learning stage of Agent-Reflex. It starts from the
ReSFT checkpoint (see [`../LLaMA-Factory`](../LLaMA-Factory)) and trains the
policy on EnvScaler tool-use environments with two additions to GRPO:

1. **Noisy agentic rollouts.** In every GRPO group, a fraction
   `ν = noise_rollout_fraction` of the rollouts is executed with per-tool-call
   faults injected at probability `noise_rate`. Faults are sampled from eight
   families: `timeout`, `rate_limit`, `auth_permission`, `not_found`,
   `invalid_input`, `server_unavailable`, `connection` and `execution_failure`.
   Clean and perturbed rollouts share one advantage normalization, so the
   policy is rewarded for recovering from faults instead of avoiding them.
2. **Reflection on-policy distillation (OPD).** Each sampled trajectory is
   re-scored by the same model with the environment's offline RSD skill
   inserted into the system prompt. The skill-conditioned log-probs act as a
   teacher in a confidence-gated distillation term:

   ```
   Δ = sg[ℓ_skill − ℓ_θ],   g = σ(β_opd · Δ),   L_opd = E[ m · g · (sg[ℓ_skill] − ℓ_θ) ]
   L = L_GRPO + λ_kl · KL + λ_opd · L_opd
   ```

   With `opd_gate_beta <= 0` the gate is dropped (plain OPSD). With
   `opd_loss_coef = 0` OPD is off.

The code is a self-contained copy of [verl](https://github.com/volcengine/verl)
0.5 (FSDP actor, SGLang async multi-turn rollout) plus the
`recipe/envscaler_openai_fc` recipe.

## Layout

```
ORPO/
├── setup_env.sh                  # build the training environment (Python 3.10, torch 2.7.1 + cu128)
├── requirements.txt
├── scripts/
│   ├── train_orpo.sh             # full launcher; every knob is an env var
│   ├── run_orpo_qwen3_8b.sh      # paper setting (200 updates, 1x8 GPUs)
│   ├── run_orpo_smoke.sh         # 2 updates, no validation / checkpoint
│   ├── preflight.py              # checks model, data and prompt lengths before launch
│   └── prepare_init_checkpoint.py# makes a transformers-5 ReSFT checkpoint loadable here
├── recipe/envscaler_openai_fc/
│   ├── agent_loop.py             # OpenAI-FC multi-turn agent loop, clean/noisy group split
│   ├── tool_fault_injection.py   # the eight fault families and their templates
│   ├── skill_context.py          # inserts an RSD skill into the system prompt
│   ├── skill_rescoring.py        # builds the skill-conditioned teacher batch
│   ├── tool_execution.py, adapters/   # EnvScaler environment execution and reward
│   └── data/                     # scripts that rebuilt the shipped data
├── data/
│   ├── train_envscaler_2550_with_skills.jsonl   # 2,550 training tasks with attached skills
│   ├── bfcl_val_128.jsonl                       # 128-task validation split
│   └── environment_skills_envscaler.jsonl       # 51 environment-level RSD skills
├── verl/                         # verl 0.5 with the ORPO changes below
└── tests/
```

### Changes to verl

| File | Change |
| --- | --- |
| `verl/trainer/ppo/core_algos.py` | `compute_opd_loss`: confidence-gated OPD term |
| `verl/workers/actor/dp_actor.py` | adds `opd_loss_coef · L_opd` to the policy loss and logs `actor/opd_*` |
| `verl/trainer/ppo/ray_trainer.py` | after rollout, builds the skill teacher batch and computes teacher log-probs with the reference worker |
| `verl/workers/config/{actor,rollout}.py`, `verl/trainer/config/` | `opd_loss_coef`, `opd_gate_beta`, `noise_rollout_fraction`, `noise_rate`, `noise_adv_split`, `noise_catalog_path` |

## Environment

```bash
cd ORPO
bash setup_env.sh              # creates .venv (override with ENV_DIR=...)
source .venv/bin/activate
```

`setup_env.sh` installs torch 2.7.1 (cu128), SGLang, flash-attn and this
package in editable mode. On a machine without GPUs the final import check
only reports versions, so the environment can be built on a CPU login node.
Behind a proxy, export `HTTP_PROXY` / `HTTPS_PROXY` first. If your pip mirror
does not carry the CUDA wheels, `setup_env.sh` also reads `TORCH_INDEX_URL`.

Weights & Biases is optional: copy `.env.example` to `.env` and set
`WANDB_API_KEY`, then run with `LOGGER='[console,wandb]'`.

## Initial checkpoint

ORPO starts from the ReSFT checkpoint. LLaMA-Factory saves it with
transformers 5.x, whose config layout transformers 4.54 (used here) silently
misreads (the RoPE base falls back to 10000). Convert it once:

```bash
python scripts/prepare_init_checkpoint.py /path/to/resft/checkpoint-5127 --apply
```

The script only adds the legacy keys next to the new ones, so the checkpoint
stays valid for both versions. `preflight.py` refuses to start on an
unconverted checkpoint.

## Training

```bash
# Paper setting: Qwen3-8B ReSFT checkpoint, one node with 8 GPUs, 200 updates.
MODEL_PATH=/path/to/resft/checkpoint-5127 bash scripts/run_orpo_qwen3_8b.sh

# Smoke test: 2 updates, about 30 minutes on 8 GPUs.
MODEL_PATH=/path/to/Qwen3-8B bash scripts/run_orpo_smoke.sh

# Resume an interrupted run.
MODEL_PATH=... bash scripts/run_orpo_qwen3_8b.sh trainer.resume_mode=auto
```

Any Hydra override can be appended to the command line. Checkpoints go to
`checkpoints/<EXP_NAME>` (`CKPT_DIR` to change).

### Hyper-parameters

| Variable | Default | Meaning |
| --- | --- | --- |
| `TRAIN_BATCH_SIZE` / `ROLLOUT_N` | 64 / 8 | tasks per update / rollouts per task |
| `ACTOR_LR` | 1e-6 | actor learning rate |
| `KL_COEF` | 0.01 | low-variance KL loss to the reference policy |
| `NOISE_ROLLOUT_FRACTION` | 0.25 | ν, fraction of each group rolled out with faults |
| `NOISE_RATE` | 0.2 | per-tool-call fault probability inside a noisy rollout |
| `NOISE_ADV_SPLIT` | False | normalize advantages over the whole mixed group |
| `OPD_LOSS_COEF` | 0.01 | λ_opd |
| `OPD_GATE_BETA` | 5.0 | β_opd of the confidence gate |
| `MAX_PROMPT_LENGTH` / `MAX_RESPONSE_LENGTH` | 8192 / 16384 | token budgets |
| `MAX_ASSISTANT_TURNS` | 40 | turns per trajectory |
| `ROLLOUT_TEMPERATURE` / `ROLLOUT_TOP_P` | 0.99 / 0.99 | sampling during training |
| `TP_SIZE` / `GPU_MEMORY_UTILIZATION` | 4 / 0.45 | SGLang rollout engine |
| `TOTAL_TRAINING_STEPS` / `SAVE_FREQ` / `TEST_FREQ` | 200 / 20 / 10 | schedule |

Useful metrics: `critic/score/mean` (training reward),
`val-core/.../reward/mean@1` (BFCL validation), `actor/opd_loss`,
`actor/opd_active_frac` and `actor/opd_gate_mean`.

### Export to Hugging Face format

```bash
python -m verl.model_merger merge --backend fsdp \
  --local_dir checkpoints/orpo_qwen3_8b/global_step_200/actor \
  --target_dir checkpoints/orpo_qwen3_8b/hf_step_200
```

The merged directory is what [`../evaluation`](../evaluation) serves.

## Data

The shipped files are ready to train on. The scripts in
`recipe/envscaler_openai_fc/data/` document how they were built:
`build_envscaler_train.py` (EnvScaler tasks to OpenAI-FC prompts),
`build_envscaler_skill_catalog.py` and `attach_environment_skills.py` (attach
the RSD skill of each environment), `build_bfcl_val.py` (validation split) and
`validate_data.py` (schema check).

## Tests

```bash
pytest tests/envscaler_openai_fc tests/trainer/ppo/test_opd_loss.py
```
