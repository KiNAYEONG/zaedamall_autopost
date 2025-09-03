# tools/auto_write.py
# -*- coding: utf-8 -*-
"""
재다몰 자동 업로드 (로그인 보장형 단일 스크립트)

기능 요약
- .env의 프로필로 크롬 실행, 충돌/크래시 시 폴백 프로필로 재시도
- 로그인 상태 점검 → 미로그인 시:
    * ZAEDA_ID/ZAEDA_PW 있으면 자동 로그인
    * 없거나 실패하면 수동 로그인 대기(엔터로 계속)
- 글쓰기 페이지 진입:
    * 직접 write URL 접근 시도
    * 실패하면 목록(list) 페이지에서 '글쓰기' 버튼 클릭
- 제목/본문 입력 후 제출
- 기본적으로 브라우저를 닫지 않음(--keep-open)

필요 .env 키
CHROME_USER_DATA_DIR=C:\Users\...\Google\Chrome\User Data
CHROME_PROFILE=Profile 18
CHROME_FALLBACK_DIR=C:\ChromeProfiles\zaeda_selenium
ZAEDA_ID=your_id
ZAEDA_PW=your_password
"""

from dotenv import load_dotenv
import os
import argparse
import datetime
import time
from pathlib import Path
import openpyxl

from selenium.webdriver import Chrome, ChromeOptions
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.alert import Alert
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    UnexpectedAlertPresentException,
    WebDriverException,
)

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
XLSX = DOCS / "data.xlsx"

MAX_WAIT = 20

def log(msg: str):
    print(msg, flush=True)

def wait_ready(drv, timeout=MAX_WAIT):
    WebDriverWait(drv, timeout).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )

def accept_all_alerts(drv, limit=3):
    for _ in range(limit):
        try:
            a = drv.switch_to.alert
            txt = a.text
            log(f"⚠ 알럿 감지: {txt}")
            a.accept()
            time.sleep(0.4)
        except Exception:
            break

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
        body = (ws[f"B{i}"].value or "").strip()
        status = (ws[f"C{i}"].value or "").strip().upper()
        if title and body and status not in ("DONE", "PUBLISHED", "SKIP"):
            return wb, ws, i, title, body
    return wb, ws, None, None, None

