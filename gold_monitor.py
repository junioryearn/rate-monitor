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

def send_dual_alert(current, high, low, res, msg_mode="ALERT"):
    """
    msg_mode: 
    - ALERT: 触发预警 (红/绿)
    - PULSE: 定时快报 (蓝色)
    - SUMMARY: 收盘总结 (金色)
    """
    if msg_mode == "ALERT" and not res["type"]: return # 非预警模式且无触发则退出

    # 颜色配置
    colors = {"ALERT_BUY": "#52c41a", "ALERT_SELL": "#ff4d4f", "PULSE": "#1890ff", "SUMMARY": "#faad14"}
    
    if msg_mode == "ALERT":
        mode_name = "📉 低吸信号" if res["type"] == "买入" else "📈 高抛信号"
        theme_color = colors["ALERT_BUY"] if res["type"] == "买入" else colors["ALERT_SELL"]
        icon = "⭐" * res["level"]
    elif msg_mode == "PULSE":
        mode_name = "⏲️ 准点快报"
        theme_color = colors["PULSE"]
        icon = "🔔"
    else:
        mode_name = "📊 收盘总结"
        theme_color = colors["SUMMARY"]
        icon = "🏁"

    title = f"{mode_name}: {current}元"
    content = f"""
    <div style="border: 2px solid {theme_color}; padding: 15px; border-radius: 10px; font-family: sans-serif;">
        <h2 style="color: {theme_color}; margin: 0 0 10px 0;">{mode_name} {icon}</h2>
        <p style="font-size: 20px; margin: 5px 0;"><b>{current} 元/克</b></p>
        <div style="background: #f5f5f5; padding: 10px; border-radius: 5px; font-size: 14px;">
            开盘: {low} | 最高: {high}<br>
            <b>日内涨跌: {'+' if res['day_change']>0 else ''}{res['day_change']}%</b>
        </div>
        {f'<div style="margin-top:10px; padding:8px; background:{theme_color}11; border-left:4px solid {theme_color};"><b>建议: {res["advice"]} ({res["rate"]}%)</b></div>' if res['type'] else ''}
        <p style="font-size: 12px; color: #999; margin-top: 10px;">北京时间: {get_beijing_time().strftime('%H:%M:%S')}</p>
    </div>
    """
    requests.get("http://www.pushplus.plus/send", params={
        "token": ADMIN_TOKEN, "title": title, "content": content, "template": "html", "topic": PUSH_TOPIC
    })


if __name__ == "__main__":
    now = get_beijing_time()
    curr_hm = now.hour * 100 + now.minute
    
    if not is_within_trade_session():
        sys.exit(0)

    curr, hi, lo, o = get_gold_full_data()
    if curr:
        res = analyze_market(curr, hi, lo, o)
        
        # --- 消息触发逻辑 ---
        msg_mode = "ALERT" 
        
        # 1. 如果是收盘时间 (15:15 左右)
        if 1510 <= curr_hm <= 1525:
            msg_mode = "SUMMARY"
        
        # 2. 如果是整点快报 (每2小时一次: 10点, 12点, 14点, 22点, 0点)
        # 逻辑：如果是整点后的前15分钟内（GitHub每15分运行一次），则触发快报
        elif now.hour % 2 == 0 and now.minute < 15:
            msg_mode = "PULSE"
        
        # 发送判断
        send_dual_alert(curr, hi, lo, res, msg_mode=msg_mode)
        print(f"[{now.strftime('%H:%M')}] 模式:{msg_mode} 现价:{curr}")

