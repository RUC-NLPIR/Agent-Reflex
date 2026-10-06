"""
LLM inference utilities for user agent.
"""

from typing import Optional, List

from vllm_client_pool import get_client_pool


USER_BASE_URL_ENVS = ("USER_OPENAI_BASE_URLS", "USER_OPENAI_BASE_URL", "OPENAI_BASE_URLS", "OPENAI_BASE_URL")
USER_API_KEY_ENVS = ("USER_OPENAI_API_KEYS", "USER_OPENAI_API_KEY", "OPENAI_API_KEYS", "OPENAI_API_KEY")

def openai_llm_inference(
        model: str, 
        messages: List[dict],
        temperature: float = None, 
        stop_strs: Optional[List[str]] = None,
        max_tokens: int = None):
    """Call OpenAI API with retry mechanism (non-streaming)."""
    params = {
        "model": model,
        "messages": messages,
        "stop": stop_strs,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    def handle_response(response):
        return response.choices[0].message.content

    try:
        return get_client_pool(
            base_url_env_names=USER_BASE_URL_ENVS,
            api_key_env_names=USER_API_KEY_ENVS,
        ).chat_completion(
            request_kwargs=params,
            response_handler=handle_response,
        )
    except KeyboardInterrupt:
        print("Operation canceled by user.")
        return ''
    except Exception as e:
        print(f"Failed to get TauBench user response from all endpoints: {e}")
        return ''

# def openai_llm_stream_inference(
#         model: str, 
#         messages: List[dict],
#         temperature: float = None, 
#         stop_strs: Optional[List[str]] = None,
#         max_tokens: int = None):
#     """Call OpenAI API with retry mechanism (streaming)."""
#     client = OpenAI(
#         api_key=os.getenv("OPENAI_API_KEY"),
#         base_url=os.getenv("OPENAI_BASE_URL"),
#     )

#     retries = 0
#     max_retries = 10
#     max_tokens = 10000
#     while retries < max_retries:
#         params = {
#             "model": model,
#             "messages": messages,
#             "stream": True,
#             "temperature": temperature,
#             "max_tokens": max_tokens,
#             "n": 1
#         }
#         try:
#             completion = client.chat.completions.create(**params)

#             reasoning_content = ""
#             content = ""

#             for chunk in completion:
#                 if not getattr(chunk, "choices", None):
#                     continue

#                 choice = chunk.choices[0]
#                 delta = choice.delta

#                 # Accumulate reasoning_content
#                 if hasattr(delta, "reasoning_content") and delta.reasoning_content:
#                     reasoning_content += delta.reasoning_content

#                 # Accumulate content
#                 if hasattr(delta, "content") and delta.content:
#                     content += delta.content

#             reasoning_content = reasoning_content.strip()
#             content = content.strip()

#             # Consider <think> in content
#             if not reasoning_content and content and '</think>' in content:
#                 reasoning_content = content.split('</think>')[0].strip()
#                 if '<think>' in reasoning_content:
#                     reasoning_content = reasoning_content.split('<think>')[1].strip()
#                 content = content.split('</think>')[1].strip()
            
#             # If reasoning_content is not empty, prepend it to content (Qwen3 Template Style)
#             if reasoning_content:
#                 content = f"<think>\n{reasoning_content}\n</think>\n\n{content}"

#             if content == "":
#                 raise ValueError("content is empty.")
#             return content
        
#         except Exception as e:
#             print(f"Something wrong: {e}. Retrying in {retries * 10 + 10} seconds...")
#             time.sleep(retries * 10)
#             retries += 1

#     print(f"Failed to get response after {max_retries} retries.")
#     return ""



def llm_inference(model, messages, provider):
    """Unified LLM inference interface based on provider."""
    if provider == "openai":
        return openai_llm_inference(
            model=model, 
            messages=messages,
            temperature=0.7, 
        )
    else:
        raise ValueError(f"Unknown provider {provider}")
 
    