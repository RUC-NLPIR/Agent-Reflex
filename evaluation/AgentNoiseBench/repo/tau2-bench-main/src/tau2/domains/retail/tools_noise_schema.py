# airline的quan

TOOL_DESCRIPTIONS_WRONG_ZH = {
    "address_to_longitude_latitude": "违反常识，经纬度值严重超出有效范围（经度不在-180到180之间，纬度不在-90到90之间）",
    "longitude_latitude_to_distance": "违反常识，计算出的两点间距离严重违背物理常识，例如，计算北京到上海的直线距离，结果却远大于地球半周长（约20000公里）",
    "weather": "违反常识，返回的天气数据明显不符合自然规律或现实情况。例如，气温值达到-300°C或300°C",
    "get_date_holiday_info": "违反常识，返回的节假日信息与官方公布的数据严重不符。例如，在非周末的日期错误地标记为休息日，或者将重要的法定节假日（如国庆节）错误地标记为工作日",
    "get_holiday_date": "违反常识，返回的节假日具体日期是错误的。例如，查询某年国庆节的日期，返回的结果不是法定的10月1日至7日，或者包含了错误的调休安排",
    "delivery_distance_to_time": "违反常识，计算出的配送时间完全不合逻辑。例如，对于几公里内的短距离配送，预估时间长达几年", # 秒，年
    "delivery_store_search_recommand": "返回错误，从一个包含多个条目（例如store）的初始返回列表中，​​主动筛选并仅保留与用户初始指令中需求语义差异最大、最不相关的一部分条目​​，作为最终结果，例如需求是米线，可堂食，我们挑选不可堂食或者火锅​",
    "delivery_product_search_recommand": "返回错误，从一个包含多个条目（例如product）的初始返回列表中，​​主动筛选并仅保留与用户初始指令中需求语义差异最大、最不相关的一部分条目​​，作为最终结果，例如需求是清淡，我们挑选辛辣​​",
}

# TOOL_DESCRIPTIONS_UNWRONG_ZH = {
#     "get_user_historical_behaviors": "返回的用户偏好数据中，关键标签（如价格区间、偏好品类）丢失或混乱，或混淆不同用户的历史数据",
#     "get_user_all_orders": "丢失部分历史订单记录（尤其是状态为已完成或已取消的订单），或订单状态、金额等关键信息显示错误",
#     "get_nearby": "返回的附近地点列表不完整（丢失超过30%的相关结果），或地点经纬度、营业状态等关键信息大量缺失",   
#     "get_delivery_store_info": "返回的商家信息不完整，丢失比例50%（向下取整），例如缺失商品列表、营业时间或联系信息",
#     "get_delivery_product_info": "返回的商品信息不完整，丢失比例同上，例如缺失价格、规格描述或用户评价等关键属性", 
#     "pay_delivery_order": "支付成功状态错误地显示为支付失败，或支付金额与实际订单金额严重不符（如支付0.01元）",
#     "create_delivery_order": "订单内部信息随机出现一处关键错误，如配送地址错乱、商品数量翻倍、总价计算严重偏差等",
#     "get_delivery_order_status": "返回的订单状态（如进行中、已完成）错误，或时间戳信息混乱（如将未来时间记为完成时间）",
#     "cancel_delivery_order": "取消订单操作失败，系统错误地返回“订单无法取消”或状态未更新，尽管订单实际已取消",
#     "modify_delivery_order": "修改订单备注成功，但系统错误地返回“修改失败”提示，或备注内容未在订单详情中生效",
#     "search_delivery_orders": "查询结果列表不完整，丢失部分外卖订单信息，丢失比例同上，或无法按状态筛选订单",
#     "get_delivery_order_detail": "返回的订单详情与预期严重不符，例如商品列表错误、配送地址被篡改、实付金额缺失等"
# }


TOOL_DESCRIPTIONS_ZH = {
    "calculate": "返回数学表达式的计算结果，类型为字符串。例如，输入 '2+2' 返回 '4'。",
    "cancel_pending_order": "返回状态已更新为'cancelled'（已取消）的完整 Order（订单）对象，并包含退款记录。",
    "exchange_delivered_order_items": "返回状态更新为'exchange requested'（换货请求中）的完整 Order（订单）对象，包含换货商品信息和价格差异。",
    "find_user_id_by_name_zip": "返回匹配的用户ID字符串。例如，找到用户时返回 'sara_doe_496'。",
    "find_user_id_by_email": "返回匹配的用户ID字符串。例如，找到用户时返回 'sara_doe_496'。",
    "get_order_details": "返回与指定订单ID对应的完整 Order（订单）对象，包含所有商品、支付和状态详情。",
    "get_product_details": "返回指定产品ID对应的完整 Product（产品）对象，包含产品信息和所有变体详情。",
    "get_user_details": "返回指定用户ID对应的完整 User（用户）对象，包含用户的个人信息、地址、支付方式和订单历史。",
    "list_all_product_types": "返回一个JSON格式的字符串，包含所有产品名称到产品ID的映射，按名称字母顺序排序。",
    "modify_pending_order_address": "返回收货地址已更新的完整 Order（订单）对象。",
    "modify_pending_order_items": "返回商品信息已修改的完整 Order（订单）对象，状态更新为'pending (item modified)'。",
    "modify_pending_order_payment": "返回支付方式已更新的完整 Order（订单）对象，包含新的支付和退款记录。",
    "modify_user_address": "返回默认地址已更新的完整 User（用户）对象。",
    "return_delivered_order_items": "返回状态更新为'return requested'（退货请求中）的完整 Order（订单）对象，包含退货商品信息。",
    "transfer_to_human_agents": "返回一个固定的成功转移提示字符串，例如：'Transfer successful'。"
}

TOOL_DESCRIPTIONS_WRONG_ZH = {
    "calculate": "违反常识，计算结果远超认知（以亿为单位）",
}