def mark_done(wb, ws, row: int):
    ws[f"C{row}"] = "DONE"
    ws[f"D{row}"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    wb.save(XLSX)

# ──────────────────────────────
# Driver bootstrap
# ──────────────────────────────
def build_options(user_dir: str, profile_dirname: str = None):
    opts = ChromeOptions()
    if profile_dirname:
        # "User Data" + "Profile 18" 형태
        opts.add_argument(f'--user-data-dir={user_dir}')
        opts.add_argument(f'--profile-directory={profile_dirname}')
    else:
        # 그냥 하나의 전용 폴더(C:\ChromeProfiles\xxx)를 user-data-dir로 사용하는 경우
        opts.add_argument(f'--user-data-dir={user_dir}')
    opts.add_argument('--start-maximized')
    opts.add_argument('--no-first-run')
    opts.add_argument('--no-default-browser-check')
    opts.add_argument('--disable-extensions')
    opts.add_argument('--disable-popup-blocking')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--remote-allow-origins=*')
    # Windows 환경에서 간헐적 크래시 회피
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option('useAutomationExtension', False)
    return opts

def setup_driver():
    load_dotenv()

    primary_user_dir = os.getenv("CHROME_USER_DATA_DIR", "").strip()
    profile_name = os.getenv("CHROME_PROFILE", "").strip()  # 예: "Profile 18"
    fallback_dir = os.getenv("CHROME_FALLBACK_DIR", r"C:\ChromeProfiles\zaeda_selenium").strip()

    # 1) 우선: User Data + Profile N 조합 시도
    try:
        if primary_user_dir and profile_name:
            log("기존 브라우저 세션(프로필 지정)에서 여는 중입니다.")
            opts = build_options(primary_user_dir, profile_name)
        elif primary_user_dir:
            log("기존 브라우저 세션(폴더 지정)에서 여는 중입니다.")
            opts = build_options(primary_user_dir, None)
        else:
            raise RuntimeError("CHROME_USER_DATA_DIR 미지정")

        drv = Chrome(service=Service(ChromeDriverManager().install()), options=opts)
        return drv, f"{primary_user_dir} | {profile_name or ''}".strip()
    except Exception as e:
        log(f"[chrome] primary profile failed → {e}")

    # 2) 폴백 프로필 폴더 보장
    try:
        Path(fallback_dir).mkdir(parents=True, exist_ok=True)
        opts = build_options(fallback_dir, None)
        drv = Chrome(service=Service(ChromeDriverManager().install()), options=opts)
        log(f"[chrome] fallback profile launched: {fallback_dir}")
        log("  ↳ 폴백 창에서 재다몰에 1회 로그인해 두면 이후 자동 유지됩니다.")
        return drv, fallback_dir
    except Exception as e:
        raise RuntimeError(f"크롬 실행 실패: {e}")

# ──────────────────────────────
# Login helpers
# ──────────────────────────────
def is_logged_in(drv) -> bool:
    """
    재다몰 공통: 로그인 상태면 보통 상단/하단에 '로그아웃' 링크가 있고,
    글쓰기 버튼이 활성화된다. 쉬운 휴리스틱 2가지를 모두 봅니다.
    """
    try:
        # 1) 로그아웃 링크 존재?
        logout = drv.find_elements(By.XPATH, "//a[contains(.,'로그아웃') or contains(.,'Logout')]")
        if logout:
            return True
        # 2) 글쓰기 버튼 활성화?
        write_btns = drv.find_elements(By.XPATH, "//a[contains(.,'글쓰기') or contains(.,'Write')] | //button[contains(.,'글쓰기')]")
        if write_btns:
            # disabled 속성이 없거나 클릭 가능하면 로그인된 경우가 많음
            try:
                if write_btns[0].is_enabled():
                    return True
            except Exception:
                pass
        return False
    except Exception:
        return False

def try_auto_login(drv, login_url_candidates):
    uid = os.getenv("ZAEDA_ID", "").strip()
    pw = os.getenv("ZAEDA_PW", "").strip()
    if not uid or not pw:
        return False

    for url in login_url_candidates:
        try:
            drv.get(url)
            wait_ready(drv, 15)
        except Exception:
            continue

        # id / password 필드 후보
        input_selectors = [
            "input[name='mb_id']", "input[name='id']", "input#mb_id", "input#login_id",
            "input[name='mb_password']", "input[name='password']", "input#mb_password", "input#login_pw",
        ]

        try:
            # 아이디
            id_candidates = drv.find_elements(By.CSS_SELECTOR, "input[name='mb_id'], input[name='id'], input#mb_id, input#login_id")
            pw_candidates = drv.find_elements(By.CSS_SELECTOR, "input[name='mb_password'], input[name='password'], input#mb_password, input#login_pw")
            if not id_candidates or not pw_candidates:
                continue

            id_el = id_candidates[0]
            pw_el = pw_candidates[0]
            id_el.clear(); id_el.send_keys(uid)
            pw_el.clear(); pw_el.send_keys(pw)

            # 로그인 버튼 후보
            login_btn = None
            for sel in [
                "button[type='submit']", "input[type='submit']",
                "a.btn_login", "button.login", "button#login", "input#login"
            ]:
                btns = drv.find_elements(By.CSS_SELECTOR, sel)
                if btns:
                    login_btn = btns[0]
                    break
            if login_btn is None:
                # 텍스트로 찾기
                btns = drv.find_elements(By.XPATH, "//button[contains(.,'로그인')] | //a[contains(.,'로그인')] | //input[@type='submit']")
                if btns:
                    login_btn = btns[0]

            if login_btn is None:
                continue

            login_btn.click()
            time.sleep(1.0)
            accept_all_alerts(drv)
            time.sleep(0.5)
            # 로그인 성공 판정
            if is_logged_in(drv):
                log("🔐 자동 로그인 성공")
                return True
        except UnexpectedAlertPresentException:
            accept_all_alerts(drv)
        except Exception:
            continue
    return False

def ensure_login(drv, list_url_for_check: str):
    """
    로그인 상태 보장:
    - 현재 페이지에서 로그인 여부 체크
    - 미로그인 → 자동 로그인 시도 → 실패시 수동 로그인 안내
    """
    try:
        drv.get(list_url_for_check)
        wait_ready(drv)
    except Exception:
        pass

    if is_logged_in(drv):
        log("🔓 이미 로그인 상태입니다.")
        return

    # 자동 로그인 시도
    login_urls = [
        "https://zae-da.com/m/bbs/login.php",
        "https://zae-da.com/m/member/login.php",
        "https://zae-da.com/bbs/login.php",
        "https://zae-da.com/member/login.php",
        "https://zae-da.com/m/",
        "https://zae-da.com/",
    ]
    if try_auto_login(drv, login_urls):
        return

    # 수동 로그인 유도
    log("👤 자동 로그인 실패 → 수동 로그인 안내")
    # 가장 일반적인 로그인 화면으로 이동
    try:
        drv.get("https://zae-da.com/m/member/login.php")
        wait_ready(drv, 15)
    except Exception:
        try:
            drv.get("https://zae-da.com/m/bbs/login.php")
            wait_ready(drv, 15)
        except Exception:
            pass

    input("재다몰에 수동 로그인 후 엔터를 눌러 계속하세요... ")
    # 로그인 여부 재확인
    drv.get(list_url_for_check)
    wait_ready(drv)
    if not is_logged_in(drv):
        raise RuntimeError("로그인이 확인되지 않았습니다. 수동 로그인 후 다시 시도해주세요.")

# ──────────────────────────────
# Navigation to write page
# ──────────────────────────────
def goto_write_from_list(drv, list_url: str) -> bool:
    try:
        drv.get(list_url)
        wait_ready(drv)
        accept_all_alerts(drv)

        # 글쓰기 버튼 후보들
        candidates = [
            (By.CSS_SELECTOR, "a.btn_write"),
            (By.XPATH, "//a[contains(.,'글쓰기')]"),
            (By.XPATH, "//button[contains(.,'글쓰기')]"),
            (By.CSS_SELECTOR, "a[class*='write']"),
        ]
        for by, sel in candidates:
            btns = drv.find_elements(by, sel)
            if not btns:
                continue
            for b in btns:
                try:
                    if b.is_enabled():
                        b.click()
                        time.sleep(0.4)
                        accept_all_alerts(drv)
                        wait_ready(drv)
                        # 도착 확인: 보통 subject 필드가 존재
                        if find_subject(drv) is not None:
                            log("✅ 글쓰기 페이지(리스트→버튼) 진입 성공")
                            return True
                except Exception:
                    accept_all_alerts(drv)
                    continue
        return False
    except Exception:
        return False

def find_subject(drv):
    sels = [
        "input[name='wr_subject']",
        "input[name='subject']",
        "input[name='title']",
        "input#wr_subject",
        "input#subject",
        "input#title",
    ]
    for sel in sels:
        els = drv.find_elements(By.CSS_SELECTOR, sel)
        if els:
            return els[0]
    return None

def find_body_targets(drv):
    # textarea 우선, 없으면 contenteditable
    ta = drv.find_elements(By.CSS_SELECTOR, "textarea[name='wr_content'], textarea[name='content'], textarea#wr_content, textarea#content, textarea")
    if ta:
        return ("textarea", ta[0])

    ed = None
    # 대표적인 에디터 컨테이너
    for sel in [
        "div[contenteditable='true']",
        "div.se2_inputarea",         # SmartEditor
        "iframe",                    # iframe 기반 에디터
    ]:
        els = drv.find_elements(By.CSS_SELECTOR, sel)
        if els:
            ed = els[0]
            break
    if ed is not None:
        return ("editor", ed)
    return (None, None)

def ensure_write_page(drv, list_url: str, write_url: str) -> None:
    """
    1) write_url 직접 접근 시도 → 제목 필드 보이면 OK
    2) 안되면 list_url에서 글쓰기 버튼 클릭
    """
    try:
        drv.get(write_url)
        wait_ready(drv)
        accept_all_alerts(drv)
        if find_subject(drv) is not None:
            log("✅ 글쓰기 페이지(직접 URL) 진입 성공")
            return
    except Exception:
        accept_all_alerts(drv)

    # 목록에서 글쓰기 버튼
    if goto_write_from_list(drv, list_url):
        return

    raise RuntimeError("글쓰기 페이지로 진입하지 못했습니다.")

# ──────────────────────────────
# Main
# ──────────────────────────────
def main():
    load_dotenv()

    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True, help="글쓰기 URL (예: https://zae-da.com/m/bbs/board_write.php?boardid=41)")
    ap.add_argument("--list-url", default="https://zae-da.com/bbs/list.php?boardid=41", help="글 목록 URL(글쓰기 버튼 누르기용)")
    ap.add_argument("--keep-open", action="store_true", default=True, help="종료 후 브라우저 유지")
    ap.add_argument("--no-excel", action="store_true", help="엑셀 대신 테스트 텍스트 사용")
    args = ap.parse_args()

    drv, profile_info = setup_driver()
    log(f"프로필 정보: {profile_info}")

    try:
        # 로그인 보장
        ensure_login(drv, args.list_url)

        # 글쓰기 페이지 진입
        ensure_write_page(drv, args.list_url, args.url)

        # 콘텐츠 준비
        if args.no_excel:
            title = "테스트 제목입니다 (자동화)"
            body = "테스트 본문 입니다.\n자동화 확인용."
            wb = ws = row = None
        else:
            wb, ws, row, title, body = load_next_row()
            if not row:
                log("대기 중인 업로드 건이 없습니다.")
                return

        # 제목 입력
        ti = find_subject(drv)
        if not ti:
            raise RuntimeError("제목 입력 필드를 찾을 수 없습니다.")
        ti.clear()
        ti.send_keys(title)
        log("제목 입력 완료 ✓")

        # 본문 입력
        kind, target = find_body_targets(drv)
        if kind == "textarea":
            target.clear()
            target.send_keys(body)
            log("본문 입력 완료 ✓ (textarea)")
        elif kind == "editor":
            tag_name = target.tag_name.lower()
            if tag_name == "iframe":
                # iframe 에디터인 경우
                drv.switch_to.frame(target)
                try:
                    ed = drv.find_element(By.CSS_SELECTOR, "body[contenteditable='true'], body")
                    drv.execute_script("arguments[0].innerHTML = arguments[1];", ed, body.replace("\n","<br>"))
                    log("본문 입력 완료 ✓ (iframe editor)")
                finally:
                    drv.switch_to.default_content()
            else:
                drv.execute_script("arguments[0].innerHTML = arguments[1];", target, body.replace("\n","<br>"))
                log("본문 입력 완료 ✓ (contenteditable/editor)")
        else:
            raise RuntimeError("본문 입력 필드를 찾을 수 없습니다.")

        # 제출 버튼
        submit_btn = None
        for sel in [
            "//button[contains(.,'등록') or contains(.,'작성') or contains(.,'저장')]",
            "//input[@type='submit']",
        ]:
            btns = drv.find_elements(By.XPATH, sel)
            if btns:
                submit_btn = btns[0]
                break

        if submit_btn is None:
            raise RuntimeError("제출 버튼을 찾을 수 없습니다.")

        submit_btn.click()
        time.sleep(0.5)
        accept_all_alerts(drv)
        wait_ready(drv)

        log("등록 버튼 클릭 ✓")

        # 엑셀 DONE 표시
        if 'wb' in locals() and wb and ws and row:
            mark_done(wb, ws, row)
            log("✅ 업로드 완료 → DONE 처리")

    except UnexpectedAlertPresentException:
        try:
            a = drv.switch_to.alert
            log(f"❌ 알럿으로 인해 제출이 중단되었습니다. 메시지: {a.text}")
            a.accept()
        except Exception:
            pass
    except Exception as e:
        log(f"❌ 오류: {e}")
    finally:
        if args.keep_open:
            log("브라우저는 열어둡니다. 작업 내용을 확인하세요.")
        else:
            try:
                drv.quit()
            except Exception:
                pass

if __name__ == "__main__":
    main()
