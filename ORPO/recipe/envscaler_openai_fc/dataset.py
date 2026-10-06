"""JSON/JSONL dataset that tokenizes each row with its native tool schemas."""

import copy
import json
from pathlib import Path
from typing import Optional

import torch
from omegaconf import DictConfig, ListConfig
from transformers import PreTrainedTokenizer, ProcessorMixin

import verl.utils.torch_functional as verl_F
from verl.utils.model import compute_position_id_with_mask


def load_rows(path: str | Path) -> list[dict]:
    path = Path(path).expanduser()
    if not path.is_file():
        raise FileNotFoundError(f"data file not found: {path}")
    if path.suffix == ".jsonl":
        rows = []
        with open(path, encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, 1):
                if not line.strip():
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise ValueError(
                        f"{path}:{line_number}: invalid JSON: {exc}"
                    ) from exc
        return rows
    if path.suffix == ".json":
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle)
        return value if isinstance(value, list) else [value]
    raise ValueError(f"unsupported data format for {path}; expected .json or .jsonl")


def tools_for_row(row: dict) -> list[dict]:
    source = row.get("data_source")
    extra = row.get("extra_info") or {}
    if source == "envscaler":
        tools = (extra.get("environment") or {}).get("tools")
    elif source == "bfcl":
        tools = extra.get("tools")
    else:
        raise ValueError(
            f"unsupported data_source={source!r}; only envscaler and bfcl routes exist"
        )
    if not isinstance(tools, list) or not tools:
        raise ValueError(f"{source} row has no OpenAI tool schemas")
    return tools


class OpenAIFCToolDataset(torch.utils.data.Dataset):
    """VeRL-compatible text dataset with per-example ``tools=`` tokenization."""

    def __init__(
        self,
        data_files: str | list[str],
        tokenizer: PreTrainedTokenizer,
        config: DictConfig,
        processor: Optional[ProcessorMixin] = None,
    ):
        if not isinstance(data_files, (list, ListConfig)):
            data_files = [data_files]
        if processor is not None:
            raise ValueError("OpenAIFCToolDataset currently supports text-only models")

        self.data_files = [str(path) for path in data_files]
        self.tokenizer = tokenizer
        self.processor = processor
        self.config = config
        self.prompt_key = config.get("prompt_key", "prompt")
        self.max_prompt_length = config.get("max_prompt_length", 8192)
        self.return_raw_chat = config.get("return_raw_chat", True)
        self.return_full_prompt = config.get("return_full_prompt", False)
        self.truncation = config.get("truncation", "error")
        self.filter_overlong_prompts = config.get("filter_overlong_prompts", True)
        self.apply_chat_template_kwargs = dict(
            config.get("apply_chat_template_kwargs", {})
        )
        self.rows: list[dict] = []
        self._load_data()
        self._filter_rows_if_requested()

    def _load_data(self) -> None:
        self.rows = []
        for path in self.data_files:
            self.rows.extend(load_rows(path))
        print(
            f"OpenAIFCToolDataset loaded {len(self.rows)} rows from {self.data_files}"
        )

    def _template_kwargs(self) -> dict:
        kwargs = dict(self.apply_chat_template_kwargs)
        kwargs.pop("tools", None)
        return kwargs

    def _render(self, row: dict, tokenize: bool):
        messages = row.get(self.prompt_key)
        if not isinstance(messages, list) or not messages:
            raise ValueError("row.prompt must be a non-empty OpenAI message list")
        return self.tokenizer.apply_chat_template(
            messages,
            tools=tools_for_row(row),
            add_generation_prompt=True,
            tokenize=tokenize,
            **self._template_kwargs(),
        )

    def _filter_rows_if_requested(self) -> None:
        if not self.filter_overlong_prompts:
            return
        before = len(self.rows)
        self.rows = [
            row
            for row in self.rows
            if len(self._render(row, tokenize=True)) <= self.max_prompt_length
        ]
        if len(self.rows) != before:
            print(
                f"OpenAIFCToolDataset filtered {before - len(self.rows)} overlong prompts"
            )

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, index: int) -> dict:
        row = copy.deepcopy(self.rows[index])
        messages = row.pop(self.prompt_key)
        render_row = {**row, self.prompt_key: messages}
        raw_prompt = self._render(render_row, tokenize=False)
        model_inputs = self.tokenizer(
            raw_prompt, return_tensors="pt", add_special_tokens=False
        )
        input_ids, attention_mask = verl_F.postprocess_data(
            input_ids=model_inputs["input_ids"],
            attention_mask=model_inputs["attention_mask"],
            max_length=self.max_prompt_length,
            pad_token_id=self.tokenizer.pad_token_id,
            left_pad=True,
            truncation=self.truncation,
        )
        row["input_ids"] = input_ids[0]
        row["attention_mask"] = attention_mask[0]
        row["position_ids"] = compute_position_id_with_mask(attention_mask)[0]

        raw_prompt_ids = self.tokenizer.encode(raw_prompt, add_special_tokens=False)
        if len(raw_prompt_ids) > self.max_prompt_length:
            if self.truncation == "left":
                raw_prompt_ids = raw_prompt_ids[-self.max_prompt_length :]
            elif self.truncation == "right":
                raw_prompt_ids = raw_prompt_ids[: self.max_prompt_length]
            elif self.truncation == "middle":
                left = self.max_prompt_length // 2
                raw_prompt_ids = (
                    raw_prompt_ids[:left]
                    + raw_prompt_ids[-(self.max_prompt_length - left) :]
                )
            elif self.truncation == "error":
                raise RuntimeError(
                    f"prompt length {len(raw_prompt_ids)} exceeds max_prompt_length={self.max_prompt_length}"
                )
        row["raw_prompt_ids"] = raw_prompt_ids
        if self.return_raw_chat:
            row["raw_prompt"] = messages
        if self.return_full_prompt:
            row["full_prompts"] = raw_prompt

        extra = row.setdefault("extra_info", {})
        extra["raw_messages"] = messages
        row["index"] = extra.get("index", index)
        row["tools_kwargs"] = extra.get("tools_kwargs", {})
        row["interaction_kwargs"] = extra.get("interaction_kwargs", {})
        return row

    def resume_dataset_state(self) -> None:
        self._load_data()
        self._filter_rows_if_requested()
