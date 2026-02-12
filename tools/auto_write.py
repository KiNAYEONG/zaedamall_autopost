# tools/auto_write.py
# -*- coding: utf-8 -*-
r"""
재다몰 자동 업로드 (로그인 보장형 단일 스크립트) - SmartEditor2(memo) 대응

✅ 현재 게시판(boardid=41) 기준 확인된 구조
- oEditors.getById['memo'] 존재
- textarea id/name = memo
- se2_iframe 이라는 id의 iframe은 없음(iframe id/name 비어있을 수 있음)

동작 요약
1) 시크릿 크롬 실행
2) 로그인 페이지로 이동 → #login_id/#login_pw 자동 입력 → 엔터 submit
3) 글쓰기 페이지 진입 (write.php?boardid=41)
4) 제목 입력
5) 본문 입력
   - 1순위: textarea#memo value 세팅(가장 튼튼)
   - 2순위: oEditors.getById['memo'] 있으면 SET_CONTENTS + UPDATE_CONTENTS_FIELD
6) 등록 버튼 클릭(JS click)
7) 브라우저는 기본적으로 열어둠(옵션 --close로 닫기)

.env (프로젝트 루트에 위치)
ZAEDA_ID=...
ZAEDA_PW=...

실행 예시
- 테스트(엑셀 없이):
  python tools/auto_write.py --no-excel

- 엑셀 있으면(없으면 자동으로 no-excel처럼 동작):
  python tools/auto_write.py
"""

from dotenv import load_dotenv
import os
import argparse
import datetime
import time
import traceback
from pathlib import Path

import openpyxl
from selenium.webdriver import Chrome, ChromeOptions
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
from selenium.common.exceptions import TimeoutException, UnexpectedAlertPresentException


# ──────────────────────────────
# Constants / Paths
# ──────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
XLSX = DOCS / "data.xlsx"

MAX_WAIT = 20

LOGIN_URL = "https://zae-da.com/bbs/login.php?url=%2F"
DEFAULT_LIST_URL = "https://zae-da.com/bbs/list.php?boardid=41"
DEFAULT_WRITE_URL = "https://zae-da.com/bbs/write.php?boardid=41"


# ──────────────────────────────
# Utils
# ──────────────────────────────
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
            time.sleep(0.3)
        except Exception:
            break


# ──────────────────────────────
# Excel (optional)
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
# Driver
# ──────────────────────────────
def build_options():
    opts = ChromeOptions()
    opts.add_argument("--incognito")
    opts.add_argument("--start-maximized")
    opts.add_argument("--no-first-run")
    opts.add_argument("--no-default-browser-check")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--disable-popup-blocking")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--remote-allow-origins=*")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    return opts


def setup_driver():
    opts = build_options()
    drv = Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    return drv, "incognito"


# ──────────────────────────────
# Login
# ──────────────────────────────
def is_logged_in(drv) -> bool:
    try:
        logout = drv.find_elements(
            By.XPATH,
            "//a[contains(.,'로그아웃') or contains(.,'Logout') or contains(@href,'logout')]",
        )
        return bool(logout)
    except Exception:
        return False


def try_auto_login(drv) -> bool:
    uid = os.getenv("ZAEDA_ID", "").strip()
    pw = os.getenv("ZAEDA_PW", "").strip()

    if not uid or not pw:
        log("[login] ZAEDA_ID/ZAEDA_PW 미설정 → 자동 로그인 스킵")
        return False

    drv.get(LOGIN_URL)
    wait_ready(drv, 15)
    accept_all_alerts(drv)

    id_el = WebDriverWait(drv, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "#login_id"))
    )
    pw_el = WebDriverWait(drv, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "#login_pw"))
    )

    id_el.clear()
    id_el.send_keys(uid)
    pw_el.clear()
    pw_el.send_keys(pw)
    pw_el.send_keys("\n")

    time.sleep(1.0)
    accept_all_alerts(drv)
    time.sleep(0.5)

    if is_logged_in(drv):
        log("🔐 자동 로그인 성공")
        return True

    return False


