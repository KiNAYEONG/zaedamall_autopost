# tools/mall_auto_write.py
# -*- coding: utf-8 -*-
r"""
재다몰 자동 업로드 (리스트→글쓰기 버튼 + 직행 URL 둘 다 지원)
- .env (루트)에 다음 값 권장:
    CHROME_USER_DATA_DIR=C:\Users\blueb\AppData\Local\Google\Chrome\User Data
    CHROME_PROFILE=Profile 18
    CHROME_FALLBACK_DIR=C:\ChromeProfiles\zaeda_selenium
- docs/data.xlsx에서 [제목(A), 본문(B)] 중 'DONE/Published/SKIP' 아닌 첫 행을 업로드
"""

import os
import time
import argparse
import datetime
from pathlib import Path

import openpyxl
from dotenv import load_dotenv

from selenium.webdriver import Chrome, ChromeOptions
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    WebDriverException,
    NoAlertPresentException,
    UnexpectedAlertPresentException,
    TimeoutException,
)
from webdriver_manager.chrome import ChromeDriverManager

# ──────────────────────────────
# 상수/경로
# ──────────────────────────────
load_dotenv()

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
XLSX = DOCS / "data.xlsx"

MAX_WAIT = 20
MALL_HOME = "https://zae-da.com/"
DEFAULT_LIST_URL  = "https://zae-da.com/bbs/list.php?boardid=41"
DEFAULT_WRITE_URL = "https://zae-da.com/bbs/board_write.php?boardid=41"

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
        title  = (ws[f"A{i}"].value or "").strip()
        body   = (ws[f"B{i}"].value or "").strip()
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
def make_options(user_data_dir: str | None, profile_dir: str | None):
    opts = ChromeOptions()
    if user_data_dir:
        opts.add_argument(f"--user-data-dir={user_data_dir}")
    if profile_dir:
        opts.add_argument(f"--profile-directory={profile_dir}")

    # 안정/호환 옵션
    opts.add_argument("--start-maximized")
    opts.add_argument("--no-first-run")
    opts.add_argument("--no-default-browser-check")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--disable-popup-blocking")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--remote-allow-origins=*")
    # opts.add_argument("--no-sandbox")  # 필요 시

    # 디버깅 편의
    opts.add_experimental_option("detach", True)
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    return opts

def setup_driver():
    """
    1) .env의 User Data + Profile로 시도
    2) 'already in use' 등 실패 시, CHROME_FALLBACK_DIR로 폴백
    """
    user_data_dir = os.path.expandvars(os.getenv(
        "CHROME_USER_DATA_DIR",
        r"C:\Users\%USERNAME%\AppData\Local\Google\Chrome\User Data"
    ))
    profile_dir = os.getenv("CHROME_PROFILE", "Default")

    try:
        opts = make_options(user_data_dir, profile_dir)
        drv = Chrome(service=Service(ChromeDriverManager().install()), options=opts)
        log(f"[chrome] using user-data-dir={user_data_dir}, profile={profile_dir}")
        return drv
    except WebDriverException as e:
        log(f"[chrome] primary profile failed → {e}")

        fallback_dir = os.path.expandvars(os.getenv("CHROME_FALLBACK_DIR", r"C:\ChromeProfiles\zaeda_selenium"))
        Path(fallback_dir).mkdir(parents=True, exist_ok=True)
        opts_fb = make_options(fallback_dir, None)
        drv = Chrome(service=Service(ChromeDriverManager().install()), options=opts_fb)
        log(f"[chrome] fallback profile launched: {fallback_dir}")
        try:
            drv.get(MALL_HOME)
        except Exception:
            pass
        log("  ↳ 폴백 창에서 재다몰에 1회 로그인해 두면 이후 자동 유지됩니다.")
        return drv

def accept_all_alerts(drv, max_times: int = 3):
    for _ in range(max_times):
        try:
            a = drv.switch_to.alert
            txt = a.text
            print(f"[alert] {txt}", flush=True)
            a.accept()
            time.sleep(0.2)
        except NoAlertPresentException:
            break

def wait_ready(drv):
    try:
        WebDriverWait(drv, MAX_WAIT).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )
    except UnexpectedAlertPresentException:
        accept_all_alerts(drv)
        WebDriverWait(drv, MAX_WAIT).until(
            lambda d: d.execute_script("return document.readyState") == "complete"
        )

def is_write_form_visible(drv) -> bool:
    try:
        WebDriverWait(drv, 5).until(
            EC.presence_of_element_located((
                By.CSS_SELECTOR,
                "input[name='wr_subject'], input[name='subject'], input[name='title']"
            ))
        )
        return True
    except TimeoutException:
        return False

def ensure_login_interactive(drv, target_url: str = MALL_HOME):
    """홈으로 보내 로그인 유도(콘솔 Enter 대기)."""
    drv.get(target_url)
    wait_ready(drv)
    print("\n────────────────────────────────────────")
    print(" 🔐 재다몰 창에서 로그인해 주세요.")
    print(" 로그인 완료 후 콘솔에서 Enter 키를 눌러 계속합니다.")
    print("────────────────────────────────────────\n")
    try:
        input()
    except EOFError:
        time.sleep(10)

