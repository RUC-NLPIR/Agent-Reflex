"""Adapter for trusted EnvScaler ``py_class`` environments."""

import types
from copy import deepcopy

from .base import EnvAdapter, ToolExecutionError


def load_environment_class(source: str, class_name: str):
    module = types.ModuleType("_envscaler_openai_fc_dynamic_env")
    exec(source, module.__dict__)  # noqa: S102 - trusted official EnvScaler data only
    if not hasattr(module, class_name):
        available = sorted(k for k in module.__dict__ if not k.startswith("_"))
        raise ValueError(
            f"Environment class {class_name!r} not found; available={available}"
        )
    return getattr(module, class_name)


def instantiate_environment(env_class, initial_state: dict):
    state = deepcopy(initial_state)
    try:
        instance = env_class(state) if state else env_class({})
    except TypeError:
        instance = env_class()
    for key, value in state.items():
        setattr(instance, key, value)
    return instance


def snapshot_instance(instance) -> dict:
    return deepcopy(
        {
            key: value
            for key, value in vars(instance).items()
            if not (key.startswith("__") and key.endswith("__"))
        }
    )


def run_check_function(source: str, initial_state: dict, final_state: dict):
    namespace = {"__builtins__": __builtins__, "initial_state": deepcopy(initial_state)}
    try:
        exec(source, namespace)  # noqa: S102 - trusted official EnvScaler data only
        check = namespace.get("check_func")
        if check is None:
            return False, None, "check_func not found"
        result = check(final_state)
        if not isinstance(result, bool):
            return (
                False,
                None,
                f"check_func returned {type(result).__name__}, expected bool",
            )
        return True, result, None
    except Exception as exc:  # checklist failures count as failed checks
        return False, None, f"{type(exc).__name__}: {exc}"


class EnvScalerAdapter(EnvAdapter):
    """Execute tools and checklist verifiers for one EnvScaler sample."""

    def __init__(self, environment: dict, verifier: dict):
        self.environment = deepcopy(environment)
        self.verifier = deepcopy(verifier)
        self.instance = None
        self.initial_state: dict = {}
        self._tools = deepcopy(environment.get("tools") or [])
        self._allowed_tools = {
            tool.get("function", {}).get("name")
            for tool in self._tools
            if tool.get("type") == "function" and tool.get("function", {}).get("name")
        }

    async def build_env(self) -> None:
        env_class = load_environment_class(
            self.environment["class_code"], self.environment["class_name"]
        )
        initial_state = self.environment.get("initial_state") or {}
        if not isinstance(initial_state, dict):
            raise TypeError("environment.initial_state must be a JSON object")
        self.instance = instantiate_environment(env_class, initial_state)
        self.initial_state = snapshot_instance(self.instance)

    def get_tools(self) -> list[dict]:
        return deepcopy(self._tools)

    async def call_tool(self, name: str, arguments: dict) -> str:
        if self.instance is None:
            raise RuntimeError("build_env() must be called before call_tool()")
        if name not in self._allowed_tools:
            return f"Error: tool '{name}' is not exposed by this environment."
        if not isinstance(arguments, dict):
            return "Error: tool arguments must be a JSON object."
        method = getattr(self.instance, name, None)
        if not callable(method):
            return f"Error: tool '{name}' is unavailable on the environment instance."
        try:
            return str(method(**arguments))
        except Exception as exc:
            raise ToolExecutionError(name, exc) from exc

    def snapshot_state(self) -> dict:
        if self.instance is None:
            raise RuntimeError("build_env() must be called before snapshot_state()")
        return snapshot_instance(self.instance)

    async def score(self) -> tuple[float, dict]:
        final_state = self.snapshot_state()
        checklist = self.verifier.get("checklist") or []
        if not checklist:
            return 0.0, {"passed": 0, "total": 0, "checks": []}

        details = []
        passed = 0
        for item in checklist:
            ok, result, error = run_check_function(
                item["check_func"], self.initial_state, final_state
            )
            did_pass = bool(ok and result is True)
            passed += int(did_pass)
            details.append(
                {
                    "check_item": item.get("check_item", ""),
                    "passed": did_pass,
                    "execution_ok": ok,
                    "error": error,
                }
            )
        reward = round(passed / len(checklist), 4)
        return reward, {"passed": passed, "total": len(checklist), "checks": details}
