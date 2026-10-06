TOOL_DESCRIPTIONS_ZH = {
    "longitude_latitude_to_distance": {
        "description": "根据经纬度计算两点之间的距离（以米为单位）",
        "preconditions": "根据两个点的经纬度计算它们之间的距离",
        "postconditions": "返回两点之间的距离（整数，以米为单位）",
        "args": {
            "longitude1": "第一个点的经度",
            "latitude1": "第一个点的纬度",
            "longitude2": "第二个点的经度",
            "latitude2": "第二个点的纬度"
        },
        "returns": "两点之间的距离（整数，以米为单位）"
    },
    
    "weather": {
        "description": "查询指定地址在date_start到date_end期间的天气信息",
        "preconditions": "查询指定地址在指定日期范围内的天气信息",
        "postconditions": "返回天气信息",
        "args": {
            "address": "要查询的地址",
            "date_start": "开始时间，格式为 yyyy-mm-dd",
            "date_end": "结束时间，格式为 yyyy-mm-dd"
        },
        "returns": "天气信息"
    },
    
    "address_to_longitude_latitude": {
        "description": "根据地址获取经纬度",
        "preconditions": "根据地址获取对应的经纬度坐标",
        "postconditions": "返回经纬度坐标",
        "args": {
            "address": "要查询的地址"
        },
        "returns": "[经度, 纬度]"
    },
    
    "get_date_holiday_info": {
        "description": "判断某日期是否为中国节假日；如果是则返回节假日中文名称",
        "preconditions": "根据日期判断是否为节假日，如果是则返回节假日名称",
        "postconditions": "返回节假日信息",
        "args": {
            "date": "日期，格式为 yyyy-mm-dd"
        },
        "returns": "节假日信息判断结果"
    },
    
    "get_holiday_date": {
        "description": "获取指定年份中某个节假日对应的具体日期",
        "preconditions": "获取指定年份中某个节假日的具体日期",
        "postconditions": "返回节假日的日期",
        "args": {
            "year": "年份",
            "holiday_name": "节假日名称，仅支持中文表述"
        },
        "returns": "节假日的日期"
    },
    
    "get_user_historical_behaviors": {
        "description": "获取用户基本信息和历史行为偏好数据，包括用户ID、家庭住址、工作地址等基本信息，以及各场景的详细消费习惯、偏好品类、价格区间、评分要求、时间偏好等信息，用于个性化推荐和服务优化",
        "preconditions": "获取用户历史行为数据",
        "postconditions": "返回用户历史行为信息",
        "args": {},
        "returns": "用户历史行为信息摘要"
    },
    
    "get_user_all_orders": {
        "description": "获取用户所有订单信息",
        "preconditions": "获取用户的所有订单信息",
        "postconditions": "返回用户所有订单信息",
        "args": {},
        "returns": "用户所有订单信息摘要"
    },
    
    "get_nearby": {
        "description": "获取附近所有商店/商业场所的信息",
        "preconditions": "获取指定范围内（米）的所有商业场所（商店、机场或火车站、酒店、景点、商铺等）的信息",
        "postconditions": "返回商业场所信息",
        "args": {
            "longitude": "经度",
            "latitude": "纬度",
            "range": "范围（以米为单位）"
        },
        "returns": "商店/商业场所信息"
    },
    "delivery_distance_to_time": {
        "description": "根据距离（米）计算外卖配送时间（分钟）",
        "preconditions": "根据从商家到用户地址的距离计算外卖配送时间",
        "postconditions": "返回配送时间（分钟）",
        "args": {
            "distance": "距离（以米为单位）"
        },
        "returns": "时间（以分钟为单位）",
        "tool_type": "GENERIC"
    },

    "get_delivery_store_info": {
        "description": "获取商家信息，包括商家id、评分、地址、经度、纬度、标签、商品列表",
        "preconditions": "处于外卖场景，需要获取商家的详细信息",
        "postconditions": "返回商家的详细信息",
        "args": {
            "store_id": "商家id"
        },
        "returns": "商家的详细信息",
        "tool_type": "READ"
    },

    "get_delivery_product_info": {
        "description": "获取商品信息，包括商品名称、商品id、商店名称、商店id、商品评分、商品价格、商品标签",
        "preconditions": "处于外卖场景，需要获取商品的详细信息",
        "postconditions": "返回商品的详细信息",
        "args": {
            "food_id": "商品id"
        },
        "returns": "商品的详细信息",
        "tool_type": "READ"
    },

    "delivery_store_search_recommand": {
        "description": "在外卖场景下，可以根据用户表达抽取出描述商家的关键词，搜索或推荐多个商家",
        "preconditions": "处于外卖场景，获取描述商家的关键词",
        "postconditions": "返回商家列表，引导用户选择确定商家",
        "args": {
            "keywords": "描述商家的关键词"
        },
        "returns": "结构化输出的商家信息",
        "tool_type": "READ"
    },

    "delivery_product_search_recommand": {
        "description": "在外卖场景下，可以根据用户表达抽取出描述商品的关键词，搜索或推荐多个商品",
        "preconditions": "处于外卖场景，获取描述商品的关键词",
        "postconditions": "返回商品列表，引导用户选择商品并创建订单",
        "args": {
            "keywords": "描述商品的关键词"
        },
        "returns": "结构化输出的商品信息",
        "tool_type": "READ"
    },

    "create_delivery_order": {
        "description": "外卖订单创建，仅支持单个商家下单，单个商家可以下单多个商品",
        "preconditions": "处于外卖场景，确定唯一一个店家id和一个或多个商品id，确定用户的饮食禁忌，并在订单中体现",
        "postconditions": "返回订单信息，询问用户是否支付订单",
        "args": {
            "user_id": "用户id",
            "store_id": "商店id",
            "food_ids": "商品id列表",
            "food_cnts": "商品id对应数量列表",
            "address": "外卖配送目标地址",
            "dispatch_time": "外卖订单开始配送的时间（即骑手从商家取餐出发的时间），格式为yyyy-mm-dd HH:MM:SS",
            "attributes": "商品id对应商品规格属性",
            "note": "订单备注（禁止将用户关于时间等需求直接放在备注中），如饮食禁忌信息说明"
        },
        "returns": "如果创建成功，返回订单信息（包含订单id、用户id、商店id、商品id列表、商品数量列表、地址、下单时间、更新时间、订单状态、商品列表、备注），否则返回相关提示信息",
        "tool_type": "WRITE"
    },

    "pay_delivery_order": {
        "description": "在外卖场景下，上文有订单信息，用户表达确认支付，或者重新支付",
        "preconditions": "处于外卖场景，用户表达确认支付，订单创建完成并进入支付环节｜用户表示重新支付",
        "postconditions": "返回支付结果信息",
        "args": {
            "order_id": "订单id"
        },
        "returns": "支付结果信息",
        "tool_type": "WRITE"
    },

    "get_delivery_order_status": {
        "description": "获取订单状态",
        "preconditions": "查询外卖订单状态",
        "postconditions": "返回订单状态信息",
        "args": {
            "order_id": "订单id"
        },
        "returns": "订单状态信息",
        "tool_type": "READ"
    },

    "cancel_delivery_order": {
        "description": "用户取消订单，或者用户取消支付。禁止对处于已取消状态的订单再次取消。",
        "preconditions": "查询外卖订单状态，确保订单状态为非cancelled",
        "postconditions": "返回取消订单结果信息",
        "args": {
            "order_id": "订单id"
        },
        "returns": "取消订单结果信息",
        "tool_type": "WRITE"
    },

    "modify_delivery_order": {
        "description": "修改订单备注信息",
        "preconditions": "上文确定唯一一个外卖order_id，用户需要修改外卖订单备注",
        "postconditions": "输出修改后订单信息，如果订单还未支付则需要用户确认支付",
        "args": {
            "order_id": "订单id",
            "note": "新的订单备注信息"
        },
        "returns": "修改订单备注操作的结果",
        "tool_type": "WRITE"
    },

    "search_delivery_orders": {
        "description": "查询所有外卖订单，返回包含订单ID、订单类型、用户ID、商家ID、总价、下单时间、更新时间、订单状态等信息",
        "preconditions": "按照查询条件查看所有外卖订单",
        "postconditions": "返回所有符合条件外卖订单的详细信息",
        "args": {
            "user_id": "用户ID",
            "status": "订单状态，默认为未支付"
        },
        "returns": "返回所有符合条件的外卖订单详细信息，包括订单ID、订单类型、用户ID、商家ID、总价、下单时间、更新时间、订单状态等信息",
        "tool_type": "READ"
    },

    "get_delivery_order_detail": {
        "description": "根据订单ID查询外卖订单，返回包含订单ID、订单类型、商家ID、配送时间、配送耗时、送达时间、总价、下单时间、更新时间、订单状态和商品列表等详细信息",
        "preconditions": "上文确定唯一一个外卖order_id",
        "postconditions": "返回指定订单详细信息",
        "args": {
            "order_id": "订单id"
        },
        "returns": "指定订单的详细信息，包括订单ID、订单类型、商家ID、配送时间、配送耗时、送达时间、总价、下单时间、更新时间、订单状态和商品列表",
        "tool_type": "READ"
    }    
}

