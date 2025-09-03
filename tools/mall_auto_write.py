# tools/mall_auto_write.py
# -*- coding: utf-8 -*-
r"""
재다몰 자동 업로드 (크롬 독립 세션 버전)
- 기존 크롬이 켜져 있어도 상관없음
- .env의 CHROME_USER_DATA_DIR (예: ...\Chrome\User Data) + CHROME_PROFILE (예: Profile 18) 사용
- docs/data.xlsx에서 첫 번째 대기 건을 읽어 글쓰기 페이지에 업로드
"""

import os
import argparse, datetime
from pathlib import Path

import openpyxl
from dotenv import load_dotenv

from selenium.webdriver import Chrome, ChromeOptions
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

# ──────────────────────────────
# 설정
# ──────────────────────────────
load_dotenv()  # .env 로드

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
XLSX = DOCS / "data.xlsx"
MAX_WAIT = 20

def log(msg: str) -> None:
    print(msg, flush=True)

# ──────────────────────────────
# Excel helpers
# ──────────────────────────────
def load_next_row():
    if not XLSX.exists():
        raise FileNotFoundError(f"엑셀 파일이 없습니다: {XLSX}")
    wb = openpyxl.load_workbook(XLSX)
    ws = wb.active
    for i in range(2, ws.max_row + 1):
        title = (ws[f"A{i}"].value or "").strip()
        body  = (ws[f"B{i}"].value or "").strip()
        status = (ws[f"C{i}"].value or "").strip().upper()
        if title and body and status not in ("DONE", "PUBLISHED", "SKIP"):
            return wb, ws, i, title, body
    return wb, ws, None, None, None

def mark_done(wb, ws, row: int):
    ws[f"C{row}"] = "DONE"
    ws[f"D{row}"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    wb.save(XLSX)

# ──────────────────────────────
# Selenium helpers
# ──────────────────────────────
def setup_driver():
    """
    user-data-dir 은 반드시 '...\\Chrome\\User Data' 상위 경로여야 하며,
    실제 사용할 프로필은 --profile-directory 로 지정합니다.
    """
    opts = ChromeOptions()

    # .env에서 읽기
    user_data_dir = os.getenv(
        "CHROME_USER_DATA_DIR",
        r"C:\Users\%USERNAME%\AppData\Local\Google\Chrome\User Data"
    )
    profile_dir = os.getenv("CHROME_PROFILE", "Default")

    # 환경변수 내 %USERNAME% 치환
    user_data_dir = os.path.expandvars(user_data_dir)

    opts.add_argument(f'--user-data-dir={user_data_dir}')
    opts.add_argument(f'--profile-directory={profile_dir}')
    opts.add_argument('--start-maximized')

    # 충돌 완화 옵션
    opts.add_argument('--no-first-run')
    opts.add_argument('--no-default-browser-check')
    opts.add_argument('--disable-extensions')
    opts.add_argument('--disable-popup-blocking')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--remote-allow-origins=*')
    # 기업 보안 정책에 따라 필요할 때만 임시 사용
    # opts.add_argument('--no-sandbox')

    # 디버깅 편의: 자동 종료 방지
    opts.add_experimental_option("detach", True)
    # 자동화 표시 최소화(일부 보안툴 충돌 회피)
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)

    drv = Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    return drv

def wait_ready(drv):
    WebDriverWait(drv, MAX_WAIT).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )

# ──────────────────────────────
# Main
# ──────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True, help="재다몰 글쓰기 URL (board_write.php)")
    args = ap.parse_args()

    wb, ws, row, title, body = load_next_row()
    if not row:
        log("대기 중인 업로드 건이 없습니다.")
        return

    drv = setup_driver()
    drv.get(args.url)
    wait_ready(drv)

    # 제목 입력
    try:
        title_input = WebDriverWait(drv, MAX_WAIT).until(
            EC.presence_of_element_located((
                By.CSS_SELECTOR,
                "input[name='wr_subject'], input[name='subject'], input[name='title']"
            ))
        )
        title_input.clear()
        title_input.send_keys(title)
        log("제목 입력 완료 ✓")
    except Exception as e:
        log(f"❌ 제목 입력 실패: {e}")
        return

    # 본문 입력 (textarea → contenteditable 순)
    try:
        ta = drv.find_element(By.CSS_SELECTOR,
            "textarea[name='wr_content'], textarea[name='content'], textarea"
        )
        ta.clear()
        ta.send_keys(body)
        log("본문 입력 완료 ✓ (textarea)")
    except Exception:
        try:
            ed = drv.find_element(By.CSS_SELECTOR, "div[contenteditable='true']")
            drv.execute_script("arguments[0].innerHTML = arguments[1];", ed, body.replace("\n", "<br>"))
            log("본문 입력 완료 ✓ (contenteditable)")
        except Exception as e:
            log(f"❌ 본문 입력 실패: {e}")
            return

    # 등록 버튼 클릭
    try:
        btn = drv.find_element(
            By.XPATH,
            "//button[contains(.,'등록') or contains(.,'작성') or contains(.,'저장')] | //input[@type='submit']"
        )
        btn.click()
        log("등록 버튼 클릭 ✓")
    except Exception as e:
        log(f"❌ 등록 버튼 클릭 실패: {e}")
        return

    # 완료 처리
    mark_done(wb, ws, row)
    log("✅ 업로드 완료 → DONE 처리")

if __name__ == "__main__":
    main()
