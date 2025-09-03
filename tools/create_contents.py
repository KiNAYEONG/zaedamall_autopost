# tools/create_contents.py
# -*- coding: utf-8 -*-
"""
지침 기반 콘텐츠 생성기
- .env 를 읽어 모델 키/옵션을 로드
- docs/data.xlsx 에 비어있는 제목/본문을 지침에 맞춰 채워 넣음
- 제목 규칙: `[카테고리1/카테고리2] 제목` (제목 길이 22~30자, 금지어 필터)
- 본문 구조/톤&매너/디스클레이머 자동 반영
"""

from __future__ import annotations
import os, re, datetime, argparse
from pathlib import Path
from typing import Optional, Tuple
from dotenv import load_dotenv
import openpyxl

# ─────────────────────────────────────────────────────────────────────────────
# 경로/상수
# ─────────────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
DOCS.mkdir(exist_ok=True)
XLSX = DOCS / "data.xlsx"

TITLE_MIN = 22
TITLE_MAX = 30

CATEGORIES = {
    "만성질환 관리": ["당뇨 관리", "고혈압 관리", "비만 관리", "치매 관리"],
    "마음과 몸 관리": ["불면증", "만성피로", "소화불량", "두통", "우울"],
    "생활습관 관리": ["식습관", "운동 습관", "배변 습관", "음주 습관", "금연"],
}

FORBIDDEN_WORDS = ["100% 예방", "충격", "완치"]

# ─────────────────────────────────────────────────────────────────────────────
# 모델 클라이언트 (gemini_client 우선, 없으면 더미)
# ─────────────────────────────────────────────────────────────────────────────
def _load_model():
    try:
        from tools.gemini_client import generate_text  # type: ignore
        return ("gemini", generate_text)
    except Exception:
        try:
            # 동일 경로에서 import될 수도 있음
            from gemini_client import generate_text  # type: ignore
            return ("gemini", generate_text)
        except Exception:
            pass

    def _fallback(prompt: str, **kwargs) -> str:
        # 아주 간단한 더미. 모델이 없을 때 최소 동작 보장용.
        return (
            "후크: 요즘 일상이 바쁜데도 증상 때문에 고생하고 계신가요? "
            "출퇴근, 카톡 알림 사이에서도 몸은 신호를 보냅니다. 오늘은 핵심 원인과 "
            "일상에서 시작할 수 있는 변화를 쉽게 풀어 드릴게요.\n\n"
            "왜 중요한가: 우리 몸은 호르몬과 자율신경의 균형으로 하루 컨디션을 유지합니다. "
            "작은 습관의 누적이 집중력, 수면, 대인관계에 영향을 줍니다. 최근 연구에서도 "
            "생활습관 중재가 유의미한 변화를 만든다고 보고합니다.\n\n"
            "1) 물 마시기 루틴 만들기 💧 …\n"
            "2) 가벼운 걷기 습관 들이기 🚶 …\n"
            "3) 취침 1시간 전 스크린 줄이기 🌙 …\n\n"
            "주의사항: 기존 질환이나 약 복용 중이면 변경 전 전문가 상담을 권장드립니다.\n\n"
            "요약: 오늘부터 쉬운 3가지를 실천하면 일정 기간 후 체감 변화가 옵니다. "
            "꾸준함이 핵심이에요. 😊\n\n"
            "근거자료:\n- WHO Lifestyle guidance\n- 질병관리청 자료\n\n"
            "이 글은 일반적인 건강 정보를 제공하기 위한 것이며, 의료적 진단이나 치료를 "
            "대신하지 않습니다. 개인별 상태에 따라 전문가 상담이 필요할 수 있습니다."
        )
    return ("fallback", _fallback)

MODEL_NAME, MODEL_FN = _load_model()

# ─────────────────────────────────────────────────────────────────────────────
# 지침 프롬프트
# ─────────────────────────────────────────────────────────────────────────────
GUIDELINE_PROMPT = """
당신은 블로그 포스트 작성 프로그램입니다. 한국어로 작성합니다.

[톤 & 매너]
- 대화체·공감형: 질문 → 공감 → 문제 정의
- 따뜻하고 격려: 공포·경고성 표현 금지. “~해 보세요 / 좋습니다 / 권장드립니다”
- 쉽게 풀기: 전문용어는 한글 우선, 필요한 경우 영어 병기
- 과학적이되 가볍게: 연구·기관 자료 1–2문장 인용, 과장·단정 금지
- 한국 맥락 반영: 밥·국·반찬·출퇴근·카톡 등 사례

[제목 규칙]
- 길이: 22–30자, 핵심 키워드 앞 10자 이내
- 1문장, 질문형/반전형/결과형/숫자형/대상형/빈칸형 중 택1
- 금지 표현: 100% 예방, 충격, 완치
- 최종 제목은 입력된 카테고리1/카테고리2를 접두로 붙여 다음 형식으로 출력:
  [카테고리1/카테고리2] 실제 제목

[본문 구조·분량 ≈ 2000자]
1) 후크(250–300자): 타이틀 표시는 쓰지 말고 문단만.
2) 왜 중요한가(400–450자): 타이틀 숨김. 몸의 메커니즘/일상 영향/짧은 근거 인용.
3) 핵심 행동 3가지(각 350–400자): 소제목 ‘번호 + 동사형 제목 + 이모지’, 문단은 문장형(마크다운 X).
   - 이유 2–3문장 → 실행법 2문장 → 초보자 팁 1–2문장
4) 주의사항(150–200자): 특정 질환·약물 복용자 주의 + 흔한 실수 팁
5) 요약(200–250자): 핵심 행동 요약 + 효과/근거 보강, 이모지 허용
6) 근거자료(3–6개): WHO/질병관리청/학회/저널 등 목록

[디스클레이머] 본문 끝 자동 출력(타이틀 숨김)
“이 글은 일반적인 건강 정보를 제공하기 위한 것이며, 의료적 진단이나 치료를 대신하지 않습니다. 개인별 상태에 따라 전문가 상담이 필요할 수 있습니다.”

요청 주제: {topic}
카테고리1: {cat1}
카테고리2: {cat2}

출력 형식:
<제목>
<본문 전체>
"""

