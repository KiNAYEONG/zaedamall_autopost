# tools/mall_auto_write.py
# -*- coding: utf-8 -*-
r"""
재다몰 자동 업로드 (로그인 유도 포함 · 크롬 독립 세션)
- .env의 CHROME_USER_DATA_DIR (예: ...\Chrome\User Data) + CHROME_PROFILE (예: Profile 18) 사용
- 로그인 안 된 경우: https://zae-da.com/ 열어서 로그인 유도 → 로그인 후 Enter 누르면 자동 진행
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

MALL_HOME = "https://zae-da.com/"
DEFAULT_WRITE_URL = "https://zae-da.com/m/bbs/board_write.php?boardid=41"

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
    1) .env의 User Data + Profile 18 로 시도
    2) 'already in use' 발생 시, CHROME_FALLBACK_DIR로 폴백(중복 사용 없음)
    3) 드라이버가 뜨면 바로 재다몰 홈으로 이동해 로그인 유도 가능
    """
    import os
    from pathlib import Path
    from selenium.common.exceptions import WebDriverException

    def make_options(user_data_dir: str, profile_dir: str | None):
        opts = ChromeOptions()
        if user_data_dir:
            opts.add_argument(f'--user-data-dir={user_data_dir}')
        if profile_dir:
            opts.add_argument(f'--profile-directory={profile_dir}')
        # 충돌/보안툴 완화 옵션
        opts.add_argument('--start-maximized')
        opts.add_argument('--no-first-run')
        opts.add_argument('--no-default-browser-check')
        opts.add_argument('--disable-extensions')
        opts.add_argument('--disable-popup-blocking')
        opts.add_argument('--disable-dev-shm-usage')
        opts.add_argument('--disable-gpu')
        opts.add_argument('--remote-allow-origins=*')
        # 필요 시에만: opts.add_argument('--no-sandbox')

        # 디버깅 편의
        opts.add_experimental_option("detach", True)
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        opts.add_experimental_option("useAutomationExtension", False)
        return opts

    # ① 기본 시도: .env의 실제 사용자 프로필
    user_data_dir = os.path.expandvars(os.getenv(
        "CHROME_USER_DATA_DIR",
        r"C:\Users\%USERNAME%\AppData\Local\Google\Chrome\User Data"
    ))
    profile_dir = os.getenv("CHROME_PROFILE", "Default")

    try:
        opts = make_options(user_data_dir, profile_dir)
        drv = Chrome(service=Service(ChromeDriverManager().install()), options=opts)
        print(f"[chrome] primary profile OK → user-data-dir={user_data_dir}, profile={profile_dir}", flush=True)
        return drv
    except WebDriverException as e:
        msg = str(e)
        print(f"[chrome] primary profile failed → {msg}", flush=True)

        # 'already in use' 등의 경우 폴백 디렉터리 사용
        fallback_dir = os.path.expandvars(os.getenv("CHROME_FALLBACK_DIR", r"C:\ChromeProfiles\zaeda_selenium"))
        try:
            Path(fallback_dir).mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        try:
            opts_fb = make_options(fallback_dir, None)  # 폴백은 Default로
            drv = Chrome(service=Service(ChromeDriverManager().install()), options=opts_fb)
            print(f"[chrome] fallback profile launched: {fallback_dir}", flush=True)
            # 폴백 드라이버가 떴으면 바로 재다몰 홈으로 이동해 로그인 유도
            try:
                drv.get("https://zae-da.com/")
            except Exception:
                pass
            print("  ↳ 폴백 창에서 재다몰에 1회 로그인하면 이후 자동 유지됩니다.", flush=True)
            return drv
        except WebDriverException as e2:
            print(f"[chrome] fallback profile failed → {e2}", flush=True)
            raise


def wait_ready(drv):
    WebDriverWait(drv, MAX_WAIT).until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )

def is_logged_in(drv) -> bool:
    """헤더/메뉴에 '로그아웃'이 보이면 로그인 상태로 판단."""
    try:
        # 버튼/링크 텍스트 내 '로그아웃' 검색
        logout = drv.find_elements(By.XPATH, "//a[contains(.,'로그아웃')] | //button[contains(.,'로그아웃')]")
        if logout:
            return True
    except Exception:
        pass
    return False

def ensure_login(drv, write_url: str):
    """
    글쓰기 페이지 진입 전, 로그인 여부 확인.
    - 미로그인: 홈으로 보내고 콘솔에서 로그인 유도 → 사용자 Enter 입력 후 재시도
    """
    # 1) 우선 글쓰기 페이지로 진입 시도
    drv.get(write_url)
    wait_ready(drv)

    # 글쓰기 폼 요소가 보이면 바로 리턴
    try:
        WebDriverWait(drv, 5).until(
            EC.presence_of_element_located((
                By.CSS_SELECTOR,
                "input[name='wr_subject'], input[name='subject'], input[name='title']"
            ))
        )
        return  # 로그인 되어 있고 글쓰기 가능
    except Exception:
        pass

    # 2) 홈으로 보내서 로그인 유도
    log("로그인 필요로 보입니다 → 재다몰 홈을 열어 로그인해 주세요.")
    drv.get(MALL_HOME)
    wait_ready(drv)
    print("\n────────────────────────────────────────────────────────")
    print("  🔐 재다몰 창에서 로그인해 주세요.")
    print("  로그인 완료 후 여기 콘솔에서 Enter 키를 눌러 계속합니다.")
    print("────────────────────────────────────────────────────────\n")
    try:
        input()  # 사용자 입력 대기
    except EOFError:
        # 파이프 실행 등으로 stdin이 없을 때는 10초 대기 후 진행
        import time
        time.sleep(10)

    # 3) 다시 글쓰기 페이지로 이동해 확인
    drv.get(write_url)
    wait_ready(drv)

# ──────────────────────────────
# Main
# ──────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", required=False, default=DEFAULT_WRITE_URL,
                    help="재다몰 글쓰기 URL (기본: %(default)s)")
    args = ap.parse_args()

    wb, ws, row, title, body = load_next_row()
    if not row:
        log("대기 중인 업로드 건이 없습니다.")
        return

    drv = setup_driver()
    ensure_login(drv, args.url)

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
