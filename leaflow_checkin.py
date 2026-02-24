#!/usr/bin/env python3
"""
Leaflow 多账号企业级自动签到脚本
多账号格式：LEAFLOW_ACCOUNTS="邮箱1:密码1,邮箱2:密码2"
单账号 fallback：LEAFLOW_EMAIL + LEAFLOW_PASSWORD
"""
import os, time, logging, requests, re
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class LeaflowAutoCheckin:
    def __init__(self, email, password):
        self.email = email
        self.password = password
        self.telegram_bot_token = os.getenv('TELEGRAM_BOT_TOKEN', '')
        self.telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID', '')
        self.driver = None
        self.setup_driver()

    def setup_driver(self):
        options = Options()
        if os.getenv('GITHUB_ACTIONS'):
            options.add_argument('--headless')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--disable-gpu')
            options.add_argument('--window-size=1920,1080')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option('useAutomationExtension', False)
        self.driver = webdriver.Chrome(options=options)
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    def login(self):
        self.driver.get("https://leaflow.net/login")
        time.sleep(3)
        try:
            email_input = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='email'], input[type='text']"))
            )
            email_input.clear()
            email_input.send_keys(self.email)
            pwd_input = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='password']"))
            )
            pwd_input.clear()
            pwd_input.send_keys(self.password)
            submit_btn = self.driver.find_element(By.CSS_SELECTOR, "button[type='submit']")
            submit_btn.click()
            WebDriverWait(self.driver, 20).until(lambda d: "dashboard" in d.current_url or "login" not in d.current_url)
            logger.info(f"{self.email} 登录成功")
            return True
        except Exception as e:
            logger.error(f"{self.email} 登录失败: {e}")
            return False

    def checkin(self):
        self.driver.get("https://checkin.leaflow.net")
        time.sleep(2)
        try:
            btn = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "button.checkin-btn"))
            )
            text = btn.text
            if "已签到" in text:
                return "今日已签到"
            btn.click()
            time.sleep(2)
            return "签到完成"
        except:
            return "签到按钮未找到或已签到"

    def get_balance(self):
        try:
            self.driver.get("https://leaflow.net/dashboard")
            time.sleep(2)
            body_text = self.driver.find_element(By.TAG_NAME, "body").text
            m = re.findall(r"(?:¥|￥|元)\s?(\d+\.?\d*)", body_text)
            return m[0]+"元" if m else "未知"
        except:
            return "未知"

    def send_telegram(self, result, balance):
        if not self.telegram_bot_token or not self.telegram_chat_id:
            return
        masked_email = self.email  # 企业版显示全邮箱
        msg = f"账号：{masked_email}\n签到结果：{result}\n余额：{balance}"
        requests.post(f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage",
                      data={"chat_id": self.telegram_chat_id, "text": msg})

    def run(self):
        try:
            if self.login():
                result = self.checkin()
                balance = self.get_balance()
                logger.info(f"{self.email} -> {result}, 余额: {balance}")
                self.send_telegram(result, balance)
                return True
            return False
        finally:
            if self.driver: self.driver.quit()


class MultiAccountManager:
    def __init__(self):
        self.accounts = self.load_accounts()

    def load_accounts(self):
        accounts = []
        env_accounts = os.getenv('LEAFFLOW_ACCOUNTS', '')
        if env_accounts:
            for pair in env_accounts.split(','):
                if ':' in pair:
                    email, pwd = pair.split(':',1)
                    accounts.append({'email':email.strip(),'password':pwd.strip()})
        elif os.getenv('LEAFFLOW_EMAIL') and os.getenv('LEAFLOW_PASSWORD'):
            accounts.append({'email':os.getenv('LEAFLOW_EMAIL'),'password':os.getenv('LEAFLOW_PASSWORD')})
        if not accounts:
            raise ValueError("未找到账号配置")
        return accounts

    def run_all(self):
        for acc in self.accounts:
            LeaflowAutoCheckin(acc['email'], acc['password']).run()


def main():
    MultiAccountManager().run_all()


if __name__=="__main__":
    main()
