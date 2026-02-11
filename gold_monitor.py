import requests
import re
import datetime
import sys
import time
import os

# ================= 商业化双向预警配置 =================
PUSH_TOPIC = "gold_pro_trading" 
ADMIN_TOKEN = os.environ.get('PUSHPLUS_TOKEN')

# 预警灵敏度 (百分比)
BUY_LEVELS = [-1.0, -2.5, -4.0]  # 跌破最高点多少%提醒买入
SELL_LEVELS = [1.5, 3.0, 5.0]    # 涨过最低点多少%提醒卖出
# =====================================================

def get_beijing_time():
    """获取精准的北京时间，解决 DeprecationWarning 警告"""
    # 使用时区感知对象获取 UTC 时间，再转换为北京时间 (UTC+8)
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    beijing_now = utc_now + datetime.timedelta(hours=8)
    return beijing_now

def is_within_trade_session():
    """判断当前是否在上海金交易时段 (北京时间)"""
    now = get_beijing_time()
    current_time = now.hour * 100 + now.minute
    weekday = now.weekday()  # 0=周一, 6=周日

    # 周六凌晨 02:35 之后到周日全天不跑 (处理周五夜盘延伸到周六凌晨的情况)
    if weekday == 5 and current_time > 235: return False
    if weekday == 6: return False

    # 上海金标准交易时段
    is_morning = 900 <= current_time <= 1135   # 上午盘
    is_afternoon = 1330 <= current_time <= 1535 # 下午盘
    is_night = current_time >= 2000 or current_time <= 235 # 夜盘
    
    return is_morning or is_afternoon or is_night

def get_gold_full_data():
    """从新浪 API 获取 Au99.99 实时行情"""
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
        
        # 字段映射 (基于实测数据):
        # 0:当前价, 4:最高, 5:最低, 8:开盘
        current = float(d[0])
        high    = float(d[4])
        low     = float(d[5])
        op      = float(d[8])
        
        # 容错处理
        high = current if high == 0 else high
        low = current if low == 0 else low
        
        return current, high, low, op
    except Exception as e:
        print(f"❌ 数据解析异常: {e}")
        return None, None, None, None

def analyze_market(current, high, low, op):
    """多维度分析行情趋势"""
    # 核心算法：回撤与反弹计算
    drop_rate = round(((current - high) / high) * 100, 2)
    rise_rate = round(((current - low) / low) * 100, 2)
    day_change = round(((current - op) / op) * 100, 2)
    
    analysis = {"type": None, "level": 0, "rate": 0, "advice": "", "day_change": day_change}

    # 买入预警逻辑 (回调买入)
    for i, threshold in enumerate(reversed(BUY_LEVELS)):
        if drop_rate <= threshold:
            level = 3 - i
            advice = ["👀 行情微调，建议关注", "✅ 深度回调，建议建仓", "🔥 极端超跌，建议重仓"][level-1]
            analysis.update({"type": "买入", "level": level, "rate": drop_rate, "advice": advice})
            break

    # 卖出预警逻辑 (冲高减仓)
    if not analysis["type"]:
        for i, threshold in enumerate(reversed(SELL_LEVELS)):
            if rise_rate >= threshold:
                level = 3 - i
                advice = ["📈 冲高受阻，注意止盈", "💰 获利丰厚，建议减仓", "🚀 涨幅过载，建议清仓"][level-1]
                analysis.update({"type": "卖出", "level": level, "rate": rise_rate, "advice": advice})
                break

    return analysis

def send_dual_alert(current, high, low, res):
    """发送中文美化预警消息"""
    if not res["type"]: return

    direction = "📉 低吸信号" if res["type"] == "买入" else "📈 高抛信号"
    # 红色代表冲高卖出，绿色代表下跌买入
    theme_color = "#ff4d4f" if res["type"] == "卖出" else "#52c41a"
    stars = "⭐" * res["level"]
    
    title = f"{direction} (等级 {res['level']}): {current}元"
    
    # 构建 HTML 消息
    content = f"""
    <div style="border: 2px solid {theme_color}; padding: 15px; border-radius: 10px; font-family: 'Microsoft YaHei', sans-serif;">
        <h2 style="color: {theme_color}; margin-top: 0; border-bottom: 1px solid #eee; padding-bottom: 10px;">
            {direction} {stars}
        </h2>
        <p style="font-size: 16px;"><b>当前实时金价：</b><span style="font-size: 24px; color: {theme_color};">{current}</span> 元/克</p>
        <div style="background-color: #f9f9f9; padding: 10px; border-radius: 5px; line-height: 1.8;">
            <b>📊 交易数据：</b><br>
            今日开盘：{low} 元<br>
            今日最高：{high} 元<br>
            日内涨跌：{res['day_change']}%
        </div>
        <div style="margin-top: 15px; padding: 10px; background-color: {theme_color}11; border-left: 5px solid {theme_color};">
            <b>💡 触发变动：{res['rate']}%</b><br>
            <b>🎯 操作建议：{res['advice']}</b>
        </div>
        <p style="font-size: 12px; color: #999; margin-top: 15px;">北京时间: {get_beijing_time().strftime('%Y-%m-%d %H:%M:%S')}</p>
    </div>
    """

    params = {
        "token": ADMIN_TOKEN, "title": title, "content": content,
        "topic": PUSH_TOPIC, "template": "html"
    }
    
    try:
        requests.get("http://www.pushplus.plus/send", params=params)
        print(f"✅ 微信预警已发送：{res['type']} 等级 {res['level']}")
    except Exception as e:
        print(f"❌ 预警发送失败: {e}")

if __name__ == "__main__":
    now_bt = get_beijing_time()
    
    print("="*45)
    print(f"🚀 上海金 Au99.99 实时监控系统")
    print(f"⏰ 当前时间: {now_bt.strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*45)

    # 1. 交易时间校验
    if not is_within_trade_session():
        print("💡 提示：当前处于休市时段，程序进入静默模式。")
        sys.exit(0)

    # 2. 数据采集
    curr, hi, lo, o = get_gold_full_data()
    
    if curr:
        # 3. 分析行情
        result = analyze_market(curr, hi, lo, o)
        
        # 4. 终端中文显示优化
        change_label = "上涨" if result['day_change'] >= 0 else "下跌"
        change_icon = "🔺" if result['day_change'] >= 0 else "🔻"
        
        print(f"💰 [当前价格]: {curr} 元/克")
        print(f"📊 [日内涨跌]: {change_icon} {change_label} {abs(result['day_change'])}%")
        print(f"📈 [今日高低]: {lo} - {hi}")
        print(f"🛡️ [策略状态]: {result['type'] if result['type'] else '观察中 (持仓无变动)'}")
        
        # 5. 执行预警
        send_dual_alert(curr, hi, lo, result)
        print("-" * 45)
    else:
        print("📢 提示：未能获取到实时行情，可能因法定节假日休市或网络波动。")
