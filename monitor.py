import requests
import datetime
import os

# ================= 商业化配置区域 =================

# 1. 目标汇率 (低于此值发送全员通知)
TARGET_RATE = 0.048

# 2. PushPlus 群组编码 (刚才在后台填写的那个英文名)
PUSH_TOPIC = "jpy_monitor_vip" 

# 3. 这里的 Token 从环境变量读取，不要修改
# 只有你自己(管理员)的 Token 才有权限向群组发消息
ADMIN_TOKEN = os.environ.get('PUSHPLUS_TOKEN')

# =================================================

def get_current_rate():
    """获取实时汇率"""
    url = "https://api.exchangerate-api.com/v4/latest/JPY"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code == 200:
            return resp.json()['rates']['CNY']
    except Exception as e:
        print(f"Error getting rate: {e}")
    return None

def send_broadcast(rate):
    """向群组发送广播通知"""
    if not ADMIN_TOKEN:
        print("❌ 错误：未配置管理员 Token，无法发送通知")
        return

    url = "http://www.pushplus.plus/send"
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 商业化文案：看起来专业一点
    title = f"📉 汇率触达提醒：{rate}"
    content = (
        f"<b>【日元汇率监控服务】</b><br>"
        f"------------------------<br>"
        f"当前时间：{current_time}<br>"
        f"<b>最新汇率：{rate}</b><br>"
        f"设定阈值：{TARGET_RATE}<br>"
        f"------------------------<br>"
        f"<i>建议：已跌破设定值，请关注买入时机。</i><br>"
        f"<a href='https://finance.sina.com.cn/money/forex/hq/JPYCNY.shtml'>点击查看新浪财经详情</a>"
    )

    params = {
        "token": ADMIN_TOKEN,
        "title": title,
        "content": content,
        "topic": PUSH_TOPIC,  # 关键：发送给群组
        "template": "html"    # 使用 HTML 格式让消息更好看
    }

    try:
        res = requests.get(url, params=params)
        print(f"✅ 广播发送结果: {res.text}")
    except Exception as e:
        print(f"❌ 广播发送失败: {e}")

if __name__ == "__main__":
    print(f"--- 任务开始: {datetime.datetime.now()} ---")
    
    rate = get_current_rate()
    
    if rate:
        print(f"📊 当前汇率: {rate}")
        if rate <= TARGET_RATE:
            print("⚡ 触发阈值，正在发送全员通知...")
            send_broadcast(rate)
        else:
            print(f"💤 未达到阈值 ({TARGET_RATE})，本轮静默。")
    else:
        print("❌ 获取汇率失败，请检查网络或API。")
        
    print("--- 任务结束 ---")

