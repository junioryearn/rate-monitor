import requests
import re
import datetime
import sys
import time
import os

# ================= 基础配置 =================
# 从 GitHub Secrets 获取 Token
ADMIN_TOKEN = os.environ.get('PUSHPLUS_TOKEN')
PUSH_TOPIC = "gold_pro_trading" 

# 预警灵敏度 (百分比)
BUY_LEVELS = [-1.0, -2.5, -4.0]  
SELL_LEVELS = [1.5, 3.0, 5.0]    

def get_beijing_time():
    """获取北京时间"""
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    return utc_now + datetime.timedelta(hours=8)

def is_within_trade_session():
    """
    判断是否在交易时段 (避免深夜打扰)
    周一至周五: 
      早: 09:00-11:30
      午: 13:30-15:30
      晚: 20:00-02:30 (次日)
    """
    now = get_beijing_time()
    current_time = now.hour * 100 + now.minute
    weekday = now.weekday() # 0=周一, 6=周日

    # 周六凌晨 02:35 之后到周日全天不跑
    if weekday == 5 and current_time > 235: return False
    if weekday == 6: return False

    # 简单判断: 早上9点到次日凌晨2点半
    # 注意: GitHub Actions 可能会延迟，放宽一点时间窗口
    is_day_trading = 855 <= current_time <= 1535
    is_night_trading = current_time >= 1955 or current_time <= 240
    
    return is_day_trading or is_night_trading

def get_gold_full_data():
    """获取新浪财经数据"""
    timestamp = int(time.time() * 1000)
    url = f"https://hq.sinajs.cn/rn={timestamp}&list=gds_AU9999"
    headers = {"Referer": "https://finance.sina.com.cn/", "User-Agent": "Mozilla/5.0"}

    try:
        response = requests.get(url, headers=headers, timeout=10)
        content = response.text
        if "gds_AU9999=" not in content: return None, None, None, None

        data_match = re.search(r'gds_AU9999="([^"]+)"', content)
        if not data_match: return None, None, None, None
        
        d = data_match.group(1).split(',')
        # 数据结构: 0:现价, 4:最高, 5:最低, 8:开盘
        current = float(d[0])
        high    = float(d[4])
        low     = float(d[5])
        op      = float(d[8])
        
        # 处理开盘瞬间最高最低为0的情况
        high = current if high == 0 else high
        low = current if low == 0 else low
        
        return current, high, low, op
    except Exception as e:
        print(f"Error: {e}")
        return None, None, None, None

def analyze_market(current, high, low, op):
    """分析涨跌幅"""
    # 避免分母为0
    if high == 0 or low == 0 or op == 0:
        return {"type": None, "level": 0, "rate": 0, "advice": "", "day_change": 0}

    drop_rate = round(((current - high) / high) * 100, 2)
    rise_rate = round(((current - low) / low) * 100, 2)
    day_change = round(((current - op) / op) * 100, 2)
    
    analysis = {"type": None, "level": 0, "rate": 0, "advice": "", "day_change": day_change}

    # 判断买入逻辑
    for i, threshold in enumerate(reversed(BUY_LEVELS)):
        if drop_rate <= threshold:
            level = 3 - i
            advice = ["👀 小跌关注", "✅ 深度回调", "🔥 黄金坑"][level-1]
            analysis.update({"type": "买入", "level": level, "rate": drop_rate, "advice": advice})
            break

    # 判断卖出逻辑
    if not analysis["type"]:
        for i, threshold in enumerate(reversed(SELL_LEVELS)):
            if rise_rate >= threshold:
                level = 3 - i
                advice = ["📈 止盈观察", "💰 建议减仓", "🚀 建议清仓"][level-1]
                analysis.update({"type": "卖出", "level": level, "rate": rise_rate, "advice": advice})
                break

    return analysis