# ─────────────────────────────────────────────────────────────────────────────
# 유틸
# ─────────────────────────────────────────────────────────────────────────────
def ensure_workbook() -> openpyxl.Workbook:
    if XLSX.exists():
        return openpyxl.load_workbook(XLSX)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "posts"
    ws["A1"] = "제목"
    ws["B1"] = "본문"
    ws["C1"] = "상태"
    ws["D1"] = "생성일"
    wb.save(XLSX)
    return wb

def first_empty_row(ws) -> int:
    r = ws.max_row + 1
    # 혹시 마지막 줄이 비어있지 않은데 더미 줄이 있을 때 대비
    while any((ws[f"{col}{r}"].value for col in "ABCD")):
        r += 1
    return r

def sanitize_title(title: str) -> str:
    t = title.strip()
    for bad in FORBIDDEN_WORDS:
        t = t.replace(bad, "")
    # 한 줄로
    t = re.sub(r"\s+", " ", t)
    return t

def clip_title_len(title: str) -> str:
    # 22~30자 범위에 최대한 맞춤(넘치면 자르고, 너무 짧으면 안전하게 보강)
    t = title
    if len(t) > TITLE_MAX:
        t = t[:TITLE_MAX]
    if len(t) < TITLE_MIN:
        t = t + " " + "가볍게 시작해 보세요"
        if len(t) > TITLE_MAX:
            t = t[:TITLE_MAX]
    return t

def extract_title_and_body(raw: str) -> Tuple[str, str]:
    raw = raw.strip()
    # 첫 줄을 제목으로 보고, 나머지를 본문으로
    if "\n" in raw:
        first, rest = raw.split("\n", 1)
    else:
        first, rest = raw, ""
    return first.strip(), rest.strip()

def wrap_title_with_categories(title: str, cat1: str, cat2: str) -> str:
    # 이미 접두가 붙어 있지 않다면 붙인다
    prefix = f"[{cat1}/{cat2}] "
    if not title.startswith(prefix):
        title = prefix + title
    return clip_title_len(sanitize_title(title))

# ─────────────────────────────────────────────────────────────────────────────
# 생성 로직
# ─────────────────────────────────────────────────────────────────────────────
def generate_post(cat1: str, cat2: str, topic: Optional[str] = None) -> Tuple[str, str]:
    topic = topic or f"{cat2} 주제의 생활 관리 가이드"
    prompt = GUIDELINE_PROMPT.format(topic=topic, cat1=cat1, cat2=cat2)

    text = MODEL_FN(prompt, max_output_tokens=2200) if MODEL_NAME == "gemini" else MODEL_FN(prompt)
    title, body = extract_title_and_body(text)

    # 제목 정리 & 접두 붙이기
    title = wrap_title_with_categories(title, cat1, cat2)

    # 디스클레이머 보장(중복 방지)
    disclaimer = (
        "이 글은 일반적인 건강 정보를 제공하기 위한 것이며, 의료적 진단이나 치료를 대신하지 않습니다. "
        "개인별 상태에 따라 전문가 상담이 필요할 수 있습니다."
    )
    if disclaimer not in body:
        body = body.rstrip() + "\n\n" + disclaimer

    return title, body

# ─────────────────────────────────────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────────────────────────────────────
def main():
    load_dotenv()

    ap = argparse.ArgumentParser()
    ap.add_argument("--only-empty", action="store_true", help="빈 행만 채우기")
    ap.add_argument("--count", type=int, default=0, help="새로 생성할 개수(0=카테고리 전체 1회전)")
    ap.add_argument("--topic", type=str, default="", help="사용자 지정 주제(옵션)")
    args = ap.parse_args()

    wb = ensure_workbook()
    ws = wb.active

    to_generate = []

    if args.count > 0:
        # 카테고리 순회로 n개 생성
        for cat1, subcats in CATEGORIES.items():
            for cat2 in subcats:
                to_generate.append((cat1, cat2))
                if len(to_generate) >= args.count:
                    break
            if len(to_generate) >= args.count:
                break
    else:
        # 전체 카테고리 1회전
        for cat1, subcats in CATEGORIES.items():
            for cat2 in subcats:
                to_generate.append((cat1, cat2))

    generated = 0
    for cat1, cat2 in to_generate:
        if args.only_empty:
            # 빈 줄 찾아 쓰기
            row = None
            for i in range(2, ws.max_row + 1):
                title = (ws[f"A{i}"].value or "").strip()
                body = (ws[f"B{i}"].value or "").strip()
                status = (ws[f"C{i}"].value or "").strip().upper()
                if not title and not body and status != "SKIP":
                    row = i
                    break
            if row is None:
                row = ws.max_row + 1
        else:
            row = ws.max_row + 1

        title, body = generate_post(cat1, cat2, args.topic or None)

        ws[f"A{row}"] = title
        ws[f"B{row}"] = body
        ws[f"C{row}"] = ""  # 상태 비움(업로더가 DONE 처리)
        ws[f"D{row}"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

        generated += 1

    wb.save(XLSX)
    print(f"✅ 생성 완료: {generated}건 (모델: {MODEL_NAME})  → {XLSX}")

if __name__ == "__main__":
    main()