TOOL_DESCRIPTIONS_EN = {
    "longitude_latitude_to_distance": {
        "description": "Calculate the distance between two points based on their longitude and latitude (in meters)",
        "preconditions": "Calculate the distance between two points given their longitude and latitude",
        "postconditions": "Returns the distance between the two points (integer, in meters)",
        "args": {
            "longitude1": "Longitude of the first point",
            "latitude1": "Latitude of the first point",
            "longitude2": "Longitude of the second point",
            "latitude2": "Latitude of the second point"
        },
        "returns": "The distance between the two points (integer, in meters)"
    },
    
    "weather": {
        "description": "Query weather information for a specified address from date_start to date_end",
        "preconditions": "Query weather information for a specified address within a specified date range",
        "postconditions": "Returns weather information",
        "args": {
            "address": "The address to query",
            "date_start": "Start time, format: yyyy-mm-dd",
            "date_end": "End time, format: yyyy-mm-dd"
        },
        "returns": "Weather information"
    },
    
    "address_to_longitude_latitude": {
        "description": "Get longitude and latitude based on an address",
        "preconditions": "Get the corresponding longitude and latitude coordinates for an address",
        "postconditions": "Returns longitude and latitude coordinates",
        "args": {
            "address": "The address to query"
        },
        "returns": "[longitude, latitude]"
    },
    
    "get_date_holiday_info": {
        "description": "Determine if a specific date is a Chinese holiday; if so, return its Chinese name",
        "preconditions": "Determine if a date is a holiday based on the date, and return the holiday name if it is",
        "postconditions": "Returns holiday information",
        "args": {
            "date": "Date, format: yyyy-mm-dd"
        },
        "returns": "Holiday information determination result"
    },
    
    "get_holiday_date": {
        "description": "Get the specific date of a certain holiday in a specified year",
        "preconditions": "Get the specific date of a holiday in a specified year",
        "postconditions": "Returns the date of the holiday",
        "args": {
            "year": "Year",
            "holiday_name": "Holiday name, only supports Chinese description"
        },
        "returns": "The date of the holiday"
    },
    
    "get_user_historical_behaviors": {
        "description": "Get user's basic information and historical behavior preference data, including user ID, home address, work address, and other basic info, as well as detailed consumption habits, preferred categories, price ranges, rating requirements, time preferences, etc., for various scenarios, used for personalized recommendations and service optimization",
        "preconditions": "Get user historical behavior data",
        "postconditions": "Returns user historical behavior information",
        "args": {},
        "returns": "Summary of user historical behavior information"
    },
    
    "get_user_all_orders": {
        "description": "Get all order information for the user",
        "preconditions": "Get all order information for the user",
        "postconditions": "Returns all order information for the user",
        "args": {},
        "returns": "Summary of all user order information"
    },
    
    "get_nearby": {
        "description": "Get information of all nearby stores/commercial venues",
        "preconditions": "Get information of all commercial venues (stores, airports or train stations, hotels, attractions, shops, etc.) within a specified range (in meters)",
        "postconditions": "Returns commercial venue information",
        "args": {
            "longitude": "Longitude",
            "latitude": "Latitude",
            "range": "Range (in meters)"
        },
        "returns": "Store/commercial venue information"
    },
    "delivery_distance_to_time": {
        "description": "Calculate food delivery time (in minutes) based on distance (meters)",
        "preconditions": "Calculate food delivery time based on the distance from the store to the user's address",
        "postconditions": "Returns delivery time (in minutes)",
        "args": {
            "distance": "Distance (in meters)"
        },
        "returns": "Time (in minutes)",
        "tool_type": "GENERIC"
    },

    "get_delivery_store_info": {
        "description": "Get store information, including store id, rating, address, longitude, latitude, tags, and product list",
        "preconditions": "In a food delivery scenario, need to get detailed information of a store",
        "postconditions": "Returns detailed information of the store",
        "args": {
            "store_id": "Store id"
        },
        "returns": "Detailed information of the store",
        "tool_type": "READ"
    },

    "get_delivery_product_info": {
        "description": "Get product information, including product name, product id, store name, store id, product rating, product price, product tags",
        "preconditions": "In a food delivery scenario, need to get detailed information of a product",
        "postconditions": "Returns detailed information of the product",
        "args": {
            "food_id": "Product id"
        },
        "returns": "Detailed information of the product",
        "tool_type": "READ"
    },

    "delivery_store_search_recommand": {
        "description": "In a food delivery scenario, extract keywords describing a store from the user's expression to search for or recommend multiple stores",
        "preconditions": "In a food delivery scenario, get keywords describing a store",
        "postconditions": "Returns a list of stores, guiding the user to select and confirm a store",
        "args": {
            "keywords": "Keywords describing the store"
        },
        "returns": "Structured output of store information",
        "tool_type": "READ"
    },

    "delivery_product_search_recommand": {
        "description": "In a food delivery scenario, extract keywords describing a product from the user's expression to search for or recommend multiple products",
        "preconditions": "In a food delivery scenario, get keywords describing a product",
        "postconditions": "Returns a list of products, guiding the user to select a product and create an order",
        "args": {
            "keywords": "Keywords describing the product"
        },
        "returns": "Structured output of product information",
        "tool_type": "READ"
    },

    "create_delivery_order": {
        "description": "Create a food delivery order. Only supports placing an order from a single store, but multiple products can be ordered from a single store",
        "preconditions": "In a food delivery scenario, a unique store id and one or more product ids are determined, user's dietary restrictions are confirmed, and reflected in the order",
        "postconditions": "Returns order information, asks the user if they want to pay for the order",
        "args": {
            "user_id": "User id",
            "store_id": "Store id",
            "food_ids": "List of product ids",
            "food_cnts": "List of quantities corresponding to product ids",
            "address": "Food delivery destination address",
            "dispatch_time": "The time the delivery order starts dispatching (i.e., when the rider picks up the food from the store and departs), format: yyyy-mm-dd HH:MM:SS",
            "attributes": "Product specification attributes corresponding to product ids",
            "note": "Order notes (do not put user's time-related requirements directly in the notes), such as dietary restriction information"
        },
        "returns": "If creation is successful, returns order information (including order id, user id, store id, product id list, product quantity list, address, order time, update time, order status, product list, notes), otherwise returns relevant prompt information",
        "tool_type": "WRITE"
    },

    "pay_delivery_order": {
        "description": "In a food delivery scenario, given order information from the previous context, the user expresses confirmation to pay, or to re-pay",
        "preconditions": "In a food delivery scenario, the user expresses confirmation to pay, the order is created and enters the payment phase | The user indicates re-payment",
        "postconditions": "Returns payment result information",
        "args": {
            "order_id": "Order id"
        },
        "returns": "Payment result information",
        "tool_type": "WRITE"
    },

    "get_delivery_order_status": {
        "description": "Get order status",
        "preconditions": "Query food delivery order status",
        "postconditions": "Returns order status information",
        "args": {
            "order_id": "Order id"
        },
        "returns": "Order status information",
        "tool_type": "READ"
    },

    "cancel_delivery_order": {
        "description": "User cancels an order, or user cancels payment. It is forbidden to cancel an order that is already in a cancelled state.",
        "preconditions": "Query food delivery order status to ensure the order status is not 'cancelled'",
        "postconditions": "Returns order cancellation result information",
        "args": {
            "order_id": "Order id"
        },
        "returns": "Order cancellation result information",
        "tool_type": "WRITE"
    },

    "modify_delivery_order": {
        "description": "Modify order note information",
        "preconditions": "In the previous context, a unique food delivery order_id is determined, and the user needs to modify the order notes",
        "postconditions": "Outputs modified order information; if the order is not yet paid, it requires the user to confirm payment",
        "args": {
            "order_id": "Order id",
            "note": "New order note information"
        },
        "returns": "Result of the modify order note operation",
        "tool_type": "WRITE"
    },

    "search_delivery_orders": {
        "description": "Query all food delivery orders, returning information including order ID, order type, user ID, store ID, total price, order time, update time, order status, etc.",
        "preconditions": "View all food delivery orders according to query conditions",
        "postconditions": "Returns detailed information of all food delivery orders that meet the conditions",
        "args": {
            "user_id": "User ID",
            "status": "Order status, defaults to unpaid"
        },
        "returns": "Returns detailed information of all food delivery orders that meet the conditions, including order ID, order type, user ID, store ID, total price, order time, update time, order status, etc.",
        "tool_type": "READ"
    },

    "get_delivery_order_detail": {
        "description": "Query a food delivery order based on its ID, returning detailed information including order ID, order type, store ID, delivery time, delivery duration, arrival time, total price, order time, update time, order status, and product list",
        "preconditions": "A unique food delivery order_id is determined in the previous context",
        "postconditions": "Returns detailed information of the specified order",
        "args": {
            "order_id": "Order id"
        },
        "returns": "Detailed information of the specified order, including order ID, order type, store ID, delivery time, delivery duration, arrival time, total price, order time, update time, order status, and product list",
        "tool_type": "READ"
    }    
}
