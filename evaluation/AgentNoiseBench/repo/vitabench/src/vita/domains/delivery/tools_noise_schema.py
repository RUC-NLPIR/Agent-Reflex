# 所以说可能出现的错误选择是
# 1.失败。 2.冗余。3. 诱导  4.错误     
# 4.1违反常识，4.2排序失败 4.3 返回前10-20个token tag不完整，返回截断，删去不符合的数据
# todo: 每个
TOOL_DESCRIPTIONS_WRONG_ZH = {
    "address_to_longitude_latitude": "违反常识，经纬度值严重超出有效范围（经度不在-180到180之间，纬度不在-90到90之间）",
    "longitude_latitude_to_distance": "违反常识，计算出的两点间距离严重违背物理常识，例如，计算北京到上海的直线距离，结果却远大于地球半周长（约20000公里）",
    "weather": "违反常识，返回的天气数据明显不符合自然规律或现实情况。例如，气温值达到-300°C或300°C",
}

TOOL_DESCRIPTIONS_WRONG_EN = {
    "address_to_longitude_latitude": "Violates common sense, coordinate values are severely outside valid ranges (longitude not between -180 and 180, latitude not between -90 and 90)",
    "longitude_latitude_to_distance": "Violates common sense, the calculated distance between two points severely defies physical reality. For example, calculating the straight-line distance from Beijing to Shanghai yields a result far greater than the Earth's semi-circumference (approximately 20,000 km)",
    "weather": "Violates common sense, the returned weather data is clearly inconsistent with natural laws or reality. For example, temperature values reaching -300°C or 300°C",
}

TOOL_DESCRIPTIONS_UNWRONG_ZH = {
    "get_user_historical_behaviors": "返回的用户偏好数据中，关键标签（如价格区间、偏好品类）丢失或混乱，或混淆不同用户的历史数据",
    "get_user_all_orders": "丢失部分历史订单记录（尤其是状态为已完成或已取消的订单），或订单状态、金额等关键信息显示错误",
    "get_nearby": "返回的附近地点列表不完整（丢失超过30%的相关结果），或地点经纬度、营业状态等关键信息大量缺失",   
    "get_delivery_store_info": "返回的商家信息不完整，丢失比例50%（向下取整），例如缺失商品列表、营业时间或联系信息",
    "get_delivery_product_info": "返回的商品信息不完整，丢失比例同上，例如缺失价格、规格描述或用户评价等关键属性", 
    "pay_delivery_order": "支付成功状态错误地显示为支付失败，或支付金额与实际订单金额严重不符（如支付0.01元）",
    "create_delivery_order": "订单内部信息随机出现一处关键错误，如配送地址错乱、商品数量翻倍、总价计算严重偏差等",
    "get_delivery_order_status": "返回的订单状态（如进行中、已完成）错误，或时间戳信息混乱（如将未来时间记为完成时间）",
    "cancel_delivery_order": "取消订单操作失败，系统错误地返回“订单无法取消”或状态未更新，尽管订单实际已取消",
    "modify_delivery_order": "修改订单备注成功，但系统错误地返回“修改失败”提示，或备注内容未在订单详情中生效",
    "search_delivery_orders": "查询结果列表不完整，丢失部分外卖订单信息，丢失比例同上，或无法按状态筛选订单",
    "get_delivery_order_detail": "返回的订单详情与预期严重不符，例如商品列表错误、配送地址被篡改、实付金额缺失等"
}