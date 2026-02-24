#!/usr/bin/env python3
import os
import json
import time
import random
import logging
import requests
import re
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager

# ---------------------------
# 日志系统
# ---------------------------
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------
# 单账号签到类
# ---------------------------
class LeaflowCheckin:
    def __init__(self, email, password):
        self.email = email
        self.password = password
        self.driver = None

    # ---------------------------
    # Driver 初始化
    # ---------------------------
    def setup_driver(self):
        chrome_options = Options()
        chrome_options.add_argument("--headless=new")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-blink-features=AutomationControlled")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument(
            "user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=chrome_options)
        self.driver.set_page_load_timeout(30)
        return self.driver

    # ---------------------------
    # 通用等待
    # ---------------------------
    def wait_click(self, by, value, timeout=15):
        return WebDriverWait(self.driver, timeout).until(
            EC.element_to_be_clickable((by, value))
        )

    def wait_visible(self, by, value, timeout=15):
        return WebDriverWait(self.driver, timeout).until(
            EC.visibility_of_element_located((by, value))
        )

    def human_delay(self, min_sec=2.0, max_sec=5.0):
        time.sleep(random.uniform(min_sec, max_sec))

    # ---------------------------
    # 登录流程（含弹窗关闭 + JS hack）
    # ---------------------------
    def login(self):
        logger.info(f"开始登录：{self.email}")
        self.driver.get("https://leaflow.example.com/login")
        self.human_delay()

        # 关闭弹窗
        try:
            self.driver.execute_script("document.body.click()")
            self.human_delay(1,2)
        except:
            pass

        # JS hack 防webdriver检测
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        # 输入邮箱密码
        email_input = self.wait_visible(By.NAME, "email")
        password_input = self.wait_visible(By.NAME, "password")
        email_input.clear()
        email_input.send_keys(self.email)
        password_input.clear()
        password_input.send_keys(self.password)
        self.human_delay()

        # 点击登录
        login_btn = self.wait_click(By.XPATH, "//button[contains(text(),'登录')]")
        login_btn.click()
        self.wait_visible(By.TAG_NAME, "body")
        logger.info("登录成功")

    # ---------------------------
    # 获取余额
    # ---------------------------
    def get_balance(self):
        try:
            self.driver.get("https://leaflow.example.com/dashboard")
            self.human_delay()
            body_text = self.driver.find_element(By.TAG_NAME,"body").text
            match = re.search(r"(?:¥|￥|元)\s?([\d\.]+)", body_text)
            if match:
                balance = match.group(1)
                return f"{balance}元"
            return "未知"
        except Exception as e:
            logger.warning(f"获取余额失败: {e}")
            return "未知"

    # ---------------------------
    # 签到流程
    # ---------------------------
    def checkin(self):
        logger.info("开始签到")
        self.driver.get("https://leaflow.example.com/dashboard")
        self.human_delay()

        try:
            checkin_btn = self.wait_click(By.XPATH, "//button[contains(text(),'签到')]")
            btn_text = checkin_btn.text.strip()
            if "已签到" in btn_text:
                return "今日已签到"
            checkin_btn.click()
            self.human_delay()
            # 获取签到结果
            body_text = self.driver.find_element(By.TAG_NAME,"body").text
            for kw in ["成功","签到","获得","完成","连续签到"]:
                if kw in body_text:
                    return kw
            return "签到完成"
        except TimeoutException:
            return "今日已签到或按钮未找到"

    # ---------------------------
    # 安全执行（重试机制）
    # ---------------------------
    def safe_execute(self, func, retries=3):
        for attempt in range(retries):
            try:
                return func()
            except Exception as e:
                logger.warning(f"第 {attempt+1} 次失败: {e}")
                time.sleep(3)
        raise Exception("超过最大重试次数")

    # ---------------------------
    # 执行主流程
    # ---------------------------
    def run(self):
        try:
            self.setup_driver()
            self.safe_execute(self.login)
            result = self.safe_execute(self.checkin)
            balance = self.safe_execute(self.get_balance)
            return True, result, balance
        except Exception as e:
            return False, str(e), "未知"
        finally:
            if self.driver:
                self.driver.quit()

# ---------------------------
# 多账号管理
# ---------------------------
def load_accounts():
    accounts_env = os.getenv("LEAFLOW_ACCOUNTS")
    if accounts_env:
        return json.loads(accounts_env)
    email = os.getenv("LEAFLOW_EMAIL")
    password = os.getenv("LEAFLOW_PASSWORD")
    if email and password:
        return [{"email": email, "password": password}]
    raise Exception("未提供账号信息")

# ---------------------------
# Telegram 通知
# ---------------------------
def send_telegram(results):
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        logger.warning("未配置 Telegram")
        return
    current_date = datetime.now().strftime("%Y/%m/%d")
    message = f"🎁 Leaflow自动签到通知 - {current_date}\n\n"
    for email, success, result, balance in results:
        message += f"账号：{email}\n"
        status = "✅" if success else "❌"
        message += f"{status}  {result}\n💰 余额：{balance}\n\n"
    try:
        requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json={"chat_id": chat_id, "text": message})
    except Exception as e:
        logger.error(f"Telegram发送失败: {e}")

# ---------------------------
# 主入口
# ---------------------------
if __name__ == "__main__":
    accounts = load_accounts()
    results = []
    for acc in accounts:
        checker = LeaflowCheckin(acc["email"], acc["password"])
        success, result, balance = checker.run()
        results.append((acc["email"], success, result, balance))
    send_telegram(results)
    overall_success = all(s for _,s,_,_ in results)
    if overall_success:
        logger.info("全部账号签到成功")
        exit(0)
    else:
        logger.error("存在失败账号")
        exit(1)