def send_pushplus(current, high, low, op, res, msg_mode):
    """
    msg_mode: 
    - ALERT: 触发阈值 (红/绿)
    - PULSE: 15分钟常规播报 (蓝色)
    - SUMMARY: 收盘总结 (金色)
    """
    
    # 配色方案
    colors = {"BUY": "#52c41a", "SELL": "#ff4d4f", "PULSE": "#1890ff", "SUMMARY": "#faad14"}
    
    # 确定标题和颜色
    if msg_mode == "SUMMARY":
        title_prefix = "🏁 收盘"
        theme_color = colors["SUMMARY"]
    elif msg_mode == "ALERT":
        title_prefix = "📉 机会" if res["type"] == "买入" else "📈 风险"
        theme_color = colors["BUY"] if res["type"] == "买入" else colors["SELL"]
    else: # PULSE
        # 常规播报，根据涨跌微调颜色，或者统一用蓝色
        title_prefix = "🔔 快报"
        theme_color = colors["PULSE"]

    title = f"{title_prefix}: {current}元 ({'+' if res['day_change']>0 else ''}{res['day_change']}%)"
    
    # 构建建议HTML
    advice_html = ""
    if res['type']: 
        advice_html = f'<div style="margin-top:10px; padding:8px; background:{theme_color}11; border-left:4px solid {theme_color};"><b>策略: {res["advice"]} (幅度:{res["rate"]}%)</b></div>'
    elif msg_mode == "PULSE":
        advice_html = f'<div style="margin-top:10px; color:#666; font-size:12px;">当前波动平稳，持续监控中...</div>'

    content = f"""
    <div style="border: 2px solid {theme_color}; padding: 15px; border-radius: 10px; font-family: sans-serif;">
        <h2 style="color: {theme_color}; margin: 0 0 10px 0;">{title}</h2>
        <p style="font-size: 24px; margin: 5px 0; font-weight:bold;">{current} <span style="font-size:14px; color:#666;">元/克</span></p>
        <div style="background: #f5f5f5; padding: 10px; border-radius: 5px; font-size: 14px; line-height: 1.6;">
            开盘: {op} | 昨收: N/A<br>
            最高: <span style="color:#ff4d4f">{high}</span> | 最低: <span style="color:#52c41a">{low}</span><br>
            <b>日内涨跌: {'+' if res['day_change']>0 else ''}{res['day_change']}%</b>
        </div>
        {advice_html}
        <p style="font-size: 12px; color: #999; margin-top: 10px; text-align:right;">
            北京时间: {get_beijing_time().strftime('%H:%M:%S')}
        </p>
    </div>
    """
    
    if not ADMIN_TOKEN:
        print("❌ 未配置 PUSHPLUS_TOKEN")
        return

    try:
        req = requests.get("http://www.pushplus.plus/send", params={
            "token": ADMIN_TOKEN, 
            "title": title, 
            "content": content, 
            "template": "html", 
            "topic": PUSH_TOPIC
        })
        print(f"推送结果: {req.text}")
    except Exception as e:
        print(f"推送异常: {e}")

if __name__ == "__main__":
    now = get_beijing_time()
    curr_hm = now.hour * 100 + now.minute
    
    # 1. 检查是否在交易时间 (不在交易时间直接退出，不发送)
    if not is_within_trade_session():
        print("💤 非交易时段，休眠中...")
        sys.exit(0)

    # 2. 获取数据
    curr, hi, lo, o = get_gold_full_data()
    
    if curr:
        # 3. 分析数据
        res = analyze_market(curr, hi, lo, o)
        
        # 4. 决策发送模式
        msg_mode = "PULSE" # 默认模式：每15分钟的常规快报
        
        # 判定收盘总结 (下午3点10分到3点30分之间)
        if 1510 <= curr_hm <= 1530:
            msg_mode = "SUMMARY"
        # 判定是否触发强预警 (如果有预警，覆盖常规快报，显示为警告色)
        elif res["type"]:
            msg_mode = "ALERT"
            
        print(f"[{now.strftime('%H:%M:%S')}] 模式:{msg_mode} 价格:{curr}")
        
        # 5. 发送消息 (无论何种模式都发送，除非Token为空)
        send_pushplus(curr, hi, lo, o, res, msg_mode)
    else:
        print("❌ 获取金价数据失败")
