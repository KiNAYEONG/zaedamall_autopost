# -*- coding: utf-8 -*-
"""
지침 반영 샘플 data.xlsx 생성 스크립트
- 카테고리 트리(대분류/소분류) 기반으로 샘플 행 생성
- 제목 형식: [카테고리1/카테고리2] 글 제목 (22–30자 목표)
- 본문 구조: 후크 → 왜 중요한가 → 핵심 행동 3가지 → 주의사항 → 요약 → 근거자료 → 디스클레이머
- 기존 파일이 있어도 덮어쓰지 않음(옵션 --force 시 덮어쓰기)
- --only "소분류1, 소분류2" 로 부분 생성 가능
"""

from __future__ import annotations
import argparse
from pathlib import Path
import datetime as dt
import random
import textwrap

import openpyxl

ROOT = Path(__file__).resolve().parent
DOCS = (ROOT / "docs")
XLSX = (DOCS / "data.xlsx")

HEADERS = ["제목", "본문", "상태", "업데이트시각"]

CATS = {
    "만성질환 관리": ["당뇨 관리", "고혈압 관리", "비만 관리", "치매 관리"],
    "마음과 몸 관리": ["불면증", "만성피로", "소화불량", "두통", "우울"],
    "생활습관 관리": ["식습관", "운동 습관", "배변 습관", "음주 습관", "금연"],
}

TITLE_STYLES = [
    "question",  # 질문형
    "numeric",   # 숫자형
    "result",    # 결과형
    "target",    # 대상형
    "twist",     # 반전형
    "blank"      # 빈칸형
]

def log(msg: str):
    print(msg, flush=True)

def now_str():
    return dt.datetime.now().strftime("%Y-%m-%d %H:%M")

def _fit_len(s: str, min_len=22, max_len=30):
    """제목 길이 보정: 너무 길면 자르고, 짧으면 자연스러운 접미사를 더함."""
    if len(s) > max_len:
        return s[:max_len].rstrip()
    if len(s) < min_len:
        pad = [" 가이드", " 한눈정리", " 핵심팁", " 빠른정리", " 시작법"]
        for p in pad:
            s2 = s + p
            if len(s2) >= min_len:
                return s2[:max_len]
    return s

def gen_title(group: str, sub: str, idx: int) -> str:
    """제목 생성: [그룹/소분류] + 스타일별 문구, 22–30자 맞춤."""
    style = TITLE_STYLES[idx % len(TITLE_STYLES)]
    prefix = f"[{group}/{sub}] "
    key = sub.replace(" 관리", "")  # 키워드 전면 배치 (앞 10자 내)
    if style == "question":
        core = f"{key} 왜 어려울까요"
    elif style == "numeric":
        core = f"{key} 실천 팁 3가지"
    elif style == "result":
        core = f"{key} 한 달 변화 기록"
    elif style == "target":
        core = f"바쁜 직장인 {key} 루틴"
    elif style == "twist":
        core = f"{key} 많이 하면 오히려 역효과?"
    else:  # blank
        core = f"{key}만 바꿔도 달라져요"
    title = prefix + core
    return _fit_len(title)

def wrap_para(txt: str) -> str:
    return textwrap.fill(txt, width=80, replace_whitespace=False)

