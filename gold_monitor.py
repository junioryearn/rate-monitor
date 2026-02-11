import requests
import re
import os
import datetime

# ================= 商业化双向预警配置 =================
PUSH_TOPIC = "gold_pro_trading" 
ADMIN_TOKEN = os.environ.get('PUSHPLUS_TOKEN')

# 预警灵敏度 (百分比)
BUY_LEVELS = [-1.0, -2.5, -4.0]  # 跌破最高点多少%提醒买入
SELL_LEVELS = [1.5, 3.0, 5.0]    # 涨过最低点多少%提醒卖出
# =====================================================

def is_within_trade_session():
    """精准判断当前是否在上海金交易时段内"""
    now = datetime.datetime.now()
    # 转换成 HHMM 格式的数字，方便比较 (例如 09:30 变成 930)
    current_time = now.hour * 100 + now.minute
    
    # 周六、周日全天不跑 (周六凌晨的夜盘已在 YAML 逻辑中处理)
    if now.weekday() >= 5:
        return False

    # 上海金精准交易时间段 (北京时间):
    # 1. 上午：09:00 - 11:35 (多给5分钟收尾)
    # 2. 下午：13:30 - 15:35
    # 3. 夜盘：20:00 - 02:35 (跨天)
    
    is_morning = 900 <= current_time <= 1135
    is_afternoon = 1330 <= current_time <= 1535
    is_night = current_time >= 2000 or current_time <= 235
    
    return is_morning or is_afternoon or is_night

def get_gold_full_data():
    """从新浪获取：当前价[1], 开盘价[2], 最高价[3], 最低价[4]"""
    url = "https://hq.sinajs.cn/list=goldsse"
    headers = {"Referer": "http://finance.sina.com.cn"}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        data_str = re.search(r'goldsse="([^"]+)"', resp.text).group(1)
        d = data_str.split(',')
        # 返回：当前, 最高, 最低, 开盘
        return float(d[1]), float(d[3]), float(d[4]), float(d[2])
    except Exception as e:
        print(f"数据获取失败: {e}")
        return None, None, None, None

def analyze_market(current, high, low, op):
    """核心算法：判断挡位和买卖方向"""
    # 1. 计算回撤 (相对于今日高点)
    drop_rate = round(((current - high) / high) * 100, 2)
    # 2. 计算反弹 (相对于今日低点)
    rise_rate = round(((current - low) / low) * 100, 2)
    
    msg = {"type": None, "level": 0, "rate": 0, "advice": ""}

    # 判断买入逻辑 (回撤)
    if drop_rate <= BUY_LEVELS[2]:
        msg.update({"type": "BUY", "level": 3, "rate": drop_rate, "advice": "🔥 极端捡漏机会，建议重仓入场！"})
    elif drop_rate <= BUY_LEVELS[1]:
        msg.update({"type": "BUY", "level": 2, "rate": drop_rate, "advice": "✅ 日内深度回调，刚需可以分批买入。"})
    elif drop_rate <= BUY_LEVELS[0]:
        msg.update({"type": "BUY", "level": 1, "rate": drop_rate, "advice": "👀 行情开始松动，建议入场关注。"})

    # 判断卖出逻辑 (涨幅) - 如果已经触发买入就不再重复判断卖出
    if not msg["type"]:
        if rise_rate >= SELL_LEVELS[2]:
            msg.update({"type": "SELL", "level": 3, "rate": rise_rate, "advice": "🚀 获利盘巨大！建议全量清仓，落袋为安。"})
        elif rise_rate >= SELL_LEVELS[1]:
            msg.update({"type": "SELL", "level": 2, "rate": rise_rate, "advice": "💰 涨势喜人，建议减仓 50% 锁定利润。"})
        elif rise_rate >= SELL_LEVELS[0]:
            msg.update({"type": "SELL", "level": 1, "rate": rise_rate, "advice": "📈 正在上行，可设置止盈位继续持有。"})

    return msg

def send_dual_alert(current, high, low, analysis):
    if not analysis["type"]: return # 无触发不发消息

    url = "http://www.pushplus.plus/send"
    direction = "📉【回调提醒】" if analysis["type"] == "BUY" else "📈【冲高提醒】"
    level_stars = "⭐" * analysis["level"]
    
    title = f"{direction} 等级:{level_stars} ({current})"
    content = (
        f"<b>{direction} 实时预警系统</b><br>"
        f"------------------------<br>"
        f"实时价格：<b>{current} 元/克</b><br>"
        f"今日高位：{high} | 今日低位：{low}<br>"
        f"------------------------<br>"
        f"<b>变动幅度：{analysis['rate']}%</b><br>"
        f"<b>预警等级：{level_stars}</b><br>"
        f"<b>操作建议：{analysis['advice']}</b><br>"
        f"------------------------<br>"
        f"<i>💡 提示：本监控基于日内波动算法，仅供参考。</i>"
    )

    params = {
        "token": ADMIN_TOKEN, "title": title, "content": content,
        "topic": PUSH_TOPIC, "template": "html"
    }
    requests.get(url, params=params)
    print(f"通知已发送：{analysis['type']} Level {analysis['level']}")

if __name__ == "__main__":
    # 1. 首先检查是否在交易时段
    if not is_within_trade_session():
        print(f"⏰ 当前时间 {datetime.datetime.now().strftime('%H:%M')} 为休市时段，程序静默退出。")
        sys.exit(0)

    # 2. 如果在交易时段，尝试获取数据
    current, high, low, op = get_gold_full_data()
    
    # 3. 再次兜底：如果接口返回空 (比如法定节假日)，也退出
    if current is None or current == 0:
        print("📢 接口未返回数据，今日可能为法定节假日休市。")
        sys.exit(0)

    # 4. 正常执行逻辑
    res = analyze_market(current, high, low, op)
    send_dual_alert(current, high, low, res)
