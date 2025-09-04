# tools/auto_write.py
# -*- coding: utf-8 -*-
"""
재다몰 자동 글쓰기 (Excel → 웹)
- Excel 첫 번째 '미발행' 행 선택
- 제목, 본문, 이미지 업로드
- 발행 버튼 자동 클릭
"""

import os, time
import pandas as pd
from pathlib import Path
from dotenv import load_dotenv

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

# .env 불러오기
load_dotenv()

ROOT  = Path(__file__).resolve().parent.parent
DOCS  = ROOT / "docs"
XLSX  = DOCS / "data.xlsx"

ZAEDA_ID = os.getenv("ZAEDA_ID")
ZAEDA_PW = os.getenv("ZAEDA_PW")

if not ZAEDA_ID or not ZAEDA_PW:
    raise RuntimeError("환경변수 ZAEDA_ID / ZAEDA_PW 필요")

def get_next_post():
    """Excel에서 미발행 데이터 1건 가져오기"""
    df = pd.read_excel(XLSX)
    if "상태" not in df.columns:
        df["상태"] = ""
    row = df[df["상태"] != "발행"].head(1)
    if row.empty:
        print("📭 발행할 글 없음")
        return None, None, None, df
    idx = row.index[0]
    title = str(row.at[idx, "제목"]).strip()
    body = str(row.at[idx, "본문"]).strip()
    return idx, title, body, df

def save_posted(df, idx):
    """발행 상태 저장"""
    df.at[idx, "상태"] = "발행"
    df.to_excel(XLSX, index=False)
    print(f"💾 발행 완료 기록 저장 ({XLSX})")

def start_chrome():
    """Chrome 실행"""
    opts = Options()
    opts.add_argument("--start-maximized")
    drv = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    return drv

def login(drv):
    """재다몰 로그인"""
    drv.get("https://zae-da.com/bbs/login.php?url=%2F")
    print("🔍 로그인 페이지 진입...")

    # 아이디/비밀번호 입력
    WebDriverWait(drv, 10).until(EC.presence_of_element_located((By.ID, "login_id"))).send_keys(ZAEDA_ID)
    drv.find_element(By.ID, "login_pw").send_keys(ZAEDA_PW)

    # 로그인 버튼 클릭 (수정된 selector)
    drv.find_element(By.CSS_SELECTOR, "#login_fld > dl > dd:nth-child(5) > button").click()
    print("✅ 로그인 버튼 클릭")

def write_post(drv, url, title, body):
    """글 작성"""
    drv.get(url)
    print(f"📍 글쓰기 페이지 이동: {url}")

    # 제목 입력 (iframe 아님)
    # 제목 입력
    try:
        title_box = WebDriverWait(drv, 10).until(
            EC.presence_of_element_located((
                By.CSS_SELECTOR,
                "#fboardform > div.tbl_frm01.tbl_wrap > table > tbody > tr:nth-child(3) > td > input"
            ))
        )
        title_box.clear()
        title_box.send_keys(title)
        print("📝 제목 입력 완료")
    except Exception as e:
        print("❌ 제목 입력 실패:", e)
        raise

    # 본문 입력 (iframe 안에 있음)
    drv.switch_to.frame("se2_iframe")
    body_area = WebDriverWait(drv, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "body"))
    )
    body_area.clear()
    body_area.send_keys(body)
    drv.switch_to.default_content()
    print("📝 제목/본문 입력 완료")

    # 발행 버튼 클릭
    WebDriverWait(drv, 10).until(
        EC.element_to_be_clickable((By.CSS_SELECTOR, "button.btn_submit"))
    ).click()
    print("🚀 발행 버튼 클릭")


def main():
    idx, title, body, df = get_next_post()
    if not title:
        return

    drv = start_chrome()
    try:
        login(drv)
        time.sleep(2)  # 로그인 처리 대기
        write_post(drv, "https://zae-da.com/bbs/write.php?boardid=41", title, body)
        save_posted(df, idx)
    finally:
        print("✅ 종료(브라우저는 수동 닫기)")

if __name__ == "__main__":
    main()
