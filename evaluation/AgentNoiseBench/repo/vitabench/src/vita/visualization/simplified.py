import json
import os
from pathlib import Path

# Same anchor as vita.utils.utils.DATA_DIR, recomputed here rather than imported
# because this module is also run directly (python src/vita/visualization/simplified.py),
# where the vita package is not on sys.path.
DATA_DIR = Path(__file__).parents[3] / "data"

def extract_all_messages_from_file(file_path):
    """
    从JSON文件中提取所有simulations的所有messages内容，按照指定格式抽象化
    """
    try:
        # 读取JSON文件
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        all_simulations_data = []
        
        # 检查是否有simulations字段
        if 'simulations' not in data:
            print("文件中没有找到simulations字段")
            return all_simulations_data
        
        # 遍历所有simulations
        for simulation_idx, simulation in enumerate(data['simulations']):
            simulation_data = {
                'simulation_id': simulation.get('id', f'simulation_{simulation_idx}'),
                'task_id': simulation.get('task_id', ''),
                'timestamp': simulation.get('timestamp', ''),
                'domain': simulation.get('domain', ''),
                'messages': []
            }
            
            # 提取当前simulation的messages
            if 'messages' in simulation:
                for msg in simulation['messages']:
                    extracted_msg = {}
                    
                    # 提取role和content
                    extracted_msg['role'] = msg.get('role', '')
                    
                    # 处理content
                    if msg.get('content'):
                        extracted_msg['content'] = msg['content']
                    
                    # 处理assistant角色的tool_calls
                    if msg['role'] == 'assistant' and msg.get('tool_calls'):
                        extracted_msg['tool_calls'] = []
                        for tool_call in msg['tool_calls']:
                            tool_info = {
                                'name': tool_call.get('name', ''),
                                'arguments': tool_call.get('arguments', {})
                            }
                            # 如果arguments是字符串，尝试解析为JSON
                            if isinstance(tool_info['arguments'], str):
                                try:
                                    tool_info['arguments'] = json.loads(tool_info['arguments'])
                                except json.JSONDecodeError:
                                    # 如果解析失败，保持原样
                                    pass
                            extracted_msg['tool_calls'].append(tool_info)
                    
                    # 处理tool角色的name
                    if msg['role'] == 'tool' and msg.get('name'):
                        extracted_msg['name'] = msg['name']
                    
                    simulation_data['messages'].append(extracted_msg)
            
            all_simulations_data.append(simulation_data)
        
        return all_simulations_data
        
    except Exception as e:
        print(f"处理文件时出错: {e}")
        return []

def generate_output_filename(input_file_path):
    """
    根据输入文件路径生成输出文件名
    保持与输入文件同名，保存在指定目录下
    """
    # 获取输入文件名（不含扩展名）
    input_filename = os.path.basename(input_file_path)
    base_name = os.path.splitext(input_filename)[0]
    
    # 构建输出文件路径
    output_dir = str(DATA_DIR / "simple_version")
    output_filename = f"{base_name}_extracted.json"
    output_file_path = os.path.join(output_dir, output_filename)
    
    return output_file_path

def save_all_simulations_to_auto_named_file(all_simulations_data, input_file_path):
    """
    将所有模拟数据保存到自动命名的文件中，并启用自动换行
    """
    try:
        # 生成输出文件路径
        output_file_path = generate_output_filename(input_file_path)
        
        # 确保输出目录存在
        output_dir = os.path.dirname(output_file_path)
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
        
        # 自定义JSON编码器，处理长字符串的自动换行
        class CustomJSONEncoder(json.JSONEncoder):
            def iterencode(self, o, _one_shot=False):
                """重写iterencode方法，处理长字符串的换行"""
                for chunk in super().iterencode(o, _one_shot):
                    # 如果遇到长字符串，添加换行
                    if len(chunk) > 100 and '"' not in chunk and "'" not in chunk:
                        # 在适当位置插入换行符
                        lines = []
                        current_line = ""
                        words = chunk.split()
                        for word in words:
                            if len(current_line + word) > 80:
                                if current_line:
                                    lines.append(current_line)
                                current_line = word
                            else:
                                if current_line:
                                    current_line += " " + word
                                else:
                                    current_line = word
                        if current_line:
                            lines.append(current_line)
                        chunk = '\n'.join(lines)
                    yield chunk
        
        # 将所有模拟数据保存到文件中，启用缩进和自动换行
        with open(output_file_path, 'w', encoding='utf-8') as f:
            # 使用自定义的JSON格式化参数
            json.dump(
                all_simulations_data, 
                f, 
                ensure_ascii=False, 
                indent=2,
                separators=(',', ': '),  # 在冒号后添加空格，提高可读性
                # 使用默认的encoder，但通过indent参数控制换行
            )
        
        print(f"所有模拟数据已保存到: {output_file_path}")
        print(f"文件结构: 包含 {len(all_simulations_data)} 个模拟对象，存储在一个列表中")
        print(f"已启用自动换行格式化，便于阅读")
        
        return output_file_path
        
    except Exception as e:
        print(f"保存文件时出错: {e}")
        return None

