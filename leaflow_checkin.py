#!/usr/bin/env python3
"""
Leaflow 企业级稳定增强版自动签到脚本
支持多账号/单账号，Telegram 通知，直接读取 Secrets，无文件生成
"""

import os, time, logging, requests
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains

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
        chrome_options = Options()
        if os.getenv('GITHUB_ACTIONS'):
            chrome_options.add_argument('--headless')
            chrome_options.add_argument('--no-sandbox')
            chrome_options.add_argument('--disable-dev-shm-usage')
            chrome_options.add_argument('--disable-gpu')
            chrome_options.add_argument('--window-size=1920,1080')
        chrome_options.add_argument('--disable-blink-features=AutomationControlled')
        chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
        chrome_options.add_experimental_option('useAutomationExtension', False)
        self.driver = webdriver.Chrome(options=chrome_options)
        self.driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    def close_popup(self):
        try:
            time.sleep(2)
            actions = ActionChains(self.driver)
            actions.move_by_offset(10,10).click().perform()
        except: pass

    def wait_for(self, by, value, timeout=10):
        return WebDriverWait(self.driver, timeout).until(EC.presence_of_element_located((by,value)))

    def login(self):
        logger.info(f"[{self.email}] 开始登录")
        self.driver.get("https://leaflow.net/login")
        time.sleep(3)
        self.close_popup()
        # 邮箱
        email_input = self.wait_for(By.CSS_SELECTOR, "input[type='email'],input[type='text']")
        email_input.clear()
        email_input.send_keys(self.email)
        # 密码
        password_input = self.wait_for(By.CSS_SELECTOR, "input[type='password']")
        password_input.clear()
        password_input.send_keys(self.password)
        # 登录按钮
        login_btn = self.wait_for(By.CSS_SELECTOR, "button[type='submit'],input[type='submit']")
        login_btn.click()
        WebDriverWait(self.driver, 15).until(lambda d: "dashboard" in d.current_url or "login" not in d.current_url)
        logger.info(f"[{self.email}] 登录成功")

    def get_balance(self):
        try:
            self.driver.get("https://leaflow.net/dashboard")
            time.sleep(2)
            page_text = self.driver.find_element(By.TAG_NAME, "body").text
            import re
            match = re.findall(r'(¥|￥)?\d+\.?\d*', page_text)
            if match: return match[0]
            return "未知"
        except: return "未知"

    def checkin(self):
        self.driver.get("https://checkin.leaflow.net")
        time.sleep(3)
        try:
            btn = self.driver.find_element(By.XPATH, "//button[contains(text(),'签到') or contains(text(),'Checkin')]")
            if "已签到" in btn.text:
                return "今日已签到"
            btn.click()
            time.sleep(3)
            page_text = self.driver.find_element(By.TAG_NAME,"body").text
            keywords = ["成功","签到","获得","恭喜","完成"]
            for kw in keywords:
                if kw in page_text: return page_text
            return "签到完成"
        except:
            return "签到失败或按钮不可点击"

    def run(self):
        try:
            self.login()
            result = self.checkin()
            balance = self.get_balance()
            logger.info(f"[{self.email}] 签到结果: {result}, 余额: {balance}")
            return True, result, balance
        except Exception as e:
            logger.error(f"[{self.email}] 错误: {e}")
            return False, str(e), "未知"
        finally:
            if self.driver: self.driver.quit()

class MultiAccountManager:
    def __init__(self):
        self.telegram_bot_token = os.getenv('TELEGRAM_BOT_TOKEN','')
        self.telegram_chat_id = os.getenv('TELEGRAM_CHAT_ID','')
        self.accounts = self.load_accounts()

    def load_accounts(self):
        accounts = []
        accts = os.getenv('LEAFLOW_ACCOUNTS','').strip()
        if accts:
            for pair in accts.split(','):
                if ':' in pair:
                    email,password = pair.split(':',1)
                    accounts.append({'email':email.strip(),'password':password.strip()})
        else:
            email = os.getenv('LEAFLOW_EMAIL','').strip()
            password = os.getenv('LEAFLOW_PASSWORD','').strip()
            if email and password: accounts.append({'email':email,'password':password})
        if not accounts: raise ValueError("未找到账号配置")
        return accounts

    def send_telegram(self, results):
        if not self.telegram_bot_token or not self.telegram_chat_id: return
        message = f"🎁 Leaflow签到通知\n📊 成功: {sum(1 for _,s,_,_ in results if s)}/{len(results)}\n📅 {datetime.now().strftime('%Y/%m/%d')}\n\n"
        for email,suc,res,balance in results:
            message += f"账号：{email}\n{'✅' if suc else '❌'} {res}\n💰余额：{balance}\n\n"
        try:
            requests.post(f"https://api.telegram.org/bot{self.telegram_bot_token}/sendMessage",
                          data={"chat_id":self.telegram_chat_id,"text":message,"parse_mode":"HTML"},timeout=10)
        except: pass

    def run_all(self):
        results=[]
        for acc in self.accounts:
            checker = LeaflowAutoCheckin(acc['email'],acc['password'])
            suc,res,balance = checker.run()
            results.append((acc['email'],suc,res,balance))
            time.sleep(3)
        self.send_telegram(results)
        return results

def main():
    try:
        MultiAccountManager().run_all()
    except Exception as e:
        logger.error(f"脚本错误: {e}")

if __name__=="__main__":
    main()
