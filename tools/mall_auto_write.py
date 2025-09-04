# -*- coding: utf-8 -*-
"""
zae-da 게시글 자동 작성 (웹/모바일 겸용)
- 글쓰기 진입: 리스트 → '글쓰기' 버튼 or 직접 write URL
- 제목/본문 입력
- 이미지 업로드: input[type=file] → 에디터 사진아이콘 → HTML <img> Fallback
- 비밀글: .env의 MALL_SECRET_DEFAULT=1 이면 체크
"""

from __future__ import annotations
import os, time, sys, random, tempfile, urllib.request
from pathlib import Path
from dataclasses import dataclass
from typing import Iterable, List, Tuple, Optional

from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver import Chrome
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.alert import Alert
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

MAX_WAIT = 10
ROOT = Path(__file__).resolve().parent
DOCS = ROOT.parent / "docs"
XLSX = DOCS / "data.xlsx"

# -----------------------
# 유틸
# -----------------------
def log(msg: str): print(msg, flush=True)

def wait_ready(drv: Chrome, timeout: int = MAX_WAIT):
    WebDriverWait(drv, timeout).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )

def find_any(drv: Chrome, candidates: Iterable[Tuple[str, str]], timeout: int = 5):
    last_err = None
    for by, sel in candidates:
        try:
            el = WebDriverWait(drv, timeout).until(EC.presence_of_element_located((by, sel)))
            return el, (by, sel)
        except Exception as e:
            last_err = e
    raise last_err or RuntimeError("element not found for any selector")

def click_any(drv: Chrome, candidates: Iterable[Tuple[str, str]], timeout: int = 5) -> bool:
    try:
        el, used = find_any(drv, candidates, timeout)
        drv.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        el.click()
        return True
    except Exception:
        return False

def send_keys_any(drv: Chrome, text: str, candidates: Iterable[Tuple[str, str]], clear=True, timeout: int = 5) -> bool:
    try:
        el, used = find_any(drv, candidates, timeout)
        drv.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        if clear:
            try: el.clear()
            except Exception: pass
        el.send_keys(text)
        return True
    except Exception:
        return False

def accept_all_alerts(drv: Chrome, limit=3):
    for _ in range(limit):
        try:
            a = WebDriverWait(drv, 1).until(EC.alert_is_present())
            txt = a.text
            log(f"⚠️ 알럿: {txt}")
            a.accept()
            time.sleep(0.2)
        except Exception:
            break

# -----------------------
# 모드 판별 & 셀렉터
# -----------------------
@dataclass
class ModeSelectors:
    title: List[Tuple[str, str]]
    body_textarea: List[Tuple[str, str]]     # 순수 textarea
    body_iframe: List[Tuple[str, str]]       # 에디터 iframe (본문은 iframe 내부 body에 입력)
    photo_icon: List[Tuple[str, str]]        # 에디터 사진 아이콘
    file_input: List[Tuple[str, str]]        # 파일 업로더 직접 접근
    secret_checkbox: List[Tuple[str, str]]
    submit_btn: List[Tuple[str, str]]
    write_button_on_list: List[Tuple[str, str]]

def detect_mode(drv: Chrome) -> str:
    url = drv.current_url.lower()
    if "/m/" in url or url.endswith("/m") or url.split("//")[1].startswith("m."):
        return "mobile"
    # 바디에 모바일 힌트가 있으면 mobile
    try:
        cls = drv.find_element(By.TAG_NAME, "body").get_attribute("class") or ""
        if "mobile" in cls.lower():
            return "mobile"
    except Exception:
        pass
    return "web"

WEB = ModeSelectors(
    title=[(By.CSS_SELECTOR, "input[name='title']"), (By.CSS_SELECTOR, "input#title"), (By.CSS_SELECTOR, "input[type='text']")],
    body_textarea=[(By.CSS_SELECTOR, "textarea[name='contents']"), (By.CSS_SELECTOR, "textarea#contents"), (By.CSS_SELECTOR, "textarea")],
    body_iframe=[(By.CSS_SELECTOR, "iframe[name='ir1']"), (By.CSS_SELECTOR, "iframe#ir1"), (By.CSS_SELECTOR, "div.editor iframe")],
    photo_icon=[(By.CSS_SELECTOR, "img[alt='사진']"), (By.CSS_SELECTOR, "button[title*='사진']"), (By.CSS_SELECTOR, "a[title*='사진']")],
    file_input=[(By.CSS_SELECTOR, "input[type='file'][name^='bf_file']"), (By.CSS_SELECTOR, "input[type='file']")],
    secret_checkbox=[(By.CSS_SELECTOR, "input[name='is_secret']"), (By.CSS_SELECTOR, "input#is_secret"), (By.XPATH, "//label[contains(.,'비밀글')]/input[@type='checkbox']")],
    submit_btn=[(By.CSS_SELECTOR, "input[type='submit'][value*='등록']"), (By.CSS_SELECTOR, "button[type='submit']"), (By.XPATH, "//button[contains(.,'글쓰기') or contains(.,'등록')]")],
    write_button_on_list=[(By.CSS_SELECTOR, "a[href*='write.php?boardid=']"), (By.XPATH, "//a[contains(.,'글쓰기')]")]
)

