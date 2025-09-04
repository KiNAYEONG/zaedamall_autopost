# -*- coding: utf-8 -*-
"""
재다몰 글쓰기 자동화 (Selenium + Excel 연동 + 자동 로그인)
- Excel의 data.xlsx 에서 1건 읽어 자동 발행
- 로그인: 환경변수 ZAEDA_ID / ZAEDA_PW 기반 자동 로그인
- 로그인 성공 시 글쓰기 페이지로 자동 이동 (--url)
- 제목/본문 입력
- 비밀글 체크(기본 ON, SECRET_DEFAULT=0 이면 OFF)
- 이미지 첨부: HTML 주입 (<img src="https://..."> Unsplash 원격 URL)
- 게시 성공 시 해당 행 상태를 DONE 으로 변경

엑셀 헤더:
제목 | 본문 | 상태 | 업데이트시각 | 이미지검색어
"""

from __future__ import annotations
import os, sys, time, random, argparse, datetime as dt
from pathlib import Path
from typing import List
import openpyxl, requests

from selenium.webdriver import Chrome
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from webdriver_manager.chrome import ChromeDriverManager

ROOT = Path(__file__).resolve().parent
DOCS = ROOT.parent / "docs"
XLSX = DOCS / "data.xlsx"

MAX_WAIT = 12

def log(msg: str): print(msg, flush=True)

def env(name: str, default: str | None = None) -> str | None:
    v = os.environ.get(name)
    return v if (v is not None and str(v).strip() != "") else default

def now_str(): return dt.datetime.now().strftime("%Y-%m-%d %H:%M")

# ---------------- Excel ----------------
def load_next_post() -> dict | None:
    if not XLSX.exists():
        log(f"❌ Excel 파일 없음: {XLSX}")
        return None
    wb = openpyxl.load_workbook(XLSX)
    ws = wb.active
    for row in ws.iter_rows(min_row=2, values_only=False):
        if len(row) < 5: continue
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

# ---------------- Driver ----------------
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
    opts.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/120.0.0.0 Safari/537.36")
    profile_dir = env("ZAEDA_PROFILE_DIR", r"C:\ChromeProfiles\zaeda")
    opts.add_argument(f"--user-data-dir={profile_dir}")
    log("🌐 Chrome 실행 준비 중...")
    drv = Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    time.sleep(2)
    return drv

# ---------------- Login ----------------

def auto_login(drv, target_url: str):
    """환경변수 ZAEDA_ID / ZAEDA_PW 로 자동 로그인 → 글쓰기 페이지 이동"""
    user = env("ZAEDA_ID")
    pw = env("ZAEDA_PW")
    if not user or not pw:
        log("⚠️ ID/PW 환경변수 없음 → 자동로그인 생략")
        return

    try:
        log("🔍 로그인 버튼 탐색 중...")

        # PC 버전 강제 (이미 setup_driver 에 UA 적용됨)
        drv.get("https://zae-da.com/")  

        # 1️⃣ 기본 셀렉터 (PC 버전)
        try:
            btn = WebDriverWait(drv, 10).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "#tnb_inner > ul > li:nth-child(1) > a"))
            )
        except TimeoutException:
            # 2️⃣ 대체 셀렉터 (링크 텍스트 기반)
            try:
                btn = WebDriverWait(drv, 5).until(
                    EC.element_to_be_clickable((By.LINK_TEXT, "입점사 로그인"))
                )
            except TimeoutException:
                raise NoSuchElementException("로그인 버튼을 찾지 못했습니다.")

        drv.execute_script("arguments[0].click();", btn)  # JS 클릭 (가려진 경우 대비)
        log("➡️ 로그인 버튼 클릭 완료")
        WebDriverWait(drv, 10).until(EC.presence_of_element_located((By.ID, "login_id")))

        # 3️⃣ 아이디/비번 입력
        drv.find_element(By.ID, "login_id").send_keys(user)
        drv.find_element(By.ID, "login_pw").send_keys(pw)

        # 4️⃣ 로그인 버튼 클릭
        try:
            submit_btn = drv.find_element(By.CSS_SELECTOR, "form[name='flogin'] input[type=submit]")
        except:
            submit_btn = drv.find_element(By.CSS_SELECTOR, "form[name='flogin'] button")

        drv.execute_script("arguments[0].click();", submit_btn)
        log("🔑 로그인 시도 완료")

        # 5️⃣ 글쓰기 페이지 이동
        WebDriverWait(drv, 10).until(EC.url_changes(drv.current_url))
        drv.get(target_url)
        log("✅ 로그인 성공 → 글쓰기 페이지 이동")

    except Exception as e:
        log(f"❌ 자동로그인 실패: {e}")

