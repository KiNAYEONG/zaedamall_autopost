# -*- coding: utf-8 -*-
"""
SmartEditor2 구조 진단 스크립트
"""

from dotenv import load_dotenv
import os
import time

from selenium.webdriver import Chrome, ChromeOptions
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

LOGIN_URL = "https://zae-da.com/bbs/login.php?url=%2F"
WRITE_URL = "https://zae-da.com/bbs/write.php?boardid=41"

def log(msg):
    print(msg, flush=True)

def wait_ready(drv, timeout=20):
    WebDriverWait(drv, timeout).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )

def accept_all_alerts(drv, limit=3):
    for _ in range(limit):
        try:
            a = drv.switch_to.alert
            txt = a.text
            log(f"⚠ 알럿: {txt}")
            a.accept()
            time.sleep(0.3)
        except Exception:
            break

def is_logged_in(drv):
    try:
        logout = drv.find_elements(By.XPATH, "//a[contains(.,'로그아웃') or contains(@href,'logout')]")
        return bool(logout)
    except Exception:
        return False

def try_auto_login(drv):
    uid = os.getenv("ZAEDA_ID", "").strip()
    pw = os.getenv("ZAEDA_PW", "").strip()
    if not uid or not pw:
        return False
    drv.get(LOGIN_URL)
    wait_ready(drv, 15)
    accept_all_alerts(drv)
    id_el = WebDriverWait(drv, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "#login_id")))
    pw_el = WebDriverWait(drv, 10).until(EC.presence_of_element_located((By.CSS_SELECTOR, "#login_pw")))
    id_el.clear()
    id_el.send_keys(uid)
    pw_el.clear()
    pw_el.send_keys(pw)
    pw_el.send_keys("\n")
    time.sleep(1.0)
    accept_all_alerts(drv)
    time.sleep(0.5)
    return is_logged_in(drv)

def diagnose_editor(drv):
    log("\n" + "="*60)
    log("SmartEditor2 구조 진단")
    log("="*60)
    
    # 1. oEditors 확인
    log("\n[1] window.oEditors 확인")
    js = """
    if (typeof window.oEditors === 'undefined') return 'UNDEFINED';
    if (!window.oEditors) return 'NULL';
    if (!window.oEditors.getById) return 'NO_GETBYID';
    const keys = Object.keys(window.oEditors.getById);
    return 'KEYS:' + keys.join(',');
    """
    result = drv.execute_script(js)
    log(f"   결과: {result}")
    
    # 2. iframe 확인
    log("\n[2] iframe 확인")
    iframes = drv.find_elements(By.TAG_NAME, "iframe")
    log(f"   총 {len(iframes)}개")
    for i, iframe in enumerate(iframes):
        log(f"   [{i}] id={iframe.get_attribute('id')}, name={iframe.get_attribute('name')}")
    
    # 3. se2_iframe 내부
    log("\n[3] se2_iframe 내부")
    try:
        drv.switch_to.frame("se2_iframe")
        body_els = drv.find_elements(By.TAG_NAME, "body")
        if body_els:
            body = body_els[0]
            log(f"   class={body.get_attribute('class')}")
            log(f"   contenteditable={body.get_attribute('contenteditable')}")
        drv.switch_to.default_content()
    except Exception as e:
        log(f"   실패: {e}")
        drv.switch_to.default_content()
    
    # 4. textarea
    log("\n[4] textarea 확인")
    textareas = drv.find_elements(By.TAG_NAME, "textarea")
    log(f"   총 {len(textareas)}개")
    for i, ta in enumerate(textareas):
        log(f"   [{i}] id={ta.get_attribute('id')}, name={ta.get_attribute('name')}")
    
    # 5. 전역 변수
    log("\n[5] SmartEditor 전역 변수")
    js = """
    const vars = [];
    if (typeof nhn !== 'undefined') vars.push('nhn');
    if (typeof jindo !== 'undefined') vars.push('jindo');
    if (typeof oEditors !== 'undefined') vars.push('oEditors');
    return vars.join(', ') || 'NONE';
    """
    log(f"   {drv.execute_script(js)}")
    
    log("\n" + "="*60 + "\n")

def main():
    load_dotenv()
    opts = ChromeOptions()
    opts.add_argument("--incognito")
    opts.add_argument("--start-maximized")
    opts.add_argument("--remote-allow-origins=*")
    drv = Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    
    try:
        if not is_logged_in(drv) and not try_auto_login(drv):
            drv.get(LOGIN_URL)
            input("로그인 후 엔터...")
        
        log(f"글쓰기 페이지: {WRITE_URL}")
        drv.get(WRITE_URL)
        wait_ready(drv, 15)
        time.sleep(3)
        
        diagnose_editor(drv)
        input("\n엔터를 누르면 종료...")
    finally:
        drv.quit()

if __name__ == "__main__":
    main()