def gen_body(group: str, sub: str) -> str:
    """지침 구조로 본문 생성(약 2000자 목표, 자연어 랜덤성 소폭 부여)."""
    today = now_str()
    topic = sub
    emoji = ["🌿", "💡", "🏃", "🍚", "🧠", "🧘", "🛌", "📌", "✅", "⚠️"]
    e = lambda: random.choice(emoji)

    # 1) 후크 (타이틀 숨김)
    hook = (
        f"요즘 {topic}이(가) 잘 안 되신다고 느끼나요? 아침엔 시간에 쫓기고, "
        f"퇴근하면 지쳐서 계획이 밀리곤 합니다. 밥상 차리면 국과 반찬 앞에서 "
        f"'뭘 줄이고 무엇을 더해야 하지?'라는 생각이 들죠. 이 글에서는 바쁜 일상 "
        f"속에서도 {topic}을(를) 무리 없이 관리하는 현실적인 방법을 함께 정리해 봅니다."
    )

    # 2) 왜 중요한가 (타이틀 숨김)
    insight = (
        f"{topic}은(는) 호르몬과 자율신경계의 균형과 밀접합니다. 스트레스와 수면의 질은 "
        f"코르티솔, 인슐린(Insulin)·세로토닌(Serotonin) 같은 신경전달물질에 영향을 주어 "
        f"식욕, 혈당, 혈압, 피로감에 연쇄 반응을 일으킵니다. 출근길 카페인, 늦은 밤 카톡, "
        f"단 음식이 반복되면 뇌의 보상 회로가 강화되어 습관을 바꾸기 더 어려워집니다. "
        f"국내외 연구에서도 생활습관 개입이 만성질환 위험을 낮추고 삶의 질을 개선한다는 "
        f"결과가 꾸준히 보고됩니다. 예를 들어 세계보건기구(WHO)와 질병관리청 자료는 "
        f"규칙적인 신체활동과 균형 잡힌 식사가 대사 건강과 정신 건강 모두에 긍정적이라고 "
        f"권장합니다(과장 없이, 개인차 존재)."
    )

    # 3) 핵심 행동 3가지
    action_title = f"{topic} 관리를 위한 핵심 행동 3가지"
    a1 = (
        "1) 식사 타이밍 고정하기 " + e() + " "
        f"식사 시간을 일정하게 유지하면 인슐린 분비 패턴이 안정되어 폭식과 야식을 줄일 수 있습니다. "
        f"출근·퇴근 루틴에 맞춰 아침·점심·저녁을 고정해 보세요. "
        f"실행은 캘린더 알람으로 식사 시작 알림을 설정하고, 밥·국·반찬 기본 구성을 지킵니다. "
        f"모임이나 회식이 있으면 '밥 반 공기+단백질 우선' 같은 대안을 선택해 흐트러짐을 최소화합니다. "
        f"초보자는 한 끼부터 시간을 고정하고, 간식은 식사 후 2시간 뒤로 미루는 방식으로 시작해 보세요."
    )
    a2 = (
        "2) 15분 저강도 움직임 " + e() + " "
        f"짧은 걷기나 계단 오르기만으로도 혈당과 혈압 변동폭을 줄이고 에너지를 끌어올릴 수 있습니다. "
        f"점심 이후 15분, 저녁 식사 후 15분을 걷기 시간으로 예약하세요. "
        f"실행은 스마트워치 또는 휴대폰에 15분 타이머를 두 번 설정하고, 사무실 복도·지하상가·집 근처 골목을 루프 코스로 만듭니다. "
        f"무릎이 불편하면 실내 제자리 걷기나 간단한 스트레칭으로 대체할 수 있습니다. "
        f"비 오는 날은 계단 오르내리기나 실내 자전거로 대체하세요."
    )
    a3 = (
        "3) 저녁 루틴에 수면 위생 추가 " + e() + " "
        f"수면 직전의 밝은 화면과 야식은 멜라토닌 분비를 방해해 다음 날 컨디션을 떨어뜨립니다. "
        f"취침 2시간 전 카톡·영상 알림을 끄고, 온점(湯) 샤워·스트레칭·가벼운 독서를 권장드립니다. "
        f"실행은 와이파이 자동 OFF, '방해 금지' 예약, 블루라이트 필터 적용 같은 기술적 장치를 함께 쓰는 것입니다. "
        f"초보자는 주 3일만, 30분 루틴부터 시작하면 부담이 적습니다."
    )

    # 4) 주의사항
    caution = (
        f"기저 질환이 있거나 약물을 복용 중인 분은 개인 상태에 따라 식단·운동 강도가 달라질 수 있습니다. "
        f"어지럼증·가슴 두근거림·심한 위장 불편감이 지속되면 즉시 중단하고 전문가 상담을 권장드립니다."
    )

    # 5) 요약
    summary = (
        f"{topic} 관리는 식사 타이밍 고정, 15분 움직임, 수면 위생 강화라는 세 축으로 단순화할 수 있습니다. "
        f"이 세 가지는 호르몬 균형과 자율신경계를 안정시키는 데 도움을 주며, 국내외 공신력 있는 자료의 권고와도 일치합니다. "
        f"무리하지 말고 한 가지부터 가볍게 실천해 보세요. 꾸준함이 최고의 지름길입니다 {e()}{e()}."
    )

    # 6) 근거자료
    refs = [
        "World Health Organization. Physical activity & healthy diet 권고.",
        "질병관리청(중앙). 만성질환 예방과 생활습관 가이드.",
        "American Heart Association. Blood pressure & lifestyle guidance.",
        "American Diabetes Association. Standards of Medical Care (핵심 요지).",
    ]

    disclaimer = (
        "이 글은 일반적인 건강 정보를 제공하기 위한 것이며, 의료적 진단이나 치료를 대신하지 않습니다. "
        "개인별 상태에 따라 전문가 상담이 필요할 수 있습니다."
    )

    parts = [
        wrap_para(hook),
        "",
        wrap_para(insight),
        "",
        action_title,
        wrap_para(a1),
        wrap_para(a2),
        wrap_para(a3),
        "",
        "주의사항",
        wrap_para(caution),
        "",
        "요약",
        wrap_para(summary),
        "",
        "근거자료",
        *[f"- {r}" for r in refs],
        "",
        disclaimer,
        f"(작성시각: {today})",
    ]
    return "\n".join(parts)

def build_rows(only: list[str] | None = None):
    """카테고리 트리에서 샘플 행들을 생성."""
    rows = []
    idx = 0
    only_set = {s.strip() for s in only} if only else None

    for group, subs in CATS.items():
        for sub in subs:
            if only_set and sub not in only_set:
                continue
            title = gen_title(group, sub, idx)
            body = gen_body(group, sub)
            rows.append([title, body, "", now_str()])
            idx += 1
    return rows

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="기존 파일이 있어도 덮어쓰기")
    ap.add_argument("--only", type=str, default="", help='특정 소분류만 생성(쉼표 구분). 예: "당뇨 관리, 불면증"')
    args = ap.parse_args()

    DOCS.mkdir(parents=True, exist_ok=True)

    if XLSX.exists() and not args.force:
        log(f"이미 존재: {XLSX}  (덮어쓰려면 --force)")
        return

    only_list = [s for s in args.only.split(",") if s.strip()] if args.only else None
    rows = build_rows(only_list)

    if not rows:
        log("생성할 항목이 없습니다. --only 조건을 확인하세요.")
        return

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "posts"
    ws.append(HEADERS)
    for r in rows:
        ws.append(r)

    wb.save(XLSX)
    log(f"샘플 파일 생성 완료 → {XLSX} (행 {len(rows)}개)")

if __name__ == "__main__":
    main()
