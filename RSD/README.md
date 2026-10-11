# RSD: Environment Reflection Skill Library

This is the output of Stage 1 of Agent-Reflex, Environment Reflection Skill
Discovery (RSD). Each executable environment is anchored on a real-world MCP
server specification from [Smithery](https://smithery.ai/). Its tool returns
are perturbed with failure families mined from real tool errors. Rollouts
from a diverse LLM pool are then paired into success / failure contrasts, and
an analyzer turns each contrast into a *bad pattern* (what went wrong) and
the *reflection meta-skills* that repair it. Environment synthesis and the
environment infrastructure follow [Agent-World](https://github.com/RUC-NLPIR/Agent-World).

| | |
| --- | --- |
| Environments | 557 MCP-anchored environments, 537 with at least one skill |
| Tools | 8,856 (median 11 per environment) |
| Reflection meta-skills | **1,170** (2.2 per environment on average) |
| Bad patterns | 962 |
| Language | English (`environment_skills.jsonl`) and Chinese (`environment_skills_zh.jsonl`) |

The library is the skill source for [ReSFT](../LLaMA-Factory) data
synthesis. [ORPO](../ORPO) puts environment skills in context during
reflection on-policy distillation; its 51 EnvScaler environment skills use the
same schema and ship in `ORPO/data/environment_skills_envscaler.jsonl`.

## Example

`0146000` · **Logseq Tools** (21 tools: `getAllPages`, `getPage`, `searchPages`, `getBacklinks`, ...)

**Bad pattern.** Treats the search result summary from `getAllPages` as final fact without reading details or further pages, potentially missing matches and drawing wrong conclusions from it.

**Reflection meta-skills.**

1. When looking up information, first narrow the query conditions and run `getAllPages`.
2. Then read the details, paginated results, or statistics, and check object IDs, timestamps, and statuses.
3. Do not treat search hit counts or summaries as complete results.

<details>
<summary>中文版本</summary>

**Bad pattern.** 把 getAllPages 的搜索结果摘要当成最终事实，未继续读取详情或分页，可能遗漏匹配项并据此给出错误结论。

**Reflection meta-skills.**

1. 需要查找信息时先限定查询条件并执行 getAllPages
2. 随后读取详情、分页或统计结果，核对对象 ID、时间和状态
3. 避免把搜索命中数或摘要当作完整结果。

</details>

## File format

`environment_skills.jsonl` (English) and `environment_skills_zh.jsonl` (Chinese) share the same environments, order and schema; `bad_patterns` and `skills` are provided in each language, and tool schemas are kept as is. One environment per line:

| Field | Type | Meaning |
| --- | --- | --- |
| `env_id` | string | environment id |
| `env_name` | string | name of the anchoring MCP server |
| `environment_description` | string | what the environment manages |
| `tools` | list | the environment's tools, in OpenAI function-calling format |
| `bad_patterns` | list of strings | recurring failure patterns seen in failed rollouts |
| `skills` | list of strings | reflection meta-skills, one per entry, in the order they apply |

```python
import json

with open("RSD/environment_skills.jsonl", encoding="utf-8") as f:
    envs = {e["env_id"]: e for e in map(json.loads, f)}

env = envs["0146000"]
print(env["env_name"], len(env["tools"]), "tools")
for skill in env["skills"]:
    print("-", skill)
```

To use a skill at inference or training time, insert the environment's
`skills` into the system prompt, as `ORPO/recipe/envscaler_openai_fc/skill_context.py`
does for ORPO.
