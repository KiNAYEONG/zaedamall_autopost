#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
auto_write.py (JSON/CLI 기반 단독 실행 버전)
- 로그인: login.php 직접 이동 + #login_id/#login_pw
- 글쓰기: /bbs/write.php?boardid=41 (PC버전)
- 본문: SmartEditor2(oEditors['memo']) + textarea#memo fallback
- 로그인 확인: 로그아웃 링크 존재 여부

필수:
  pip install selenium webdriver-manager python-dotenv
"""

from __future__ import annotations

import argparse
import random
import json
import os
import sys
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from dotenv import load_dotenv
from selenium.webdriver import Chrome, ChromeOptions
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from selenium.common.exceptions import (
    NoAlertPresentException,
    TimeoutException,
    UnexpectedAlertPresentException,
)
from webdriver_manager.chrome import ChromeDriverManager


# =========================
# 경로/모듈 로딩
# =========================
TOOLS_DIR = Path(__file__).resolve().parent
ROOT_DIR = TOOLS_DIR.parent

if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

# .env 로드
load_dotenv(ROOT_DIR / ".env")

try:
    from post_generator import build_sample_post  # type: ignore
except Exception as e:
    raise RuntimeError("post_generator.py import 실패") from e

try:
    from sources_pubmed import fetch_pubmed_sources  # type: ignore
except Exception as e:
    raise RuntimeError("sources_pubmed.py import 실패") from e


# =========================
# URL 상수
# =========================
LOGIN_URL         = "https://zae-da.com/bbs/login.php?url=%2F"
DEFAULT_LIST_URL  = "https://zae-da.com/bbs/list.php?boardid=41"
DEFAULT_WRITE_URL = "https://zae-da.com/bbs/write.php?boardid=41"

MAX_WAIT = 20


# =========================
# 로깅
# =========================
def log(msg: str) -> None:
    ts = time.strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


# =========================
# 입력 데이터 구조
# =========================
@dataclass
class PostRequest:
    topic: str
    cat1: str
    cat2: str
    images: List[str]


# =========================
# 유틸
# =========================
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


# =========================
# sources.json 유틸
# =========================
def resolve_sources_json_path() -> Path:
    candidates = [TOOLS_DIR / "sources.json", ROOT_DIR / "sources.json"]
    for p in candidates:
        if p.exists():
            return p
    for p in ROOT_DIR.rglob("sources.json"):
        return p
    raise FileNotFoundError(f"sources.json 없음. 후보: {candidates}")


def load_sources_json(path: Path) -> list:
    return json.loads(path.read_text(encoding="utf-8"))


def pick_static_sources(topic: str, sources_path: Path, max_items: int = 3) -> List[str]:
    data = load_sources_json(sources_path)
    topic_l = (topic or "").lower()
    hits: List[str] = []
    for it in data:
        title = str(it.get("title", "")).strip()
        url = str(it.get("url", "")).strip()
        tags = [str(t).lower() for t in (it.get("tags") or [])]
        if title or url:
            if any(t and (t in topic_l) for t in tags):
                hits.append(f"{title} · {url}".strip(" ·"))
    if hits:
        return hits[:max_items]
    fallback: List[str] = []
    for it in data[:max_items]:
        title = str(it.get("title", "")).strip()
        url = str(it.get("url", "")).strip()
        if title or url:
            fallback.append(f"{title} · {url}".strip(" ·"))
    return fallback


# =========================
# 요청 로드
# =========================
def load_request(args: argparse.Namespace) -> PostRequest:
    if args.config:
        p = Path(args.config)
        if not p.is_absolute():
            p = (ROOT_DIR / p).resolve()
        data = json.loads(p.read_text(encoding="utf-8"))
        topic = (data.get("topic") or "").strip()
        cat1 = (data.get("cat1") or args.cat1).strip()
        cat2 = (data.get("cat2") or args.cat2).strip()
        images = data.get("images") or []
        if not isinstance(images, list):
            images = []
        images = [str(u).strip() for u in images if str(u).strip()]
        return PostRequest(topic=topic, cat1=cat1, cat2=cat2, images=images[:2])

    images = []
    for u in [args.img1, args.img2]:
        u = (u or "").strip()
        if u:
            images.append(u)
    return PostRequest(
        topic=(args.topic or "").strip(),
        cat1=(args.cat1 or "다이어트").strip(),
        cat2=(args.cat2 or "생활습관").strip(),
        images=images[:2],
    )


# =========================
# 드라이버
# =========================
def build_driver(headless: bool = False) -> Chrome:
    opts = ChromeOptions()
    opts.add_argument("--incognito")
    opts.add_argument("--start-maximized")
    if headless:
        opts.add_argument("--headless=new")
    opts.add_argument("--no-first-run")
    opts.add_argument("--no-default-browser-check")
    opts.add_argument("--disable-extensions")
    opts.add_argument("--disable-popup-blocking")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--disable-gpu")
    opts.add_argument("--remote-allow-origins=*")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)

    drv = Chrome(service=Service(ChromeDriverManager().install()), options=opts)
    drv.set_page_load_timeout(60)
    return drv


# =========================
# 로그인
# =========================
def is_logged_in(drv) -> bool:
    try:
        els = drv.find_elements(
            By.XPATH,
            "//a[contains(.,'로그아웃') or contains(.,'Logout') or contains(@href,'logout')]",
        )
        return bool(els)
    except Exception:
        return False


def try_auto_login(drv) -> bool:
    uid = os.environ.get("ZAEDA_ID", "").strip()
    pw  = os.environ.get("ZAEDA_PW", "").strip()

    if not uid or not pw:
        log("⚠ ZAEDA_ID/ZAEDA_PW 미설정 → 자동 로그인 스킵")
        return False

    log(f"🔐 로그인 페이지 이동: {LOGIN_URL}")
    drv.get(LOGIN_URL)
    wait_ready(drv, 15)
    accept_all_alerts(drv)

    # #login_id / #login_pw
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

    time.sleep(1.5)
    accept_all_alerts(drv)
    wait_ready(drv, 10)

    if is_logged_in(drv):
        log("🔐 자동 로그인 성공")
        return True

    log("⚠ 로그인 후 로그아웃 버튼 미감지 (실패 가능성)")
    return False


def ensure_login(drv, list_url: str):
    # 목록 페이지에서 로그인 상태 확인
    drv.get(list_url)
    wait_ready(drv, 15)
    accept_all_alerts(drv)

    if is_logged_in(drv):
        log("🔓 이미 로그인 상태")
        return

    # 자동 로그인 시도
    if try_auto_login(drv):
        return

    # 수동 로그인 fallback
    log("👤 자동 로그인 실패 → 수동 로그인 안내")
    drv.get(LOGIN_URL)
    wait_ready(drv, 15)
    accept_all_alerts(drv)
    input("재다몰에 수동 로그인 후 엔터를 눌러 계속하세요... ")
    drv.get(list_url)
    wait_ready(drv, 15)
    accept_all_alerts(drv)
    if not is_logged_in(drv):
        raise RuntimeError("로그인이 확인되지 않았습니다.")


# =========================
# 글쓰기 페이지 진입
# =========================
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
    drv.get(write_url)
    wait_ready(drv, 15)
    accept_all_alerts(drv)

    if find_subject(drv) is not None:
        log("✅ 글쓰기 페이지 진입 성공")
        return

    # 목록에서 글쓰기 버튼 클릭 (보험)
    drv.get(list_url)
    wait_ready(drv, 15)
    accept_all_alerts(drv)

    btns = drv.find_elements(By.CSS_SELECTOR, "a.btn_lsmall, a[href*='write.php']")
    for b in btns:
        try:
            if b.is_enabled() and "글쓰기" in (b.text or ""):
                b.click()
                time.sleep(0.5)
                accept_all_alerts(drv)
                wait_ready(drv, 15)
                if find_subject(drv) is not None:
                    log("✅ 글쓰기 페이지(리스트→버튼) 진입 성공")
                    return
        except Exception:
            continue

    raise RuntimeError("글쓰기 페이지로 진입하지 못했습니다. (권한 또는 URL 확인 필요)")


# =========================
# 본문 입력 (SmartEditor2)
# =========================
def wait_editor_ready(drv):
    WebDriverWait(drv, 20).until(
        lambda d: d.find_elements(By.CSS_SELECTOR, "textarea#memo, textarea[name='memo']")
        or d.execute_script(
            "return (typeof window.oEditors !== 'undefined') && window.oEditors && oEditors.getById && oEditors.getById['memo'];"
        )
    )


def set_post_body(drv, body_html: str):
    log("본문 입력 시작… (memo)")
    wait_editor_ready(drv)

    # base64 인코딩 후 JS에서 TextDecoder로 디코딩 → 이모지 완전 보존
    b64 = encode_b64(body_html)

    # 1) oEditors (SmartEditor2)
    script_editors = f"""
    (function() {{
        const b64 = '{b64}';
        const bin = atob(b64);
        const bytes = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
        const html = new TextDecoder('utf-8').decode(bytes);
        try {{
            if (window.oEditors && oEditors.getById && oEditors.getById['memo']) {{
                oEditors.getById['memo'].exec('SET_CONTENTS', [html]);
                oEditors.getById['memo'].exec('UPDATE_CONTENTS_FIELD', []);
            }}
        }} catch(e) {{}}
        // textarea에도 동시 반영
        const t = document.querySelector('textarea#memo, textarea[name="memo"]');
        if (t) t.value = html;
    }})();
    """
    try:
        drv.execute_script(script_editors)
        log("본문 입력 완료 ✓ (base64 → oEditors + textarea)")
    except Exception as e:
        log(f"⚠ 본문 입력 예외: {repr(e)}")

    # 검증
    v = drv.execute_script(
        "const t=document.querySelector('textarea#memo,textarea[name=memo]'); return t ? (t.value || '') : null;"
    )
    if v is None or len(v.strip()) == 0:
        raise RuntimeError("본문 입력 검증 실패: textarea#memo 값이 비어있습니다.")


def sync_editor_before_submit(drv):
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


# =========================
# 주제 랜덤 선택 (중복 방지)
# =========================
TOPICS = [
    "혈압 관리",
    "혈당 관리",
    "기억력 개선",
    "체중 관리",
    "전반적인 건강관리",
    "활력있는 삶",
    "장 건강",
    "수면 개선",
    "면역력 강화",
    "스트레스 관리",
]

def _gh_api(method: str, url: str, token: str, json_body=None) -> dict:
    """GitHub REST API 호출 헬퍼"""
    import urllib.request, json as _json
    req = urllib.request.Request(
        url,
        method=method,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        },
        data=_json.dumps(json_body).encode() if json_body else None,
    )
    try:
        with urllib.request.urlopen(req) as r:
            return _json.loads(r.read())
    except Exception:
        return {}


def _get_used_topics(token: str, repo: str) -> list:
    """GitHub Variable USED_TOPICS 에서 사용된 주제 목록 읽기"""
    url = f"https://api.github.com/repos/{repo}/actions/variables/USED_TOPICS"
    data = _gh_api("GET", url, token)
    raw = data.get("value", "")
    return [t.strip() for t in raw.split(",") if t.strip()] if raw else []


def _save_used_topics(token: str, repo: str, used: list) -> None:
    """GitHub Variable USED_TOPICS 업데이트 (없으면 생성)"""
    url = f"https://api.github.com/repos/{repo}/actions/variables/USED_TOPICS"
    value = ",".join(used)
    # PATCH(업데이트) 시도, 실패하면 POST(신규 생성)
    result = _gh_api("PATCH", url, token, {"name": "USED_TOPICS", "value": value})
    if not result:
        _gh_api("POST",
                f"https://api.github.com/repos/{repo}/actions/variables",
                token,
                {"name": "USED_TOPICS", "value": value})


def pick_random_topic() -> str:
    """
    TOPICS 전체를 순환하며 중복 없이 랜덤 선택.
    - 로컬: .last_topic 파일로 직전 주제 제외
    - GitHub Actions: GITHUB_TOKEN + GITHUB_REPOSITORY 환경변수로
      Variable USED_TOPICS에 사용 이력 저장 → 전체 소진 시 초기화
    """
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    repo  = os.environ.get("GITHUB_REPOSITORY", "").strip()

    # ── GitHub Actions 환경 ──────────────────────────────
    if token and repo:
        used = _get_used_topics(token, repo)
        candidates = [t for t in TOPICS if t not in used]

        # 전체 소진 시 초기화
        if not candidates:
            log("🔄 모든 주제 소진 → 순환 초기화")
            used = []
            candidates = list(TOPICS)

        chosen = random.choice(candidates)
        used.append(chosen)
        _save_used_topics(token, repo, used)
        log(f"🎲 선택된 주제: {chosen} | 사용됨({len(used)}/{len(TOPICS)}): {used}")
        return chosen

    # ── 로컬 환경 fallback ───────────────────────────────
    last_file = ROOT_DIR / ".last_topic"
    last = ""
    if last_file.exists():
        try:
            last = last_file.read_text(encoding="utf-8").strip()
        except Exception:
            pass

    candidates = [t for t in TOPICS if t != last]
    if not candidates:
        candidates = list(TOPICS)

    chosen = random.choice(candidates)
    try:
        last_file.write_text(chosen, encoding="utf-8")
    except Exception:
        pass

    log(f"🎲 선택된 주제: {chosen} (직전: {last or '없음'})")
    return chosen


# =========================
# 이모지 → HTML 엔티티 변환 (ChromeDriver BMP 우회)
# =========================
def encode_b64(text: str) -> str:
    """문자열을 base64로 인코딩 (ChromeDriver non-BMP 우회용)"""
    import base64
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def js_set_html(drv, html: str, selector_js: str) -> None:
    """
    base64 → JS atob+TextDecoder로 디코딩하여 삽입.
    ChromeDriver가 non-BMP(이모지)를 arguments로 전달할 때 깨지는 문제를
    base64로 완전히 우회.
    """
    b64 = encode_b64(html)
    script = f"""
    (function() {{
        const b64 = '{b64}';
        const bin = atob(b64);
        const bytes = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
        const html = new TextDecoder('utf-8').decode(bytes);
        {selector_js}
    }})();
    """
    drv.execute_script(script)


# =========================
# 본문 생성
# =========================
def build_post_html(req: PostRequest) -> Tuple[str, str]:
    topic = req.topic.strip() or pick_random_topic()
    cat1 = req.cat1.strip() or "다이어트"
    cat2 = req.cat2.strip() or "생활습관"

    p = build_sample_post(topic, cat1, cat2)

    title = p.title  # 이모지 변환은 JS 입력 시점에 base64로 처리

    sources_path = resolve_sources_json_path()
    static_src = pick_static_sources(topic, sources_path, max_items=3)
    pubmed_src = fetch_pubmed_sources(topic, max_items=4)

    img_html = ""
    for u in req.images[:2]:
        img_html += f"<p><img src='{u}' style='max-width:100%; height:auto;'/></p>"

    sources_html = "".join([f"<li>{s}</li>" for s in (static_src + pubmed_src)])

    # 본문: 줄바꿈 처리 (escape는 body_html 완성 후 한 번만)

    body_html = f"""<div style="font-size:15px; line-height:1.6; color:#111;">
{img_html}
{p.body_text.replace(chr(10), "<br/>")}
<hr style="border:none;border-top:1px solid #ddd;margin:14px 0;"/>
<p><strong>출처</strong></p>
<ul>{sources_html}</ul>
</div>""".strip()

    log(f"📝 생성된 제목: {p.title}")
    log(f"📝 본문 미리보기(200자): {p.body_text[:200]}")
    return title, body_html


# =========================
# main
# =========================
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=DEFAULT_WRITE_URL, help="글쓰기 URL")
    ap.add_argument("--list-url", default=DEFAULT_LIST_URL, help="글 목록 URL")
    ap.add_argument("--close", action="store_true", help="작업 후 브라우저 닫기")
    ap.add_argument("--headless", action="store_true", help="헤드리스 모드")
    ap.add_argument("--config", default="", help="포스팅 입력 JSON 경로")
    ap.add_argument("--topic", default="", help="포스팅 주제")
    ap.add_argument("--cat1", default="다이어트", help="대분류")
    ap.add_argument("--cat2", default="생활습관", help="소분류")
    ap.add_argument("--img1", default="", help="이미지 URL 1")
    ap.add_argument("--img2", default="", help="이미지 URL 2")
    args = ap.parse_args()

    req = load_request(args)
    title, body_html = build_post_html(req)

    drv = build_driver(headless=args.headless)
    try:
        # 1) 로그인 (login.php 직접 이동)
        ensure_login(drv, args.list_url)

        # 2) 글쓰기 페이지 진입 (/bbs/write.php)
        ensure_write_page(drv, args.list_url, args.url)

        # 3) 제목 입력 (base64 → JS TextDecoder - 이모지 완전 보존)
        # f-string과 arguments[] 혼용 금지 → b64를 JS 변수로 먼저 주입
        ti = find_subject(drv)
        if not ti:
            raise RuntimeError("제목 입력 필드를 찾을 수 없습니다.")
        b64_title = encode_b64(title)
        js_title = (
            "var b64='" + b64_title + "';"
            "var bin=atob(b64);"
            "var bytes=new Uint8Array(bin.length);"
            "for(var i=0;i<bin.length;i++) bytes[i]=bin.charCodeAt(i);"
            "var text=new TextDecoder('utf-8').decode(bytes);"
            "arguments[0].value=text;"
            "arguments[0].dispatchEvent(new Event('input',{bubbles:true}));"
        )
        drv.execute_script(js_title, ti)
        log("제목 입력 완료 ✓")

        # 4) 본문 입력
        set_post_body(drv, body_html)

        # 5) 등록 버튼
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

        sync_editor_before_submit(drv)
        drv.execute_script("arguments[0].click();", submit_btn)
        time.sleep(0.7)
        accept_all_alerts(drv)
        wait_ready(drv, 15)
        log("✅ 등록 완료")

        log("브라우저는 열어둡니다. 작업 내용을 확인하세요.")
        if args.close:
            drv.quit()
        return 0

    except UnexpectedAlertPresentException:
        try:
            a = drv.switch_to.alert
            log(f"❌ 알럿으로 중단: {a.text}")
            a.accept()
        except Exception:
            pass
        if args.close:
            drv.quit()
        return 1

    except Exception as e:
        log(f"❌ 오류: {repr(e)}")
        log(traceback.format_exc())
        log("브라우저는 열어둡니다.")
        if args.close:
            drv.quit()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())