def ensure_login(drv, list_url_for_check: str):
    try:
        drv.get(list_url_for_check)
        wait_ready(drv, 15)
        accept_all_alerts(drv)
    except Exception:
        pass

    if is_logged_in(drv):
        log("🔓 이미 로그인 상태입니다.")
        return

    if try_auto_login(drv):
        return

    log("👤 자동 로그인 실패 → 수동 로그인 안내")
    drv.get(LOGIN_URL)
    wait_ready(drv, 15)
    accept_all_alerts(drv)

    input("재다몰에 수동 로그인 후 엔터를 눌러 계속하세요... ")

    drv.get(list_url_for_check)
    wait_ready(drv, 15)
    accept_all_alerts(drv)

    if not is_logged_in(drv):
        raise RuntimeError("로그인이 확인되지 않았습니다.")


# ──────────────────────────────
# Navigation (write page)
# ──────────────────────────────
def find_subject(drv):
    for sel in [
        "input[name='wr_subject']",
        "input#wr_subject",
        "input[name='subject']",
        "input#subject",
        "input[name='title']",
        "input#title",
    ]:
        els = drv.find_elements(By.CSS_SELECTOR, sel)
        if els:
            return els[0]
    return None


def ensure_write_page(drv, list_url: str, write_url: str) -> None:
    # 1) write_url 직접 접근
    drv.get(write_url)
    wait_ready(drv, 15)
    accept_all_alerts(drv)

    if find_subject(drv) is not None:
        log("✅ 글쓰기 페이지(직접 URL) 진입 성공")
        return

    # 2) 목록에서 글쓰기 버튼 클릭(보험)
    drv.get(list_url)
    wait_ready(drv, 15)
    accept_all_alerts(drv)

    btns = drv.find_elements(By.CSS_SELECTOR, "a.btn_lsmall, a[href*='write.php']")
    for b in btns:
        try:
            if b.is_enabled() and ("글쓰기" in (b.text or "")):
                b.click()
                time.sleep(0.5)
                accept_all_alerts(drv)
                wait_ready(drv, 15)
                if find_subject(drv) is not None:
                    log("✅ 글쓰기 페이지(리스트→버튼) 진입 성공")
                    return
        except Exception:
            continue

    raise RuntimeError("글쓰기 페이지로 진입하지 못했습니다.")


# ──────────────────────────────
# SmartEditor2(memo) body set
# ──────────────────────────────
def wait_editor_ready(drv):
    """
    memo textarea 또는 oEditors.getById['memo']가 준비될 때까지 대기
    """
    WebDriverWait(drv, 20).until(
        lambda d: d.find_elements(By.CSS_SELECTOR, "textarea#memo, textarea[name='memo']")
        or d.execute_script(
            "return (typeof window.oEditors !== 'undefined') && window.oEditors && oEditors.getById && oEditors.getById['memo'];"
        )
    )


def set_body_textarea_memo(drv, body: str) -> bool:
    tas = drv.find_elements(By.CSS_SELECTOR, "textarea#memo, textarea[name='memo']")
    if not tas:
        return False
    drv.execute_script("arguments[0].value = arguments[1];", tas[0], body)
    return True


def set_body_oeditors_memo(drv, body: str) -> str:
    """
    oEditors API로 memo에 SET_CONTENTS / UPDATE_CONTENTS_FIELD
    """
    html = body.replace("\n", "<br>")
    return drv.execute_script(
        """
        const html = arguments[0];
        try {
            if (window.oEditors && oEditors.getById && oEditors.getById['memo']) {
                oEditors.getById['memo'].exec('SET_CONTENTS', [html]);
                oEditors.getById['memo'].exec('UPDATE_CONTENTS_FIELD', []);
                return 'OK:memo';
            }
            return 'NO_EDITORS';
        } catch(e) {
            return 'ERR:' + e.toString();
        }
        """,
        html,
    )


def sync_editor_before_submit(drv):
    """
    등록 직전 한번 더 textarea 동기화(있으면 성공률↑)
    """
    try:
        drv.execute_script(
            """
            try {
                if (window.oEditors && oEditors.getById && oEditors.getById['memo']) {
                    oEditors.getById['memo'].exec('UPDATE_CONTENTS_FIELD', []);
                }
            } catch(e) {}
            """
        )
    except Exception:
        pass