MOBILE = ModeSelectors(
    title=[(By.CSS_SELECTOR, "input[name='title']"), (By.CSS_SELECTOR, "input#title"), (By.CSS_SELECTOR, "input[type='text']")],
    body_textarea=[(By.CSS_SELECTOR, "textarea[name='memo']"), (By.CSS_SELECTOR, "textarea#memo"), (By.CSS_SELECTOR, "textarea")],
    body_iframe=[(By.CSS_SELECTOR, "iframe[name='ir1']"), (By.CSS_SELECTOR, "div.editor iframe")],
    photo_icon=[(By.CSS_SELECTOR, "img[alt='사진']"), (By.CSS_SELECTOR, "button[title*='사진']"), (By.CSS_SELECTOR, "a[title*='사진']")],
    file_input=[(By.CSS_SELECTOR, "input[type='file'][name^='bf_file']"), (By.CSS_SELECTOR, "input[type='file']")],
    secret_checkbox=[(By.CSS_SELECTOR, "input[name='is_secret']"), (By.XPATH, "//label[contains(.,'비밀글')]/input[@type='checkbox']")],
    submit_btn=[(By.XPATH, "//button[contains(.,'글쓰기')]"), (By.CSS_SELECTOR, "input[type='submit']")],
    write_button_on_list=[(By.CSS_SELECTOR, "a[href*='board_write.php?boardid=']"), (By.XPATH, "//a[contains(.,'글쓰기')]")]
)

def get_selectors(mode: str) -> ModeSelectors:
    return MOBILE if mode == "mobile" else WEB

# -----------------------
# 드라이버 & 로그인
# -----------------------
def setup_driver() -> Chrome:
    load_dotenv()
    opts = webdriver.ChromeOptions()

    # 사용자 프로필 (있으면 우선 사용)
    ud = os.getenv("CHROME_USER_DATA_DIR")
    prof = os.getenv("CHROME_PROFILE")
    if ud:
        opts.add_argument(f"--user-data-dir={ud}")
    if prof:
        opts.add_argument(f"--profile-directory={prof}")

    # 창 자동 종료 방지/안정화
    opts.add_argument("--disable-gpu")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--start-maximized")

    try:
        drv = Chrome(service=Service(ChromeDriverManager().install()), options=opts)
        return drv
    except Exception as e:
        log(f"[chrome] primary profile failed → {e}")
        # Fallback 프로필
        fb = os.getenv("CHROME_FALLBACK_DIR", r"C:\ChromeProfiles\zaeda_selenium")
        Path(fb).mkdir(parents=True, exist_ok=True)
        opts = webdriver.ChromeOptions()
        opts.add_argument(f"--user-data-dir={fb}")
        opts.add_argument("--start-maximized")
        drv = Chrome(service=Service(ChromeDriverManager().install()), options=opts)
        log(f"[chrome] fallback profile launched: {fb}\n  ↳ 폴백 창에서 재다몰에 1회 로그인하면 이후 자동 유지됩니다.")
        return drv

def ensure_login(drv: Chrome, any_url_in_site: str):
    """로그인 상태가 아니면 로그인 페이지로 유도하고 수동로그인 자동 감지"""
    wait_ready(drv)
    # 로그인 필요 신호: '로그인' 링크, 'member/login' 등
    html = drv.page_source.lower()
    need = ("login.php" in drv.current_url.lower()) or ("로그인" in html and "로그아웃" not in html)

    if need:
        log("👉 로그인 페이지로 이동해 수동 로그인 해주세요. (최대 3분 내 자동 감지)")
        start = time.time()
        while time.time() - start < 180:
            time.sleep(1.5)
            try:
                if "로그아웃" in drv.page_source:
                    log("🔓 로그인 감지됨")
                    return
            except Exception:
                pass
        raise RuntimeError("로그인 감지 실패")
    else:
        return

