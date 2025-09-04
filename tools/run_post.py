# tools/run_post.py
# -*- coding: utf-8 -*-
"""
원클릭 재다몰 업로드 실행기
- docs/data.xlsx 없으면 자동 생성 + 본문 채우기
- auto_write.py 호출 (전용 프로필 크롬으로 실행)

환경변수(선택):
  ZAEDA_WRITE_URL   : 글쓰기 URL (기본값 아래)
  ZAEDA_PROFILE_DIR : 전용 크롬 프로필 경로 (기본 C:\ChromeProfiles\zaeda)
"""

from __future__ import annotations
import os, subprocess, sys
from pathlib import Path

ROOT  = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
DOCS  = ROOT / "docs"
XLSX  = DOCS / "data.xlsx"

DEFAULT_URL = "https://zae-da.com/bbs/board_write.php?boardid=41"

def run(cmd: list[str], check=True):
    print("▶", " ".join(str(c) for c in cmd), flush=True)
    return subprocess.run(cmd, check=check)

def main():
    print("🚀 원클릭 재다몰 업로드 시작")

    # 0) 기본 값 준비
    write_url = os.getenv("ZAEDA_WRITE_URL", DEFAULT_URL)
    os.environ.setdefault("ZAEDA_PROFILE_DIR", r"C:\ChromeProfiles\zaeda")

    # 1) 데이터 파일 없으면 샘플 생성
    if not XLSX.exists():
        DOCS.mkdir(exist_ok=True)
        run([sys.executable, str(TOOLS/"make_sample_data.py"), "--rows", "1"])

    # 2) 본문 비어있는 행 채우기
    run([sys.executable, str(TOOLS/"create_contents.py"), "--only-empty"])

    # 3) 실제 업로드 실행 (auto_write.py 호출)
    run([
        sys.executable,
        str(TOOLS/"auto_write.py"),
        "--url", write_url,
        "--secret", "1",           # 기본: 비밀글 ON
        "--image-count", "2"       # 기본: 이미지 2장
    ])

    print("✅ 종료")

if __name__ == "__main__":
    main()