def set_post_body(drv, body: str):
    """
    본문 입력 통합(가장 안정적인 순서):
    1) textarea#memo value 세팅(제출값 직접)
    2) oEditors가 있으면 UI/textarea 동기화까지 수행
    """
    log("본문 입력 시작… (memo)")

    wait_editor_ready(drv)

    # 1) textarea 먼저 세팅 (가장 확실)
    if set_body_textarea_memo(drv, body):
        log("본문 입력 완료 ✓ (textarea#memo)")
    else:
        log("⚠ textarea#memo 미탐지")

    # 2) oEditors 있으면 한번 더 세팅/동기화 (선택 but 유용)
    try:
        res = set_body_oeditors_memo(drv, body)
        log(f"oEditors 결과: {res}")
        if isinstance(res, str) and res.startswith("OK:"):
            log("본문 동기화 완료 ✓ (oEditors:memo)")
    except Exception as e:
        log(f"⚠ oEditors 예외(무시하고 진행): {repr(e)}")

    # 최종 검증: textarea 값이 들어갔는지 확인(짧게)
    try:
        v = drv.execute_script(
            "const t=document.querySelector('textarea#memo,textarea[name=memo]'); return t ? (t.value || '') : null;"
        )
        if v is None or len(v.strip()) == 0:
            raise RuntimeError("textarea#memo 값이 비어있습니다.")
    except Exception as e:
        raise RuntimeError(f"본문 입력 검증 실패: {repr(e)}")


# ──────────────────────────────
# Main
# ──────────────────────────────
def main():
    load_dotenv()

    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=DEFAULT_WRITE_URL, help="글쓰기 URL")
    ap.add_argument("--list-url", default=DEFAULT_LIST_URL, help="글 목록 URL")
    ap.add_argument("--no-excel", action="store_true", help="엑셀 없이 테스트 본문/제목 사용")
    ap.add_argument("--close", action="store_true", help="작업 후 브라우저 닫기")
    args = ap.parse_args()

    drv, profile_info = setup_driver()
    log(f"프로필 정보: {profile_info}")

    try:
        ensure_login(drv, args.list_url)
        ensure_write_page(drv, args.list_url, args.url)

        # 콘텐츠 준비
        wb = ws = row = None
        if args.no_excel:
            title = "테스트 제목입니다 (자동화)"
            body = "테스트 본문 입니다.\n자동화 확인용."
        else:
            # 엑셀 없으면 자동으로 테스트 모드로 전환
            try:
                wb, ws, row, title, body = load_next_row()
                if not row:
                    log("대기 중인 업로드 건이 없습니다.")
                    return
            except FileNotFoundError as e:
                log(f"⚠ {e} → --no-excel처럼 테스트 데이터로 진행합니다.")
                title = "테스트 제목입니다 (자동화)"
                body = "테스트 본문 입니다.\n자동화 확인용."

        # 제목 입력
        ti = find_subject(drv)
        if not ti:
            raise RuntimeError("제목 입력 필드를 찾을 수 없습니다.")
        ti.clear()
        ti.send_keys(title)
        log("제목 입력 완료 ✓")

        # 본문 입력
        set_post_body(drv, body)

        # 제출 버튼 찾기
        submit_btn = None
        for xp in [
            "//button[contains(.,'등록') or contains(.,'작성') or contains(.,'저장')]",
            "//input[@type='submit']",
        ]:
            btns = drv.find_elements(By.XPATH, xp)
            if btns:
                submit_btn = btns[0]
                break

        if submit_btn is None:
            raise RuntimeError("제출 버튼을 찾을 수 없습니다.")

        # 등록 직전 동기화
        sync_editor_before_submit(drv)

        # JS 클릭
        drv.execute_script("arguments[0].click();", submit_btn)
        time.sleep(0.7)
        accept_all_alerts(drv)
        wait_ready(drv, 15)

        log("등록 버튼 클릭 ✓")

        # 엑셀 DONE 처리
        if wb and ws and row:
            mark_done(wb, ws, row)
            log("✅ 업로드 완료 → DONE 처리")

    except UnexpectedAlertPresentException:
        try:
            a = drv.switch_to.alert
            log(f"❌ 알럿으로 인해 중단되었습니다. 메시지: {a.text}")
            a.accept()
        except Exception:
            pass

    except Exception as e:
        log(f"❌ 오류 타입: {type(e)}")
        log(f"❌ 오류 repr: {repr(e)}")
        log("❌ 스택트레이스:")
        log(traceback.format_exc())

    finally:
        if args.close:
            try:
                drv.quit()
            except Exception:
                pass
        else:
            log("브라우저는 열어둡니다. 작업 내용을 확인하세요.")


if __name__ == "__main__":
    main()
