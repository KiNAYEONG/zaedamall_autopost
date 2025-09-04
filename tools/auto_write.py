# -*- coding: utf-8 -*-
"""
재다몰 글쓰기 자동화 (Selenium + Excel 연동 + 자동 로그인 + 시크릿 모드)
"""

from __future__ import annotations
import os, time, random, argparse, datetime as dt
from pathlib import Path
from typing import List
import openpyxl, requests

from selenium.webdriver import Chrome
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager

ROOT = Path(__file__).resolve().parent
DOCS = ROOT.parent / "docs"
XLSX = DOCS / "data.xlsx"

# --------------------------
# 유틸
# --------------------------
def log(msg: str):
    print(msg, flush=True)

def env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name)
    return v if (v is not None and str(v).strip() != "") else default

def now_str():
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M")

# --------------------------
# 엑셀 로드/저장
# --------------------------
def load_next_post() -> dict | None:
    if not XLSX.exists():
        log(f"❌ Excel 파일 없음: {XLSX}")
        return None

    wb = openpyxl.load_workbook(XLSX)
    ws = wb.active

    for row in ws.iter_rows(min_row=2, values_only=False):
        title, body, status, updated, img_query = row[:5]
        if status.value != "DONE":
            return {
                "row": row,
                "title": title.value or "",
                "body": body.value or "",
                "img_query": img_query.value or "건강",
                "sheet": ws,
                "wb": wb,
            }
    return None

def mark_done(row, ws, wb):
    row[2].value = "DONE"
    row[3].value = now_str()
    wb.save(XLSX)
    log("📊 Excel 상태 갱신 완료")

# --------------------------
# 드라이버 (시크릿 모드)
# --------------------------
def setup_driver() -> Chrome:
    opts = Options()
    opts.add_argument("--start-maximized")
    opts.add_argument("--disable-notifications")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--disable-infobars")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)

    # 🚀 시크릿 모드
    opts.add_argument("--incognito")

    # PC User-Agent 강제
    opts.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )

    log("🌐 Chrome 실행 준비 중 (시크릿 모드)...")
    drv = Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    time.sleep(2)
    return drv

# --------------------------
# 로그인
# --------------------------
def auto_login(drv: Chrome, target_url: str) -> bool:
    user = env("ZAEDA_ID")
    pw = env("ZAEDA_PW")
    if not user or not pw:
        log("⚠️ ID/PW 환경변수 없음 → 자동로그인 생략")
        return False

    try:
        log("🔍 로그인 버튼 탐색 중...")
        btn = drv.find_element(By.CSS_SELECTOR, "#tnb_inner > ul > li:nth-child(1) > a")
        btn.click()
        log("➡️ 로그인 버튼 클릭 완료")
        time.sleep(1)

        id_input = drv.find_element(By.ID, "login_id")
        pw_input = drv.find_element(By.ID, "login_pw")
        try: id_input.clear()
        except: pass
        try: pw_input.clear()
        except: pass
        id_input.send_keys(user)
        pw_input.send_keys(pw)

        try:
            submit = drv.find_element(By.CSS_SELECTOR, "form[name='flogin'] input[type=submit]")
        except:
            submit = drv.find_element(By.CSS_SELECTOR, "form[name='flogin'] button")
        submit.click()
        log("🔑 로그인 시도 완료")
        time.sleep(2)

        if "로그아웃" in drv.page_source:
            log("🔓 로그인 성공 감지됨")
            drv.get(target_url)
            return True

        try:
            alert = drv.switch_to.alert
            msg = alert.text
            log(f"⚠️ 로그인 실패 알럿 감지: {msg}")
            alert.accept()
        except Exception:
            log("⚠️ 로그인 실패 → 알럿 없음")

        return False

    except Exception as e:
        log(f"❌ 로그인 중 에러: {e}")
        return False

# --------------------------
# 이미지
# --------------------------
def build_unsplash_remote_urls(query: str, n: int) -> List[str]:
    base = "https://source.unsplash.com/900x600"
    return [
        f"{base}/?{requests.utils.quote(query)}&sig={random.randint(1,999999)}"
        for _ in range(n)
    ]

# --------------------------
# 작성/제출
# --------------------------
def fill_title(drv, title: str):
    inputs = drv.find_elements(By.CSS_SELECTOR, "input[type='text']")
    if not inputs:
        raise NoSuchElementException("제목 입력창 없음")
    target = max(inputs, key=lambda e: e.size.get("width", 0))
    target.clear()
    target.send_keys(title)
    log("📝 제목 입력 완료")

def fill_body(drv, body_text: str):
    try:
        ta = drv.find_element(By.CSS_SELECTOR, "textarea")
        ta.clear()
        ta.send_keys(body_text)
        log("📄 본문 입력 완료")
    except Exception:
        log("⚠️ 본문 입력 실패")

def set_secret_check(drv, enable: bool):
    if not enable:
        return
    try:
        el = drv.find_element(By.XPATH, "//*[contains(text(),'비밀글')]/preceding::input[@type='checkbox'][1]")
        if not el.is_selected():
            el.click()
        log("🔒 비밀글 체크 ✓")
    except Exception:
        pass

def submit_post(drv: Chrome):
    try:
        btns = drv.find_elements(By.CSS_SELECTOR, "#con_lf form .rbt_box a")
        if btns:
            btns[-1].click()
            log("✅ 글쓰기 버튼 클릭")
            return
    except Exception:
        pass
    log("⚠️ 글쓰기/등록 버튼을 끝내 찾지 못했습니다. 브라우저에서 직접 확인하세요.")

# --------------------------
# 메인
# --------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True, help="글쓰기 URL")
    ap.add_argument("--secret", type=int, default=int(env("SECRET_DEFAULT", "1")))
    ap.add_argument("--image-count", type=int, default=2)
    args = ap.parse_args()

    post = load_next_post()
    if not post:
        log("📭 업로드할 포스트 없음")
        return

    drv = setup_driver()
    try:
        drv.get("https://zae-da.com")

        if not auto_login(drv, args.url):
            log("👉 자동로그인 실패 → 브라우저에서 직접 로그인하세요 (최대 3분)")
            input("로그인 완료했으면 Enter ▶ ")
            drv.get(args.url)

        fill_title(drv, post["title"])
        fill_body(drv, post["body"])
        set_secret_check(drv, enable=(args.secret == 1))

        urls = build_unsplash_remote_urls(post["img_query"], args.image_count)
        log(f"🖼️ 이미지 URL {len(urls)}개 준비됨")

        submit_post(drv)
        mark_done(post["row"], post["sheet"], post["wb"])
        log("🎉 업로드 완료")

    finally:
        log("✅ 종료(브라우저는 수동 닫기)")

if __name__ == "__main__":
    main()