# -----------------------
# 네비게이션/진입
# -----------------------
def ensure_write_page(drv: Chrome, list_url: Optional[str], write_url: Optional[str]):
    """리스트→글쓰기 or write_url 직접. 두 모드 모두 대응."""
    # 1) 우선 주어진 URL로 이동
    target = write_url or list_url
    if not target:
        raise RuntimeError("write_url 또는 list_url 중 하나는 필요합니다.")

    drv.get(target)
    wait_ready(drv)
    accept_all_alerts(drv)

    mode = detect_mode(drv)
    sel = get_selectors(mode)

    # 이미 write 폼이면 통과 (제목/본문 존재 확인)
    if send_keys_any(drv, "", sel.title, clear=False) or send_keys_any(drv, "", sel.body_textarea, clear=False):
        log(f"✅ 글쓰기 페이지({mode}) 진입 확인")
        return

    # 리스트라면 글쓰기 버튼 클릭
    if list_url:
        drv.get(list_url)
        wait_ready(drv)
        if click_any(drv, sel.write_button_on_list):
            time.sleep(0.5)
            wait_ready(drv)
            accept_all_alerts(drv)
            mode = detect_mode(drv)
            sel = get_selectors(mode)
            if send_keys_any(drv, "", sel.title, clear=False) or send_keys_any(drv, "", sel.body_textarea, clear=False):
                log(f"✅ 글쓰기 페이지(리스트→버튼, {mode}) 진입 성공")
                return

    # write_url을 데스크톱/모바일 모두 시도
    base = target
    if "/m/" in base:
        alt = base.replace("/m/", "/bbs/")
    else:
        alt = base.replace("/bbs/", "/m/bbs/")
    for u in [target, alt]:
        drv.get(u)
        wait_ready(drv)
        if send_keys_any(drv, "", sel.title, clear=False) or send_keys_any(drv, "", sel.body_textarea, clear=False):
            log(f"✅ 글쓰기 페이지(대안 URL, {detect_mode(drv)}) 진입 성공")
            return

    raise RuntimeError("글쓰기 페이지로 진입하지 못했습니다.")

# -----------------------
# 본문/이미지
# -----------------------
UNSPLASH_TOPICS = [
    "health lifestyle", "healthy food korean", "fitness walking", "office commute",
    "sleep wellness", "korean meal table", "city morning jog"
]

def download_unsplash_samples(n=2) -> List[str]:
    """간단한 샘플 이미지 다운로드 (저작권 고지 필요 시 본문에 출처 문구 삽입 권장)"""
    saved = []
    tmpdir = Path(tempfile.mkdtemp(prefix="zaeda_"))
    for i in range(n):
        kw = random.choice(UNSPLASH_TOPICS)
        # 1024x768 랜덤 이미지
        url = f"https://source.unsplash.com/1024x768/?{urllib.parse.quote(kw)}"
        dst = tmpdir / f"unsplash_{i+1}.jpg"
        try:
            urllib.request.urlretrieve(url, dst)
            saved.append(str(dst))
        except Exception:
            pass
    return saved

def set_body(drv: Chrome, sel: ModeSelectors, text: str) -> bool:
    """textarea → iframe 순으로 시도"""
    # 1) textarea
    if send_keys_any(drv, text, sel.body_textarea, clear=True):
        log("본문 입력 완료 ✓ (textarea)")
        return True
    # 2) iframe editor
    try:
        iframe, _ = find_any(drv, sel.body_iframe, timeout=2)
        drv.switch_to.frame(iframe)
        body = WebDriverWait(drv, 3).until(EC.presence_of_element_located((By.CSS_SELECTOR, "body")))
        drv.execute_script("arguments[0].innerHTML = '';", body)
        body.send_keys(text)
        drv.switch_to.default_content()
        log("본문 입력 완료 ✓ (iframe editor)")
        return True
    except Exception:
        pass
    return False

def try_upload_files(drv: Chrome, sel: ModeSelectors, files: List[str]) -> bool:
    """input[type=file] → 에디터 사진아이콘 순으로 업로드 시도"""
    # 1) 파일 입력 직접
    try:
        file_el, used = find_any(drv, sel.file_input, timeout=2)
        for p in files[:10]:
            file_el.send_keys(p)
            time.sleep(0.3)
        log(f"이미지 업로드 완료 ✓ (file input, {len(files[:10])}장)")
        return True
    except Exception:
        pass

    # 2) 사진 아이콘 클릭 → 파일 입력 노출
    if click_any(drv, sel.photo_icon, timeout=1):
        time.sleep(0.4)
        try:
            file_el, _ = find_any(drv, [(By.CSS_SELECTOR, "input[type='file']")], timeout=3)
            for p in files[:10]:
                file_el.send_keys(p)
                time.sleep(0.4)
            log(f"이미지 업로드 완료 ✓ (photo icon, {len(files[:10])}장)")
            return True
        except Exception:
            pass

    return False

