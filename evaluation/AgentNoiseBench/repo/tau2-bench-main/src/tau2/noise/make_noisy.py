# Defines a class that injects noise; the noise types are tool-call failure and
# blurred tool results.
# todo: Error 401 Unauthorized。Error 403 Forbidden.Error 408 Request Timeout​​ Error 429 Too Many Requests
# Introduce a separate variable to distinguish the total number of injected noises
# from the per-tool usage cap.
#
# from vita.noise.system_prompt import en_add_blurred
from tau2.domains.airline.tools_noise_schema import TOOL_DESCRIPTIONS_WRONG_EN
# The description is no longer needed here; import it directly instead.
# from tau2.domains.delivery.tools_all import TOOL_DESCRIPTIONS_ZH
from tau2.data_model.message import ToolCall
from tau2.environment.environment import Environment
import os
import random
import json
import re
import threading
import time
from loguru import logger
import requests
from tau2.config import (
    models,
    DEFAULT_MAX_RETRIES,
)
tool_calls = ['delivery_store_search_recommand', 'delivery_product_search_recommand', "search_direct_flight", "search_onestop_flight"]

_injector_clients: dict[tuple, object] = {}
_injector_clients_lock = threading.Lock()


def _injector_client(api_key: str, base_url: str, timeout: float):
    """Cached OpenAI client per (endpoint, timeout bucket)."""
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
def replace_placeholders(template_str, tool_msg, user_msg, priority_level):

    result = template_str.replace("%prompt1%", tool_msg)
    result = result.replace("%prompt2%", user_msg)
    result = result.replace("%prompt3%", str(priority_level))

    return result
def replace_placeholders_wrong(template_str, instruction):

    result = template_str.replace("%prompt1%", instruction)
    return result

class tool_noise_bench():
    def __init__(
        self,
        domain: str,
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
        tools_description: str=None,
        language: str=None,
    ):
        # All attribute initialisation below must stay indented (4 spaces).
        self.llm = llm
        self.domain = domain
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
        self.tool_name_description = tools_description

    def _client(self, timeout: float):
        return _injector_client(self.API_key, self.Base_url, timeout)

    def ask_ai(self):
        if self.Category=='blurred':
            input_messages = replace_placeholders(self.sys_prompt, self.messages, self.user_msg, self.priority_level)
        elif self.Category=='wrong':
            # input_messages = replace_placeholders_wrong(self.sys_prompt, self.user_msg)
            input_messages = self.sys_prompt.format(a=self.tool_name_description, b=TOOL_DESCRIPTIONS_WRONG_EN, c=self.tool_call, d=self.messages, e=self.instructions)

        # Redundancy uses a different set of placeholders here.
        elif self.Category=='redundant':
            input_messages = self.sys_prompt.format(a=self.messages, b=self.instructions)
        elif self.Category=='induce':
            input_messages = self.sys_prompt.format(a=self.messages, c=self.instructions)
        elif self.Category=='incomplete':
            input_messages = self.sys_prompt.format(a=self.messages, b=self.instructions)
        from tau2.utils.llm_utils import user_llm_limit
        from tau2.utils.retry_policy import MAX_TRANSIENT_RETRIES, backoff_seconds, classify
        from tau2.utils.task_deadline import (
            TaskTimeout,
            check_deadline,
            remaining_seconds,
            request_timeout,
        )

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
        key_list = [key for key in TOOL_DESCRIPTIONS_WRONG_EN]
        if self.tool_call in key_list:
            return True, self.ask_ai()
        else:
            return False, self.messages
    def Add_Redundant(self):
        return True, self.ask_ai()
    def Add_induce(self):
        # Modify the tags by prefixing them with a recommendation.
        if self.domain == 'airline' or self.domain == 'telecom' or self.domain == 'retail':
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
