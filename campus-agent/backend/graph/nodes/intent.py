def intent_node(state):
    """
    意图识别节点：根据关键词判断用户问题要走哪个功能模块。
    """

    text = state.get("input", "")
    text_lower = text.lower()

    weather_keywords = [
        "天气", "温度", "下雨", "气温", "热不热", "冷不冷", "weather"
    ]

    if any(word in text_lower for word in weather_keywords):
        return {
            "intent": "weather"
        }

    news_keywords = [
        "新闻", "头条", "热点", "资讯", "时事", "最新消息",
        "今日新闻", "今天新闻", "news"
    ]

    if any(word in text_lower for word in news_keywords):
        return {
            "intent": "news"
        }

    rag_keywords = [
        "广州应用科技学院", "广应科", "学校", "宿舍", "课程", "选课", "图书馆", "教务",
        "考试", "成绩", "专业", "老师", "校区", "校园", "食堂",
        "通知", "安排", "活动", "讲座", "会议", "报名", "实践学时",
        "教学楼", "教室", "j1", "a101",
        "奖学金", "助学金", "资助", "评优", "贫困生", "困难认定",
        "国家奖学金", "国家励志奖学金"
    ]

    if any(word in text_lower for word in rag_keywords):
        return {
            "intent": "rag"
        }

    return {
        "intent": "chat"
    }
3333