# -*- coding: utf-8 -*-
"""
재다몰 자동 글쓰기 도구 - 수정 버전
- Chrome 호환성 강화
- 스마트에디터 입력 지원
- 제목 입력 selector 수정 (#fboardform 경로)
- 제출 버튼 스마트 탐지 + 수동 대기
- Excel 상태값 업데이트
"""

import os
import sys
import time
import argparse
import traceback
from pathlib import Path
from dotenv import load_dotenv
import pandas as pd

# Selenium
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException

# ── 설정 ─────────────────────────────
load_dotenv()
ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
XLSX = DOCS / "data.xlsx"


def setup_driver(headless=False):
    opts = Options()
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--window-size=1920,1080")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-logging", "enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    if headless:
        opts.add_argument("--headless")

    driver = webdriver.Chrome(options=opts)
    driver.set_page_load_timeout(60)
    driver.implicitly_wait(10)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    print("✅ Chrome 드라이버 준비 완료")
    return driver


def enhanced_login(driver, username, password):
    try:
        driver.get("https://zae-da.com/bbs/login.php")
        WebDriverWait(driver, 10).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )

        user_field = driver.find_element(By.CSS_SELECTOR, "#login_id")
        pass_field = driver.find_element(By.CSS_SELECTOR, "#login_pw")
        user_field.clear()
        pass_field.clear()
        user_field.send_keys(username)
        pass_field.send_keys(password)

        driver.find_element(By.CSS_SELECTOR, "#login_fld button").click()
        time.sleep(3)

        if "login" not in driver.current_url.lower():
            print("✅ 로그인 성공")
            return True
        return False
    except Exception as e:
        print(f"❌ 로그인 실패: {e}")
        return False


def smart_editor_input(driver, content):
    try:
        iframe = driver.find_element(By.CSS_SELECTOR, "iframe[src*='editor']")
        driver.switch_to.frame(iframe)
        body = driver.find_element(By.TAG_NAME, "body")
        driver.execute_script("arguments[0].innerHTML = arguments[1]", body, content)
        driver.switch_to.default_content()
        print("✅ 본문 입력 완료")
        return True
    except Exception as e:
        print(f"❌ 본문 입력 실패: {e}")
        driver.switch_to.default_content()
        return False


def load_post_data():
    if not XLSX.exists():
        print("❌ data.xlsx 없음")
        return None, None, None

    df = pd.read_excel(XLSX)
    row = df[df["상태"].isna() | (df["상태"] != "발행")].head(1)

    if row.empty:
        print("❌ 발행할 데이터 없음")
        return None, None, None

    idx = row.index[0]
    title = str(row.at[idx, "제목"])
    content = str(row.at[idx, "본문"])
    return idx, title, content


def mark_as_published(idx):
    df = pd.read_excel(XLSX)
    df.at[idx, "상태"] = "발행"
    df.at[idx, "업데이트시각"] = time.strftime("%Y-%m-%d %H:%M")
    df.to_excel(XLSX, index=False)
    print(f"💾 Excel 업데이트 완료 → 행 {idx} 발행 처리")


def main_posting(driver, url, idx, title, body):
    try:
        driver.get(url)
        time.sleep(2)

        # 제목 입력 (새 selector + fallback)
        try:
            title_field = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((
                    By.CSS_SELECTOR,
                    "#fboardform > div.tbl_frm01.tbl_wrap > table > tbody > tr:nth-child(3) > td > input"
                ))
            )
        except:
            title_field = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "input[type='text']"))
            )

        title_field.clear()
        title_field.send_keys(title)
        print("✅ 제목 입력 성공")

        # 본문 입력
        if not smart_editor_input(driver, body):
            return False

        # 제출 버튼 클릭
        submit_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button[type='submit']"))
        )
        submit_btn.click()
        time.sleep(3)

        if "read.php" in driver.current_url:
            print(f"🎉 포스팅 성공 → {driver.current_url}")
            mark_as_published(idx)
            return True
        return False

    except Exception as e:
        print(f"❌ 글쓰기 실패: {e}")
        return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True, help="글쓰기 URL")
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()

    if not os.getenv("ZAEDA_ID") or not os.getenv("ZAEDA_PW"):
        print("❌ ZAEDA_ID / ZAEDA_PW 환경변수 필요")
        sys.exit(1)

    driver = setup_driver(headless=args.headless)
    try:
        if not enhanced_login(driver, os.getenv("ZAEDA_ID"), os.getenv("ZAEDA_PW")):
            sys.exit(1)

        idx, title, body = load_post_data()
        if title is None:
            sys.exit(0)

        if not main_posting(driver, args.url, idx, title, body):
            sys.exit(1)
    finally:
        driver.quit()
        print("✅ 브라우저 종료")


if __name__ == "__main__":
    main()
