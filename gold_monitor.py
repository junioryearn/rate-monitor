import requests
import re
import datetime
import sys
import time
import os

# ================= 商业化双向预警配置 =================
ADMIN_TOKEN = os.environ.get('PUSHPLUS_TOKEN')
PUSH_TOPIC = "gold_pro_trading" 

# 预警灵敏度 (百分比)
BUY_LEVELS = [-1.0, -2.5, -4.0]  # 跌破最高点多少%提醒买入
SELL_LEVELS = [1.5, 3.0, 5.0]    # 涨过最低点多少%提醒卖出
# =====================================================

def get_beijing_time():
    """获取精准的北京时间，规避 Python 3.12 弃用警告"""
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    beijing_now = utc_now + datetime.timedelta(hours=8)
    return beijing_now

def is_within_trade_session():
    """双保险：判断当前是否在上海金交易时段"""
    now = get_beijing_time()
    current_time = now.hour * 100 + now.minute
    weekday = now.weekday()

    # 周六凌晨 02:35 之后到周日全天不跑
    if weekday == 5 and current_time > 235: return False
    if weekday == 6: return False

    is_morning = 900 <= current_time <= 1135
    is_afternoon = 1330 <= current_time <= 1535
    is_night = current_time >= 2000 or current_time <= 235
    
    return is_morning or is_afternoon or is_night

def get_gold_full_data():
    """从新浪 API 抓取实时数据"""
    timestamp = int(time.time() * 1000)
    url = f"https://hq.sinajs.cn/rn={timestamp}&list=gds_AU9999"
    headers = {
        "Referer": "https://finance.sina.com.cn/futures/quotes/AU9999.shtml",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        content = response.text
        if "gds_AU9999=" not in content or '""' in content:
            return None, None, None, None

        data_match = re.search(r'gds_AU9999="([^"]+)"', content)
        if not data_match: return None, None, None, None
        
        d = data_match.group(1).split(',')
        current = float(d[0])
        high    = float(d[4])
        low     = float(d[5])
        op      = float(d[8])
        
        high = current if high == 0 else high
        low = current if low == 0 else low
        
        return current, high, low, op
    except Exception as e:
        print(f"❌ 数据解析异常: {e}")
        return None, None, None, None

def analyze_market(current, high, low, op):
    """日内波动算法"""
    drop_rate = round(((current - high) / high) * 100, 2)
    rise_rate = round(((current - low) / low) * 100, 2)
    day_change = round(((current - op) / op) * 100, 2)
    
    analysis = {"type": None, "level": 0, "rate": 0, "advice": "", "day_change": day_change}

    for i, threshold in enumerate(reversed(BUY_LEVELS)):
        if drop_rate <= threshold:
            level = 3 - i
            advice = ["👀 行情微调，建议关注", "✅ 深度回调，建议建仓", "🔥 极端超跌，建议重仓"][level-1]
            analysis.update({"type": "买入", "level": level, "rate": drop_rate, "advice": advice})
            break

    if not analysis["type"]:
        for i, threshold in enumerate(reversed(SELL_LEVELS)):
            if rise_rate >= threshold:
                level = 3 - i
                advice = ["📈 冲高受阻，注意止盈", "💰 获利丰厚，建议减仓", "🚀 涨幅过载，建议清仓"][level-1]
                analysis.update({"type": "卖出", "level": level, "rate": rise_rate, "advice": advice})
                break

    return analysis

def send_dual_alert(current, high, low, res):
    """PushPlus HTML 微信预警"""
    if not res["type"]: return
    if not ADMIN_TOKEN:
        print("⚠️ 未检测到 Token，跳过消息发送")
        return

    direction = "📉 低吸信号" if res["type"] == "买入" else "📈 高抛信号"
    theme_color = "#ff4d4f" if res["type"] == "卖出" else "#52c41a"
    stars = "⭐" * res["level"]
    
    title = f"{direction} (等级 {res['level']}): {current}元"
    content = f"""
    <div style="border: 2px solid {theme_color}; padding: 15px; border-radius: 10px;">
        <h2 style="color: {theme_color};">{direction} {stars}</h2>
        <p><b>当前价格：{current} 元/克</b></p>
        <hr/>
        <p>今日最高：{high} | 今日最低：{low} | 日内涨跌：{res['day_change']}%</p>
        <div style="background: {theme_color}11; padding: 10px; border-left: 5px solid {theme_color};">
            <b>触发变动：{res['rate']}%</b><br>
            <b>操作建议：{res['advice']}</b>
        </div>
    </div>
    """

    params = {"token": ADMIN_TOKEN, "title": title, "content": content, "topic": PUSH_TOPIC, "template": "html"}
    try:
        requests.get("http://www.pushplus.plus/send", params=params)
        print(f"✅ 预警已发送：{res['type']} 等级 {res['level']}")
    except Exception as e:
        print(f"❌ 发送失败: {e}")

if __name__ == "__main__":
    now_bt = get_beijing_time()
    print(f"{'='*30}\n🚀 监控启动: {now_bt.strftime('%Y-%m-%d %H:%M:%S')}")

    if not is_within_trade_session():
        print("⏰ 非交易时段，脚本静默。")
        sys.exit(0)

    curr, hi, lo, o = get_gold_full_data()
    if curr:
        result = analyze_market(curr, hi, lo, o)
        print(f"💰 当前价格: {curr} | 日内涨跌: {result['day_change']}%")
        send_dual_alert(curr, hi, lo, result)
    else:
        print("📢 未能获取有效数据。")
    print(f"{'='*30}")
