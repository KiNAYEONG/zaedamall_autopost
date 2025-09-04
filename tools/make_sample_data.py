# -*- coding: utf-8 -*-
"""
샘플 data.xlsx 생성 스크립트
- 기존 파일이 있어도 덮어쓰지 않음(옵션으로 --force 가능)
- 기본으로 5개 샘플 행을 생성
엑셀 헤더:
제목 | 본문 | 상태 | 업데이트시각 | 이미지검색어 | 카테고리
"""

from __future__ import annotations
import argparse
from pathlib import Path
import datetime as dt
import openpyxl

ROOT = Path(__file__).resolve().parent
DOCS = (ROOT.parent / "docs")
XLSX = (DOCS / "data.xlsx")

HEADERS = ["제목", "본문", "상태", "업데이트시각", "이미지검색어", "카테고리"]

def log(msg: str):
    print(msg, flush=True)

def now_str():
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=5, help="샘플 행 개수 (기본 5)")
    ap.add_argument("--force", action="store_true", help="기존 파일이 있어도 덮어쓰기")
    args = ap.parse_args()

    DOCS.mkdir(parents=True, exist_ok=True)

    if XLSX.exists() and not args.force:
        log(f"이미 존재: {XLSX}  (덮어쓰려면 --force)")
        return

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "posts"
    ws.append(HEADERS)

    # 카테고리/검색어/제목/본문 샘플
    samples = [
        ("[만성질환 관리/당뇨 관리] 혈당 관리 생활 습관", "아침 식사 후 혈당을 안정시키는 방법을 소개합니다.", "당뇨 식단", "만성질환 관리/당뇨 관리"),
        ("[생활습관 관리/운동 습관] 매일 걷기의 효과", "매일 30분 걷기만으로도 얻을 수 있는 건강상의 이점.", "운동", "생활습관 관리/운동 습관"),
        ("[마음과 몸 관리/불면증] 밤에 쉽게 잠드는 방법", "수면 위생을 지키는 생활 습관 가이드.", "수면", "마음과 몸 관리/불면증"),
        ("[생활습관 관리/식습관] 아침 식사의 중요성", "아침 식사가 대사와 집중력에 미치는 영향.", "건강 식단", "생활습관 관리/식습관"),
        ("[만성질환 관리/고혈압 관리] 소금 줄이는 팁", "짠맛을 줄이면서도 맛있게 먹는 방법.", "저염식", "만성질환 관리/고혈압 관리"),
    ]

    for i in range(args.rows):
        title, body, img_query, category = samples[i % len(samples)]
        ws.append([title, body, "", now_str(), img_query, category])

    wb.save(XLSX)
    log(f"샘플 파일 생성 완료 → {XLSX} (행 {args.rows}개)")

if __name__ == "__main__":
    main()