def format_long_text(text, max_line_length=80):
    """
    格式化长文本，在适当位置添加换行符
    """
    if not text or len(text) <= max_line_length:
        return text
    
    # 尝试在句子结束处换行
    lines = []
    current_line = ""
    
    # 按句子分割（中文和英文标点）
    import re
    sentences = re.split(r'([。！？\.!?]\s*)', text)
    
    for i in range(0, len(sentences), 2):
        if i + 1 < len(sentences):
            sentence = sentences[i] + sentences[i + 1]
        else:
            sentence = sentences[i]
        
        if len(current_line + sentence) <= max_line_length:
            current_line += sentence
        else:
            if current_line:
                lines.append(current_line.strip())
            current_line = sentence
            # 如果单个句子就超过最大长度，强制分割
            if len(current_line) > max_line_length:
                words = re.split(r'(\s+)', current_line)
                current_line = ""
                for word in words:
                    if len(current_line + word) > max_line_length:
                        if current_line:
                            lines.append(current_line.strip())
                        current_line = word
                    else:
                        current_line += word
    
    if current_line:
        lines.append(current_line.strip())
    
    return '\n'.join(lines)

def save_with_better_formatting(all_simulations_data, output_file_path):
    """
    使用更好的格式化方式保存JSON，处理长字符串的换行
    """
    try:
        # 先进行标准的JSON格式化
        formatted_json = json.dumps(
            all_simulations_data, 
            ensure_ascii=False, 
            indent=2,
            separators=(',', ': ')
        )
        
        # 处理长字符串的换行
        lines = formatted_json.split('\n')
        formatted_lines = []
        
        for line in lines:
            # 如果行太长且包含长字符串，尝试换行
            if len(line) > 120 and '"' in line:
                # 找到字符串内容的位置
                colon_pos = line.find(':')
                if colon_pos > 0:
                    key_part = line[:colon_pos + 1]
                    value_part = line[colon_pos + 1:].strip()
                    
                    # 如果值部分是长字符串
                    if value_part.startswith('"') and value_part.endswith('"') and len(value_part) > 100:
                        string_content = value_part[1:-1]  # 去掉引号
                        formatted_string = format_long_text(string_content)
                        
                        # 重新构建行
                        formatted_lines.append(key_part)
                        formatted_lines.append('  "' + formatted_string.replace('\n', '\n  ') + '"')
                    else:
                        formatted_lines.append(line)
                else:
                    formatted_lines.append(line)
            else:
                formatted_lines.append(line)
        
        # 写入文件
        with open(output_file_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(formatted_lines))
        
        return True
        
    except Exception as e:
        print(f"格式化保存时出错: {e}")
        return False

