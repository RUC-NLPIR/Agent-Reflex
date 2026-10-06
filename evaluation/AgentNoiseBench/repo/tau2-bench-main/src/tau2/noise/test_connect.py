from openai import OpenAI

client = OpenAI(
        api_key = "<api key>",
        base_url = "https://www.blueshirtmap.com/v1",
)

response = client.chat.completions.create(
                model='gpt-4o-mini',
                messages=[
                    {"role": "system", "content": "你是一个专家,你需要对每个问题回答答案和原因。"},
                    {"role": "user", "content": "一天几个小时？"},
                ]
            )
evaluation_response = response.choices[0].message.content

print(response)
print(evaluation_response)