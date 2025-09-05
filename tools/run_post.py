# -*- coding: utf-8 -*-
"""
원클릭 재다몰 업로드 실행기
- data.xlsx 없으면 샘플 생성
- 빈 본문 자동 생성
- auto_write.py 실행 (자동 로그인 + 글쓰기 + Excel 상태 업데이트)
"""

import os
import sys
import subprocess
from pathlib import Path
from dotenv import load_dotenv

# ── 설정 ─────────────────────────────
load_dotenv()
ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"
DOCS = ROOT / "docs"
XLSX = DOCS / "data.xlsx"

DEFAULT_URL = "https://zae-da.com/bbs/write.php?boardid=41"


def run(cmd: list[str], check=True):
    """하위 스크립트 실행"""
    print("▶", " ".join(str(c) for c in cmd), flush=True)
    return subprocess.run(cmd, check=check)


def main():
    print("🚀 원클릭 재다몰 업로드 시작")

    # 0) 글쓰기 URL
    write_url = os.getenv("ZAEDA_WRITE_URL", DEFAULT_URL)
    print(f"📍 대상 URL: {write_url}")

    # 1) docs/data.xlsx 없으면 샘플 생성
    if not XLSX.exists():
        DOCS.mkdir(exist_ok=True)
        print("📊 data.xlsx 없음 → 샘플 생성")
        run([sys.executable, str(TOOLS / "make_sample_data.py"), "--rows", "1"])

    # 2) create_contents.py 실행 → 빈 본문 채우기
    print("🔄 본문 내용 생성...")
    try:
        run([sys.executable, str(TOOLS / "create_contents.py"), "--only-empty"])
        print("✅ 본문 내용 생성 완료")
    except subprocess.CalledProcessError as e:
        print(f"❌ 본문 내용 생성 실패 (코드: {e.returncode})")
        return

    # 3) auto_write.py 실행
    print("🚀 자동 업로드 시작...")
    try:
        run([sys.executable, str(TOOLS / "auto_write.py"), "--url", write_url])
    except subprocess.CalledProcessError as e:
        print(f"❌ 업로드 실패 (코드: {e.returncode})")
    else:
        print("🎉 자동 업로드 성공!")
    finally:
        print("✅ 종료")


if __name__ == "__main__":
    main()
