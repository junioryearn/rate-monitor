import requests
import datetime
import os  # 新增：引入系统库

# ================= 配置区域 =================
# 1. 从环境变量获取 Token (这样更安全)
# 如果本地运行报错，可以在这里填入默认值，或者在电脑环境变量里设置
try:
    USER_TOKEN = os.environ['PUSHPLUS_TOKEN']
except KeyError:
    USER_TOKEN = "如果你在本地测试，可以暂时填这里，但在GitHub上不要填"

# 2. 设置目标汇率 (当汇率低于这个数字时提醒)
TARGET_RATE = 0.048 

# ================= 核心逻辑 =================

def get_exchange_rate():
    """获取 JPY 对 CNY 的实时汇率"""
    # 这是一个免费公开的 API，不需要 Key
    url = "https://api.exchangerate-api.com/v4/latest/JPY"
    
    try:
        # 发送请求
        response = requests.get(url)
        # 检查网络连接是否正常 (状态码 200)
        if response.status_code == 200:
            data = response.json()
            # 获取 CNY 的汇率
            current_rate = data['rates']['CNY']
            return current_rate
        else:
            print("❌ 获取汇率失败，接口状态码:", response.status_code)
            return None
    except Exception as e:
        print(f"❌ 发生错误: {e}")
        return None

def send_pushplus_notification(rate):
    """发送微信通知"""
    url = "http://www.pushplus.plus/send"
    
    # 获取当前时间
    now_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # 构造通知内容
    title = "汇率提醒：日元已跌破目标价！"
    content = f"当前时间：{now_time}<br>当前汇率：{rate}<br>设定目标：{TARGET_RATE}<br>快去查看！"
    
    # 发送请求的参数
    params = {
        "token": USER_TOKEN,
        "title": title,
        "content": content
    }
    
    try:
        requests.get(url, params=params)
        print("✅ 微信通知已发送！")
    except Exception as e:
        print(f"❌ 发送通知失败: {e}")

# ================= 主程序入口 =================

if __name__ == "__main__":
    print("正在查询汇率...")
    
    # 1. 获取汇率
    rate = get_exchange_rate()
    
    if rate is not None:
        print(f"当前 JPY/CNY 汇率: {rate}")
        
        # 2. 判断是否满足条件
        if rate <= TARGET_RATE:
            print(f"⚡ 汇率 ({rate}) 低于或等于目标值 ({TARGET_RATE})，准备发送通知...")
            send_pushplus_notification(rate)
        else:
            print(f"汇率 ({rate}) 高于目标值 ({TARGET_RATE})，无需通知。")