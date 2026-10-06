
from vita.domains.delivery.tools_noise_schema import TOOL_DESCRIPTIONS_WRONG_ZH, TOOL_DESCRIPTIONS_WRONG_EN
from vita.domains.delivery.tools_all import TOOL_DESCRIPTIONS_ZH, TOOL_DESCRIPTIONS_EN
from vita.data_model.message import ToolCall
from vita.environment.environment import Environment
from vita.config import DEFAULT_MAX_RETRIES
from loguru import logger
import os
import random
import threading
import time
def replace_placeholders(template_str, tool_msg, user_msg, priority_level):

    result = template_str.replace("%prompt1%", tool_msg)
    result = result.replace("%prompt2%", user_msg)
    result = result.replace("%prompt3%", str(priority_level))

    return result
def replace_placeholders_wrong(template_str, instruction):

    result = template_str.replace("%prompt1%", instruction)
    return result

Wrong_version = {'english':TOOL_DESCRIPTIONS_WRONG_EN,'chinese':TOOL_DESCRIPTIONS_WRONG_ZH}
Tool_version = {'english':TOOL_DESCRIPTIONS_EN,'chinese':TOOL_DESCRIPTIONS_ZH}

tool_calls = ['instore_shop_search_recommend','instore_product_search_recommend','hotel_search_recommand','attractions_search_recommend','delivery_store_search_recommand','delivery_product_search_recommand']

_injector_clients: dict[tuple, object] = {}
_injector_clients_lock = threading.Lock()


def _injector_client(api_key: str, base_url: str, timeout: float):
    """Cached OpenAI client per (endpoint, timeout bucket).

    Building a client per attempt re-creates an httpx pool on every injected
    tool result, which for `redundant` runs is once per tool call.
    """
    from openai import OpenAI

    bucket = round(timeout / 60.0)
    key = (api_key, base_url, bucket)
    with _injector_clients_lock:
        client = _injector_clients.get(key)
        if client is None:
            client = OpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=timeout,
                max_retries=0,
                default_headers={"Connection": "close"},
            )
            _injector_clients[key] = client
        return client
class tool_noise_bench():
    def __init__(
        self,
        messages: str,
        llm: str,
        API_key: str,
        sys_prompt: str,
        Base_url: str,
        user_msg: str,
        environment: Environment,
        tool_call: ToolCall,
        Category: str=None,
        priority_level: int=1,
        nums: int=1,
        instructions: str=None,
        language: str=None,
    ):
        # All attribute initialisation below must stay indented (4 spaces).
        self.llm = llm
        self.priority_level = priority_level
        self.user_msg = user_msg
        self.API_key = API_key
        self.Base_url = Base_url
        self.sys_prompt = sys_prompt
        self.Category = Category
        self.messages = messages
        self.nums = nums
        self.environment = environment
        self.tool_call = tool_call.name
        self.instructions = instructions
        self.language = language
        self.wrong_version = Wrong_version[self.language]
        self.tool_version = Tool_version[self.language]

    def _client(self, timeout: float):
        return _injector_client(self.API_key, self.Base_url, timeout)

    def ask_ai(self):
        if self.Category=='blurred':
            input_messages = replace_placeholders(self.sys_prompt, self.messages, self.user_msg, self.priority_level)
        elif self.Category=='wrong':
            # input_messages = replace_placeholders_wrong(self.sys_prompt, self.user_msg)
            # if self.tool_call=='address_to_longitude_latitude' or self.tool_call=='address_to_longitude_latitude' or self.tool_call=='address_to_longitude_latitude'
            input_messages = self.sys_prompt.format(a=self.tool_version, b=self.wrong_version, c=self.tool_call, d=self.messages, e=self.instructions)
        elif self.Category=='redundant':
            input_messages = self.sys_prompt.format(a=self.messages, b=str(self.environment.tools.db), c=self.instructions)
        elif self.Category=='induce':
            input_messages = self.sys_prompt.format(a=self.messages)
        elif self.Category=='incomplete':
            input_messages = self.sys_prompt.format(a=self.messages, b=self.instructions)
        from vita.utils.llm_utils import user_llm_limit
        from vita.utils.retry_policy import MAX_TRANSIENT_RETRIES, backoff_seconds, classify
        from vita.utils.task_deadline import (
            TaskTimeout,
            check_deadline,
            remaining_seconds,
            request_timeout,
        )

        # The `redundant` template embeds the whole environment DB, so an
        # injector call is far heavier than a user-simulator turn. Give it the
        # same read budget as any other LLM call rather than a fixed 120s.
        default_read = float(os.environ.get("EXTERNAL_LLM_TIMEOUT", "90"))
        last_error = None
        max_retries = max(DEFAULT_MAX_RETRIES, MAX_TRANSIENT_RETRIES)
        for attempt in range(max_retries + 1):
            try:
                check_deadline()
                _, read_timeout = request_timeout(default_read)
                client = self._client(read_timeout)
                with user_llm_limit(self.llm):
                    response = client.chat.completions.create(
                        model=self.llm,
                        messages=[
                            {"role": "user", "content": input_messages},
                        ],
                    )
                return response.choices[0].message.content
            except TaskTimeout:
                raise
            except Exception as e:
                last_error = e
                rem = remaining_seconds()
                if rem != float("inf") and rem <= 0:
                    raise TaskTimeout("task exceeded task timeout limit") from e
                should_retry, reason = classify(e, attempt, max_retries)
                if not should_retry:
                    logger.error(
                        f"noise injector LLM failed permanently after {attempt + 1} "
                        f"attempt(s) ({reason}): {e}"
                    )
                    raise
                delay = backoff_seconds(attempt, rem, reason)
                logger.warning(
                    f"noise injector LLM failed attempt {attempt + 1}/{DEFAULT_MAX_RETRIES + 1} "
                    f"({reason}); retrying in {delay:.1f}s: {e}"
                )
                time.sleep(delay)
        raise last_error

    def Add_fault(self):
        error_list = [
            'Error 401 Unauthorized',
            'Error 403 Forbidden',
            'Error 408 Request Timeout',
            'Error 429 Too Many Requests'
        ]
        random_index = random.randint(0, len(error_list) - 1)
        if self.tool_call == 'repair_default':
            # self.tools_dict[self.tool_call] = self.max_single_tool_noise
            return False, self.messages
        else:
            return True, error_list[random_index]
    def Add_blurred(self):
        return True, self.ask_ai()
    def Add_wrong(self):
        key_list = [key for key in self.wrong_version]
        if self.tool_call in key_list:
            return True, self.ask_ai()
        else:
            return False, self.messages
    def Add_Redundant(self):
        return True, self.ask_ai()
    def Add_induce(self):
        # Modify the tags by prefixing them with a recommendation.
        if self.tool_call in tool_calls:
            return True, self.ask_ai()
        else:
            return False, self.messages
    def Add_incomplete(self):
        return True, self.ask_ai()
    def Add_Noise(self):
        if self.Category == "wrong":
            return self.Add_wrong()
        elif self.Category == "blurred":
            return self.Add_blurred()
        elif self.Category == "induce":
            return self.Add_induce()
        elif self.Category == "redundant":
            return self.Add_Redundant()
        elif self.Category == "fault":
            return self.Add_fault()
        elif self.Category == "incomplete":
            return self.Add_incomplete()
        else:
            return False, self.messages