def print_detailed_summary(all_simulations_data):
    """
    打印详细的摘要信息
    """
    print(f"\n=== 详细摘要 ===")
    print(f"总模拟数量: {len(all_simulations_data)}")
    
    total_messages = 0
    total_tool_calls = 0
    
    for simulation in all_simulations_data:
        messages_count = len(simulation['messages'])
        total_messages += messages_count
        
        # 统计tool calls
        tool_calls_count = 0
        for msg in simulation['messages']:
            if msg.get('tool_calls'):
                tool_calls_count += len(msg['tool_calls'])
        total_tool_calls += tool_calls_count
        
        print(f"\n模拟 ID: {simulation['simulation_id']}")
        print(f"  任务ID: {simulation['task_id']}")
        print(f"  领域: {simulation['domain']}")
        print(f"  时间戳: {simulation['timestamp']}")
        print(f"  消息数量: {messages_count}")
        print(f"  工具调用次数: {tool_calls_count}")
        
        # 角色统计
        role_count = {}
        for msg in simulation['messages']:
            role = msg.get('role', 'unknown')
            role_count[role] = role_count.get(role, 0) + 1
        
        for role, count in role_count.items():
            print(f"    {role}角色: {count}")
    
    print(f"\n=== 总体统计 ===")
    print(f"总消息数: {total_messages}")
    print(f"总工具调用次数: {total_tool_calls}")
    print(f"平均每个模拟的消息数: {total_messages / len(all_simulations_data):.1f}")

def print_messages_preview(all_simulations_data, max_preview=3):
    """
    打印每个模拟的消息预览
    """
    print(f"\n=== 消息预览 ===")
    
    for simulation in all_simulations_data[:max_preview]:
        print(f"\n模拟 {simulation['simulation_id']} 的前3条消息:")
        
        for i, msg in enumerate(simulation['messages'][:3]):
            role = msg.get('role', 'unknown')
            content_preview = msg.get('content', '')[:80] + '...' if msg.get('content') and len(msg.get('content', '')) > 80 else msg.get('content', '无内容')
            
            # 处理tool calls
            tool_info = ""
            if msg.get('tool_calls'):
                tool_names = [tool.get('name', '未知工具') for tool in msg.get('tool_calls', [])]
                tool_info = f" [工具调用: {', '.join(tool_names)}]"
            
            print(f"  {i+1}. {role}: {content_preview}{tool_info}")

def print_file_structure_example(all_simulations_data):
    """
    打印文件结构示例
    """
    print(f"\n=== 输出文件结构示例 ===")
    print("文件将包含以下结构:")
    print("[")
    for i, simulation in enumerate(all_simulations_data[:2]):
        print("  {")
        print(f'    "simulation_id": "{simulation["simulation_id"]}",')
        print(f'    "task_id": "{simulation["task_id"]}",')
        print(f'    "domain": "{simulation["domain"]}",')
        print(f'    "timestamp": "{simulation["timestamp"]}",')
        print(f'    "messages": [')
        if simulation['messages']:
            print(f'      ... {len(simulation["messages"])} 条消息 ...')
        print("    ]")
        print("  }," if i < len(all_simulations_data[:2]) - 1 else "  }")
    if len(all_simulations_data) > 2:
        print(f"  ... {len(all_simulations_data) - 2} 个更多模拟 ...")
    print("]")

def main():
    # 输入文件路径
    input_file = str(DATA_DIR / "simulations" / "20251022_134018_delivery_llm_agent_o4-mini_user_simulator_gpt-4.1_think.json")
    
    # 提取所有消息
    print("开始提取所有模拟的消息...")
    print(f"输入文件: {input_file}")
    all_simulations_data = extract_all_messages_from_file(input_file)
    
    if all_simulations_data:
        # 打印详细摘要
        print_detailed_summary(all_simulations_data)
        
        # 打印消息预览
        print_messages_preview(all_simulations_data)
        
        # 打印文件结构示例
        print_file_structure_example(all_simulations_data)
        
        # 自动生成输出文件名并保存数据
        output_file_path = save_all_simulations_to_auto_named_file(all_simulations_data, input_file)
        
        if output_file_path:
            # 显示第一个模拟的第一条完整消息作为示例
            print(f"\n=== 第一个模拟的第一条完整消息示例 ===")
            if all_simulations_data and all_simulations_data[0]['messages']:
                first_msg = all_simulations_data[0]['messages'][0]
                print(json.dumps(first_msg, ensure_ascii=False, indent=2))
            
            print(f"\n提取完成！共处理 {len(all_simulations_data)} 个模拟")
            print(f"输入文件: {input_file}")
            print(f"输出文件: {output_file_path}")
            print(f"文件格式: 包含 {len(all_simulations_data)} 个模拟对象的列表")
            print(f"已启用自动换行格式化，便于阅读长文本内容")
        else:
            print("文件保存失败")
    else:
        print("未找到模拟数据")

if __name__ == "__main__":
    main()