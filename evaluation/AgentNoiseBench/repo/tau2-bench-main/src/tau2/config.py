# SIMULATION
# 
import os
import yaml
from dotenv import load_dotenv
from pathlib import Path
# 配置文件路径确定
_models_yaml_path = Path(__file__).parent / "models.yaml"
if os.environ.get("TAU2_MODEL_CONFIG_PATH", None):
    _models_yaml_path = os.environ.get("TAU2_MODEL_CONFIG_PATH")
# 配置文件存在性检查
if not os.path.exists(str(_models_yaml_path)):
    raise FileNotFoundError(
        f"Model configuration file ({_models_yaml_path}) dose not exists, you should create it first.")

# 深度合并字典函数，递归合并两个字典
# base = {"a": 1, "b": {"x": 10, "y": 20}}
# override = {"b": {"y": 30, "z": 40}, "c": 50}
# # 合并后: {"a": 1, "b": {"x": 10, "y": 30, "z": 40}, "c": 50}
def _deep_merge_dict(base_dict: dict, override_dict: dict) -> dict:
    result = base_dict.copy()

    for key, value in override_dict.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge_dict(result[key], value)
        else:
            result[key] = value

    return result

# 配置加载和解析
try:
    # 文件配置
    with open(_models_yaml_path, 'r') as f:
        models_config_yaml = yaml.load(f, Loader=yaml.FullLoader)
    # 获取default部分的配置
    default_model_config = models_config_yaml.get('default', {})
    # 遍历models列表中的每个模型配置
    # 将默认配置与具体模型配置深度合并
    # 以模型名称为key存储到models字典中
    models = {"default": default_model_config}
    for model in models_config_yaml.get('models', []):
        model_name = model['name']
        merged_config = _deep_merge_dict(default_model_config, model)
        if not str(merged_config.get("base_url", "")).startswith(
            ("http://127.0.0.1", "http://localhost")
        ):
            external_key = (
                os.environ.get("VITA_EXTERNAL_API_KEY")
                or os.environ.get("BOYUE_API_KEY")
            )
            external_base = (
                os.environ.get("VITA_EXTERNAL_BASE_URL")
                or os.environ.get("BOYUE_API_BASE_URL")
            )
            auth = str(merged_config.get("headers", {}).get("Authorization", ""))
            if external_key and (not auth or "<external_api_key>" in auth):
                merged_config.setdefault("headers", {})["Authorization"] = (
                    f"Bearer {external_key}"
                )
            if external_base:
                normalized_base = external_base.rstrip("/")
                if normalized_base.endswith("/chat/completions"):
                    merged_config["base_url"] = normalized_base
                elif normalized_base.endswith("/v1"):
                    merged_config["base_url"] = normalized_base + "/chat/completions"
                else:
                    merged_config["base_url"] = (
                        normalized_base + "/v1/chat/completions"
                    )
        models[model_name] = merged_config
    # ​​输出可用模型列表
    print(f"Available models: {list(models.keys())}")

except FileNotFoundError:
    print(f"Warning: models.yaml not found at {_models_yaml_path}")
    models = {}
except Exception as e:
    print(f"Error loading models.yaml: {e}")
    models = {}

DEFAULT_MAX_STEPS = 200
DEFAULT_MAX_ERRORS = 10
DEFAULT_SEED = 300
DEFAULT_MAX_CONCURRENCY = 3
DEFAULT_NUM_TRIALS = 1
DEFAULT_SAVE_TO = None
DEFAULT_LOG_LEVEL = "ERROR"

# LLM
DEFAULT_AGENT_IMPLEMENTATION = "llm_agent"
DEFAULT_USER_IMPLEMENTATION = "user_simulator"
DEFAULT_LLM_AGENT = "gpt-4.1"
DEFAULT_LLM_USER = "gpt-4.1"
DEFAULT_LLM_TEMPERATURE_AGENT = 0.0
DEFAULT_LLM_TEMPERATURE_USER = 0.0
DEFAULT_LLM_ARGS_AGENT = {"temperature": DEFAULT_LLM_TEMPERATURE_AGENT}
DEFAULT_LLM_ARGS_USER = {"temperature": DEFAULT_LLM_TEMPERATURE_USER}

DEFAULT_LLM_NL_ASSERTIONS = "gpt-4o-mini"
DEFAULT_LLM_NL_ASSERTIONS_TEMPERATURE = 0.0
DEFAULT_LLM_NL_ASSERTIONS_ARGS = {"temperature": DEFAULT_LLM_NL_ASSERTIONS_TEMPERATURE}

DEFAULT_LLM_ENV_INTERFACE = "gpt-4.1"
DEFAULT_LLM_ENV_INTERFACE_TEMPERATURE = 0.0
DEFAULT_LLM_ENV_INTERFACE_ARGS = {"temperature": DEFAULT_LLM_ENV_INTERFACE_TEMPERATURE}

# LITELLM
DEFAULT_MAX_RETRIES = int(os.environ.get("RETRY", "10"))
LLM_CACHE_ENABLED = False
DEFAULT_LLM_CACHE_TYPE = "redis"

# REDIS CACHE
REDIS_HOST = "localhost"
REDIS_PORT = 6379
REDIS_PASSWORD = ""
REDIS_PREFIX = "tau2"
REDIS_CACHE_VERSION = "v1"
REDIS_CACHE_TTL = 60 * 60 * 24 * 30

# LANGFUSE
USE_LANGFUSE = False  # If True, make sure all the env variables are set for langfuse.

# API
API_PORT = 8000

# 噪声注入与偏离审计共用的凭证，统一从这一个 .env 读取
# 覆盖方式与 models.yaml 一致：设 NOISE_ENV_PATH 指向别处即可
_noise_env_path = Path(__file__).parent / "evaluator" / ".env"
if os.environ.get("NOISE_ENV_PATH", None):
    _noise_env_path = os.environ.get("NOISE_ENV_PATH")
load_dotenv(_noise_env_path)

class Config_API:
    """评测/注入链路共用的 API 凭证，本包内的唯一来源。

    字段在 import 时绑定一次，因此 load_dotenv 必须在类体之前执行。
    """
    API_KEY = os.getenv('API_KEY')
    BASE_URL = os.getenv('BASE_URL')
    MODEL = os.getenv('MODEL')  # 偏离审计裁判模型
    EVAL = os.getenv('EVAL')  # 工具噪声生成模型