def fallback_insert_img_html(drv: Chrome, sel: ModeSelectors, urls: List[str]) -> bool:
    """업로드가 모두 실패하면 본문에 <img> HTML로 삽입"""
    html = "".join([f'<p><img src="{u}" alt="image" style="max-width:100%;height:auto"/></p>' for u in urls])
    # textarea 우선
    if send_keys_any(drv, html, sel.body_textarea, clear=False):
        return True
    # iframe
    try:
        iframe, _ = find_any(drv, sel.body_iframe, timeout=2)
        drv.switch_to.frame(iframe)
        body = WebDriverWait(drv, 3).until(EC.presence_of_element_located((By.CSS_SELECTOR, "body")))
        drv.execute_script("arguments[0].insertAdjacentHTML('beforeend', arguments[1]);", body, html)
        drv.switch_to.default_content()
        return True
    except Exception:
        pass
    return False

# -----------------------
# 제출
# -----------------------
def set_secret_if_needed(drv: Chrome, sel: ModeSelectors):
    if os.getenv("MALL_SECRET_DEFAULT", "1") == "1":
        click_any(drv, sel.secret_checkbox, timeout=1)

def submit_post(drv: Chrome, sel: ModeSelectors):
    if click_any(drv, sel.submit_btn, timeout=2):
        time.sleep(0.8)
        accept_all_alerts(drv)
        log("📤 제출 시도")
        return
    raise Exception("등록/글쓰기 버튼 클릭 실패")

# -----------------------
# 메인
# -----------------------
def main():
    load_dotenv()

    # 입력값 준비
    write_url = os.getenv("WRITE_URL", "https://zae-da.com/bbs/write.php?boardid=41")
    list_url = os.getenv("LIST_URL",  "https://zae-da.com/bbs/list.php?boardid=41")
    mobile_write = write_url.replace("/bbs/", "/m/bbs/")
    mobile_list  = list_url.replace("/bbs/", "/m/bbs/")

    # 제목/본문 샘플 (run_post.py가 넘겨줄 수도 있음)
    title = os.getenv("POST_TITLE", "[만성질환 관리/당뇨 관리] 테스트 제목")
    body  = os.getenv("POST_BODY",  "테스트 본문 입니다.\n자동화 확인용.")

    drv = setup_driver()
    try:
        # 진입(모드 불문)
        try:
            ensure_write_page(drv, list_url, write_url)
        except Exception:
            ensure_write_page(drv, mobile_list, mobile_write)

        ensure_login(drv, write_url)
        wait_ready(drv)
        accept_all_alerts(drv)

        mode = detect_mode(drv)
        sel = get_selectors(mode)

        # 제목/본문
        if not send_keys_any(drv, title, sel.title):
            raise RuntimeError("제목 입력 실패")
        if not set_body(drv, sel, body):
            raise RuntimeError("본문 입력 실패")

        # 이미지: 다운로드 → 업로드 → 실패시 HTML src 삽입
        files = download_unsplash_samples(n=3)
        if files:
            ok = try_upload_files(drv, sel, files)
            if not ok:
                # HTML로 직접 삽입 (다운로드했던 파일은 사용할 수 없으니 Unsplash URL로 다시)
                urls = [f"https://source.unsplash.com/1024x768/?health,{i}" for i in range(3)]
                if fallback_insert_img_html(drv, sel, urls):
                    log("이미지 삽입 완료 ✓ (HTML fallback)")
        else:
            # 바로 HTML로
            urls = [f"https://source.unsplash.com/1024x768/?health,{i}" for i in range(3)]
            if fallback_insert_img_html(drv, sel, urls):
                log("이미지 삽입 완료 ✓ (HTML fallback, no download)")

        # 비밀글(테스트 기본 on)
        set_secret_if_needed(drv, sel)

        # 제출
        submit_post(drv, sel)
        log("✅ 종료")
    finally:
        # 필요시 닫지 말고 유지하려면 주석
        # drv.quit()
        pass

if __name__ == "__main__":
    main()
