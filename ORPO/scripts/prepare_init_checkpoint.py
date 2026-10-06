#!/usr/bin/env python3
"""Make a ReSFT checkpoint loadable by the ORPO training stack.

ReSFT (LLaMA-Factory, transformers 5.x) saves two things that transformers 4.54
(the ORPO environment) misreads:

* the RoPE base under ``rope_parameters.rope_theta`` and the dtype under
  ``dtype``. transformers 4.54 ignores both and falls back to Qwen3Config's
  class default ``rope_theta=10000`` -- a 100x error that silently destroys the
  policy instead of crashing;
* ``extra_special_tokens`` as a list, which the 4.54 tokenizer loader rejects.

The legacy keys are written next to the new ones, so the checkpoint stays valid
for both versions. Without ``--apply`` the script only reports.

    python scripts/prepare_init_checkpoint.py /path/to/checkpoint-5127 --apply
"""

import argparse
import json
import os
import shutil


def _load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _write(path, obj):
    backup = path + ".orig"
    if not os.path.exists(backup):
        shutil.copy2(path, backup)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def config_fixes(cfg: dict) -> dict:
    fixes = {}
    rope = cfg.get("rope_parameters")
    if cfg.get("rope_theta") is None and isinstance(rope, dict) and rope.get("rope_theta") is not None:
        fixes["rope_theta"] = rope["rope_theta"]
    if cfg.get("torch_dtype") is None and cfg.get("dtype") is not None:
        fixes["torch_dtype"] = cfg["dtype"]
    return fixes


def tokenizer_fixes(tok: dict) -> dict:
    special = tok.get("extra_special_tokens")
    if isinstance(special, list):
        return {"extra_special_tokens": {t: t for t in special}}
    return {}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("checkpoints", nargs="+")
    parser.add_argument("--apply", action="store_true", help="write the fixes (default: report only)")
    args = parser.parse_args()

    for ckpt in args.checkpoints:
        for name, fix in (("config.json", config_fixes), ("tokenizer_config.json", tokenizer_fixes)):
            path = os.path.join(ckpt, name)
            if not os.path.exists(path):
                print(f"SKIP  {path} (missing)")
                continue
            obj = _load(path)
            fixes = fix(obj)
            if not fixes:
                print(f"OK    {path}")
                continue
            print(f"{'PATCH' if args.apply else 'NEEDS'} {path}: {sorted(fixes)}")
            if args.apply:
                obj.update(fixes)
                _write(path, obj)


if __name__ == "__main__":
    main()
