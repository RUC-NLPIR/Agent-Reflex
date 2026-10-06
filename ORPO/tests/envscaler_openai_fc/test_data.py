from recipe.envscaler_openai_fc.data.build_bfcl_val import build_rows as build_bfcl_rows
from recipe.envscaler_openai_fc.data.build_envscaler_train import (
    build_rows as build_train_rows,
)
from recipe.envscaler_openai_fc.dataset import tools_for_row

TOOL = {
    "type": "function",
    "function": {
        "name": "lookup",
        "description": "lookup",
        "parameters": {"type": "object", "properties": {}},
    },
}


def test_envscaler_builder_keeps_tools_out_of_system_text():
    tasks = [
        {
            "task_id": "task-1",
            "env_id": "env-1",
            "env_class_name": "TinyEnv",
            "init_config": {"items": []},
            "task": "Do the task",
            "checklist_with_func": [
                {"check_item": "done", "check_func": "def check_func(s): return True"}
            ],
        }
    ]
    metadata = {
        "row": {
            "env_id": "env-1",
            "env_class_code": "class TinyEnv: pass",
            "tools": [TOOL],
            "environment_introduction": "A tiny environment.",
            "constraints_rules": ["Be careful."],
        }
    }
    row = build_train_rows(tasks, metadata)[0]
    assert row["agent_name"] == "envscaler_openai_fc"
    assert "lookup" not in row["prompt"][0]["content"]
    assert tools_for_row(row) == [TOOL]


def test_bfcl_builder_selects_fixed_ordered_prefix():
    samples = [
        {
            "id": f"multi_turn_base_{index}",
            "questions": [f"q{index}"],
            "answers": [[]],
            "initial_config": {},
            "involved_classes": [],
            "tools": [TOOL],
        }
        for index in reversed(range(3))
    ]
    rows = build_bfcl_rows(samples, limit=3)
    assert [row["extra_info"]["id"] for row in rows] == [
        "multi_turn_base_0",
        "multi_turn_base_1",
        "multi_turn_base_2",
    ]
    assert all(row["agent_name"] == "bfcl_agent" for row in rows)