# ───────────── 리스트 → 글쓰기 버튼 클릭 (스샷 기반 셀렉터 우선) ─────────────
def goto_write_from_list(drv, list_url: str) -> bool:
    """
    /bbs/list.php?boardid=41 페이지에서 '글쓰기' 버튼 클릭 → 에디터 진입
    """
    drv.get(list_url)
    wait_ready(drv)

    # 로그인 필요하면 유도
    if ("login" in drv.current_url.lower()) or ("로그인" in drv.page_source and "회원" in drv.page_source):
        log("⚠️ 로그인 필요 → 로그인 유도")
        ensure_login_interactive(drv, list_url)
        drv.get(list_url)
        wait_ready(drv)

    candidates = [
        # ✅ 스샷 기반 최우선 (div.rbt_box 내부 a.btn_lsmall[href*='write.php'])
        (By.CSS_SELECTOR, ".rbt_box a.btn_lsmall[href*='write.php']"),
        (By.CSS_SELECTOR, ".rbt_box a[href*='write.php']"),
        (By.XPATH, "//div[contains(@class,'rbt_box')]//a[contains(@href,'write.php')]"),

        # 🔁 백업
        (By.XPATH, "//a[contains(.,'글쓰기')]"),
        (By.XPATH, "//button[contains(.,'글쓰기')]"),
        (By.CSS_SELECTOR, "[title*='글쓰기']"),
        (By.CSS_SELECTOR, "[aria-label*='글쓰기']"),
        (By.XPATH, "//img[contains(@alt,'글쓰기')]/ancestor::a"),
    ]

    for by, sel in candidates:
        try:
            elem = WebDriverWait(drv, 6).until(EC.presence_of_element_located((by, sel)))
            drv.execute_script("arguments[0].scrollIntoView({block:'center'});", elem)
            try:
                drv.execute_script("arguments[0].click();", elem)     # 1차 JS 클릭
            except Exception:
                WebDriverWait(drv, 3).until(EC.element_to_be_clickable((by, sel))).click()  # 2차 일반 클릭
            wait_ready(drv)
            if is_write_form_visible(drv):
                log("✅ 글쓰기 페이지(리스트→버튼) 진입 성공")
                return True
        except Exception:
            accept_all_alerts(drv)
            continue

    return is_write_form_visible(drv)

def try_direct_write_url(drv, write_url: str) -> bool:
    """board_write.php 직행 시도."""
    drv.get(write_url)
    try:
        wait_ready(drv)
    except Exception:
        accept_all_alerts(drv)

    if is_write_form_visible(drv):
        log("✅ 글쓰기 페이지(직행) 진입 성공")
        return True

    accept_all_alerts(drv)
    time.sleep(0.2)
    if is_write_form_visible(drv):
        log("✅ 글쓰기 페이지(직행) 진입 성공")
        return True

    log("↪ 직행 진입 실패(로그인/권한/리다이렉트 필요 가능)")
    return False

def ensure_write_page(drv, list_url: str, write_url: str) -> None:
    """
    우선순위:
      ① 리스트 페이지 → '글쓰기' 버튼 클릭
      ② 실패 시 board_write.php 직행
    """
    # list.php → board_write.php 변환 (직행 재시도용)
    derived_write_url = write_url
    if "list.php" in list_url and "board_write.php" not in write_url:
        derived_write_url = list_url.replace("list.php", "board_write.php")

    # ① 리스트 경로
    if goto_write_from_list(drv, list_url):
        return

    log("↪ 리스트→버튼 경로 실패, 직행 URL로 재시도합니다…")
    # ② 직행 (우선 전달된 write_url, 없으면 유도된 주소)
    if try_direct_write_url(drv, write_url) or try_direct_write_url(drv, derived_write_url):
        return

    print("⚠️ 글쓰기 페이지에 진입하지 못했습니다.", flush=True)
    print("   - 로그인/권한/게시판 설정을 확인해 주세요.", flush=True)
    raise SystemExit(1)

# ──────────────────────────────
# Main
# ──────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list-url",  default=DEFAULT_LIST_URL,  help="게시판 목록 URL (list.php)")
    ap.add_argument("--url",       default=DEFAULT_WRITE_URL, help="글쓰기 URL (board_write.php)")
    args = ap.parse_args()

    wb, ws, row, title, body = load_next_row()
    if not row:
        log("대기 중인 업로드 건이 없습니다.")
        return

    drv = setup_driver()

    # 글쓰기 페이지 확보(리스트→버튼 우선, 실패 시 직행)
    ensure_write_page(drv, args.list_url, args.url)

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

    # 본문 입력: textarea → contenteditable 순
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
            drv.execute_script(
                "arguments[0].innerHTML = arguments[1];",
                ed,
                body.replace("\n", "<br>")
            )
            log("본문 입력 완료 ✓ (contenteditable)")
        except Exception as e:
            log(f"❌ 본문 입력 실패: {e}")
            return

    # 등록/작성/저장 버튼 클릭
    try:
        submit_btn = drv.find_element(
            By.XPATH,
            "//button[contains(.,'등록') or contains(.,'작성') or contains(.,'저장')] | //input[@type='submit']"
        )
        drv.execute_script("arguments[0].scrollIntoView({block:'center'});", submit_btn)
        try:
            drv.execute_script("arguments[0].click();", submit_btn)
        except Exception:
            submit_btn.click()
        log("등록 버튼 클릭 ✓")
    except Exception as e:
        log(f"❌ 등록 버튼 클릭 실패: {e}")
        return

    # 완료 처리
    mark_done(wb, ws, row)
    log("✅ 업로드 완료 → DONE 처리")

if __name__ == "__main__":
    main()