# ---------------- Images ----------------
def build_unsplash_remote_urls(query: str, n: int) -> List[str]:
    base = "https://source.unsplash.com/900x600"
    return [f"{base}/?{requests.utils.quote(query)}&sig={random.randint(1,999999)}" for _ in range(n)]

def inject_images_html(drv: Chrome, urls: List[str], width: int = 900):
    if not urls: return False
    try:
        tts = drv.find_elements(By.TAG_NAME, "textarea")
        if tts:
            target = max(tts, key=lambda e: e.size.get("width", 0)*e.size.get("height",0))
            snippet = "\n".join([f'<p><img src="{u}" style="max-width:{width}px;width:100%;height:auto;"/></p>' for u in urls])
            prev = target.get_attribute("value") or ""
            target.clear()
            target.send_keys(prev + ("\n\n" if prev else "") + snippet)
            log("🧩 HTML 모드로 이미지 주입 완료")
            return True
    except Exception: pass
    return False

# ---------------- Write ----------------
def fill_title(drv, title: str):
    inputs = drv.find_elements(By.CSS_SELECTOR, "input[type='text']")
    if not inputs: raise NoSuchElementException("제목 입력창 없음")
    target = max(inputs, key=lambda e: e.size.get("width", 0))
    if not title.startswith("["):  # 중복 방지
        title = "[자동발행] " + title
    target.clear()
    target.send_keys(title)
    log("📝 제목 입력 완료")

def fill_body(drv, body_text: str):
    try:
        ta = drv.find_element(By.CSS_SELECTOR, "textarea")
        ta.clear()
        ta.send_keys(body_text)
        log("📄 본문 입력 완료")
    except Exception: log("⚠️ 본문 입력 실패")

def set_secret_check(drv, enable: bool):
    if not enable: return
    try:
        el = drv.find_element(By.XPATH, "//*[contains(text(),'비밀글')]/preceding::input[@type='checkbox'][1]")
        if not el.is_selected(): el.click()
        log("🔒 비밀글 체크 ✓")
    except Exception: pass

def submit_post(drv: Chrome):
    try:
        btns = drv.find_elements(By.XPATH, "//button[contains(.,'글쓰기')]")
        if btns: 
            btns[-1].click()
            log("✅ 글쓰기 버튼 클릭")
            return
    except Exception: pass
    raise NoSuchElementException("등록 버튼을 찾지 못했습니다.")

# ---------------- Main ----------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=True, help="글쓰기 URL")
    ap.add_argument("--secret", type=int, default=int(env("SECRET_DEFAULT", "1")), help="비밀글(1)/일반글(0)")
    ap.add_argument("--image-count", type=int, default=2, help="이미지 개수")
    args = ap.parse_args()

    post = load_next_post()
    if not post:
        log("📭 업로드할 포스트 없음")
        return

    drv = setup_driver()
    try:
        drv.get(args.url)
        auto_login(drv, args.url)
        fill_title(drv, post["title"])
        fill_body(drv, post["body"])
        set_secret_check(drv, enable=(args.secret == 1))
        urls = build_unsplash_remote_urls(post["img_query"], args.image_count)
        inject_images_html(drv, urls)
        submit_post(drv)
        mark_done(post["row"], post["sheet"], post["wb"])
        log("🎉 업로드 완료")
    finally:
        log("✅ 종료(브라우저는 수동 닫기)")

if __name__ == "__main__":
    main()
