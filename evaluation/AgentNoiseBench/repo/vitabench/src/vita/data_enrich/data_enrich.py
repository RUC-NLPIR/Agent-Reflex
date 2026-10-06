import json
import os
from pathlib import Path
from typing import Dict, Any
from openai import OpenAI
from system_prompt import tree_systemprompt
class SimpleDataEnrichment:
    """简化版数据丰富系统 - 直接使用API处理整个文件"""
    
    def __init__(self):
        self.client = OpenAI(
            api_key="<api key>",
            base_url="https://www.blueshirtmap.com/v1",
        )
    
    def enrich_complete_data(self, original_data: Dict) -> Dict:
        """使用API一次性丰富所有数据"""
        
        system_prompt = tree_systemprompt
        user_prompt = system_prompt.format({json.dumps(original_data, ensure_ascii=False, indent=4)})
        try:
            response = self.client.chat.completions.create(
                model="o4-mini",
                messages=[
                    {"role": "user", "content": user_prompt}
                ],
                temperature=0.7,
                max_tokens=32768  # 根据数据大小调整
            )
            
            # 解析API返回的JSON数据
            enriched_content = response.choices[0].message.content
            return json.loads(enriched_content)
            
        except Exception as e:
            print(f"API数据丰富失败: {e}")
            return original_data  # 失败时返回原始数据

def load_json_file(file_path: str) -> Dict:
    """加载JSON文件"""
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            return json.load(file)
    except Exception as e:
        print(f"加载文件失败: {e}")
        raise

def save_json_file(data: Dict, file_path: str) -> None:
    """保存数据到JSON文件"""
    directory = os.path.dirname(file_path)
    if directory and not os.path.exists(directory):
        os.makedirs(directory)
    
    try:
        with open(file_path, 'w', encoding='utf-8') as file:
            json.dump(data, file, ensure_ascii=False, indent=4)
        print(f"数据已保存到: {file_path}")
    except Exception as e:
        print(f"保存文件失败: {e}")
        raise

def enrich(input_file, output_file):
    """主函数：简化版数据丰富流程"""

    print("开始简化版数据丰富流程...")
    print(f"输入文件: {input_file}")
    print(f"输出文件: {output_file}")
    
    # 1. 加载原始数据
    print("1. 加载原始数据...")
    try:
        original_data = load_json_file(input_file)
        print("原始数据加载成功")
    except Exception as e:
        print(f"加载原始数据失败: {e}")
        return None
    
    # 2. 初始化简化版系统
    enrichment_system = SimpleDataEnrichment()
    
    # 3. 一次性使用API丰富所有数据
    print("2. 使用API进行数据丰富...")
    try:
        enriched_data = enrichment_system.enrich_complete_data(original_data)
        print("API数据丰富完成")
    except Exception as e:
        print(f"数据丰富失败: {e}")
        return None
    
    # 4. 保存结果
    print("3. 保存丰富后的数据...")
    try:
        save_json_file(enriched_data, output_file)
    except Exception as e:
        print(f"保存文件失败: {e}")
        return None
    
    # 5. 生成统计信息
    print("\n=== 数据丰富完成 ===")
    print(f"结果已保存至: {output_file}")
    
    return enriched_data

if __name__ == "__main__":
    # 执行简化版数据丰富流程
    # Anchored on this checkout instead of the original /NAS mount; run directly from
    # its own directory (see the flat `from system_prompt import ...` above).
    domain_dir = Path(__file__).parents[3] / "data" / "vita" / "domains" / "delivery"
    input_file = str(domain_dir / "tasks_zh.json")
    output_file = str(domain_dir / "tasks_new.json")
    enriched_result = enrich(input_file, output_file)
    
    if enriched_result:
        print("\n=== 任务执行成功 ===")
        print("数据已通过API一次性丰富完成")
    else:
        print("数据丰富流程执行失败")