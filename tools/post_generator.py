#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
post_generator.py - Google GenAI SDK(google-genai) 기반 블로그 콘텐츠 생성

- SDK 통일: from google import genai (+ types)
- API 키: GEMINI_API_KEY > GOOGLE_API_KEY
- 모델: 환경변수 GEMINI_MODEL 우선, 없으면 안전 기본값
  (너가 list_models.py로 확인한 값 예: "models/gemini-3-flash-preview")
"""

import os
import random
from dataclasses import dataclass

from google import genai
from google.genai import types


@dataclass
class GeneratedPost:
    title: str
    body_text: str
    topic: str
    cat1: str
    cat2: str


# ======= 중요 =======
# 아래 SYSTEM_PROMPT 자리에 팀원이 준 원본 프롬프트를 그대로 붙여넣으세요.
# (여기에는 내가 내용을 복사해 넣어드릴 수 없습니다.)
SYSTEM_PROMPT = """
당신은 20년 경력의 '건강 행동 심리학자'이자 '블로그 마케팅 수석 에디터'입니다.
작성하는 모든 글의 핵심 이면에는 '재다(Zaeda)' 앱의 홍보와 유입이라는 마케팅 목적이 깔려 있어야 합니다.

[마케팅 핵심 전략: 페르소나와 위장]
1. 정보성 위장: 본문은 100% 독자에게 유익한 정보로만 구성하여 철저히 '광고가 아닌 유용한 팁'으로 인식하게 하십시오.
2. 앱 이름 노출 시점: 결론 전까지는 앱 이름을 절대 언급하지 마십시오. 오직 마지막 '🎁 에디터의 찐 추천' 섹션에서만 전문가가 제안하는 해결책으로서 재다를 제시하십시오.
3. 내용의 다양성: 뻔한 교과서적인 내용(예: 무조건적인 운동, 채소 먹기 등)을 반복하지 말고, 제시된 '세부 앵글'에 맞춰 매번 참신하고 깊이 있는 심리학적/생리학적 관점을 제시하십시오.

[출력 구조 지침 - 절대 준수]
1. 제목: 이모지를 포함하여 클릭을 유발하는 제목을 가장 첫 줄에 작성하십시오. (마크다운 기호 금지)
2. 간단한 인트로: 제목과 관련해 독자의 공감을 유발하는 간단한 글로 시작해주세요.
3. 소제목 개수: **본문의 소제목 섹션은 반드시 3개만 작성하십시오.** 부족하거나 넘치지 않게 핵심 내용 3가지로 압축합니다.
4. 소제목 포맷: 반드시 '이모지 + 번호 + 마침표 + 제목' 형태로 작성하십시오. (예: 🥦 1. 소제목 내용)
5. 줄바꿈 규칙: 가독성을 위해 이모티콘 앞에 반드시 '두 번의 엔터(빈 줄 하나)'를 넣어 간격을 넓게 유지하십시오. 나머지는 모두 줄을 붙여주세요.
6. 마크다운 기호 금지: #, *, -, _, > 등 모든 특수 기호를 절대 사용하지 마십시오. 오직 텍스트와 이모지로만 구성합니다.

[톤앤매너 및 법적 가이드]
- 말투: 자기소개 없이 바로 시작하며, 친절한 '~요' 체를 사용하십시오.
- 완곡한 표현: 단정적인 의학적 표현 대신 '도움을 줄 수 있어요', '기대해 볼 수 있답니다' 등 법적 리스크를 피하는 완곡한 화법을 쓰십시오.
- 당신이 누구라는 말을 절대 하지 마십시오.

[전환 섹션 및 출처 필수 팩트]
- 앱 추천 시: 전남대 임상 연구(혈액지표 2배 개선 입증), 2025 K-디지털 브랜드 대상 수상 내역, 글의 주제와 관련한 앱 기능 소개를 반드시 포함하십시오.
- 출처 섹션: 글의 가장 마지막에 [📚 참고 자료 및 출처]를 작성하고, 재다(Zaeda) 임상 연구 결과와 관련 학회 가이드라인을 주제에 맞춰 포함하십시오.
"""


def _get_api_key() -> str:
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Gemini API 키가 없습니다.\n"
            "PowerShell 예: $env:GEMINI_API_KEY='your_key'\n"
            "또는 .env에 GEMINI_API_KEY=your_key"
        )
    return api_key


def _get_model_name() -> str:
    """
    너가 list_models.py에서 확인한 모델명은 'models/...' 형태였음.
    예) models/gemini-3-flash-preview, models/gemini-flash-latest, models/gemini-2.5-flash
    """
    return os.environ.get("GEMINI_MODEL", "models/gemini-3-flash-preview")


def generate_blog_content(topic: str, cat1: str = "", cat2: str = "") -> str:
    """
    Google GenAI SDK로 콘텐츠 생성 (제목 포함 텍스트)
    """
    api_key = _get_api_key()
    model = _get_model_name()

    # Client 생성 (SDK 통일)
    client = genai.Client(api_key=api_key)

    topics = ["혈압 관리", "혈당 관리", "기억력 개선", "체중 관리", "전반적인 건강관리", "활력있는 삶"]
    if not topic or not topic.strip():
        topic = random.choice(topics)

    angles = [
        "수면 부족과 스트레스가 미치는 치명적인 영향 관점",
        "우리가 몰랐던 일상 속 잘못된 건강 상식과 오해 관점",
        "장내 미생물과 호르몬의 비밀 관점",
        "바쁜 3040 직장인을 위한 5분 실천 루틴 관점",
        "무심코 먹는 가공식품과 숨겨진 당의 위험성 관점",
        "마음챙김과 심리적 안정이 신체에 미치는 영향 관점",
    ]
    selected_angle = random.choice(angles)

    user_input = f"""
선정된 대주제: {topic}
세부 작성 앵글: {selected_angle}

위의 대주제를 다루되, 반드시 '세부 작성 앵글'의 관점에서 깊이 있게 풀어주세요. 뻔한 내용은 지양합니다.
이면의 마케팅 목적을 반영하여, 소제목 3개 구성과 예시 포맷(이모티콘 앞 더블 엔터)대로 작성해줘.
""".strip()

    # 생성 설정
    cfg = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        temperature=0.95,
        top_p=0.95,
    )

    resp = client.models.generate_content(
        model=model,
        contents=user_input,
        config=cfg,
    )

    if not getattr(resp, "text", None):
        # 일부 케이스에서 text가 비어있을 수 있어 방어
        raise RuntimeError("Gemini 응답에 text가 없습니다. (응답 구조/권한/모델 확인 필요)")

    return resp.text


def extract_title_from_content(content: str) -> tuple[str, str]:
    """
    생성된 콘텐츠에서 제목(첫 줄)과 본문 분리
    """
    lines = content.strip().split("\n")
    title = lines[0].strip().replace("#", "").strip()
    body = "\n".join(lines[1:]).strip()
    return title, body


def build_sample_post(topic: str, cat1: str, cat2: str) -> GeneratedPost:
    full_content = generate_blog_content(topic, cat1, cat2)
    title, body = extract_title_from_content(full_content)

    if len(title) > 100:
        title = title[:97] + "..."

    return GeneratedPost(
        title=title,
        body_text=body,
        topic=topic,
        cat1=cat1,
        cat2=cat2,
    )


if __name__ == "__main__":
    import sys

    try:
        post = build_sample_post("혈당 관리", "건강", "영양")
        print("=" * 60)
        print(f"제목: {post.title}")
        print("=" * 60)
        print(post.body_text[:500])
        print("...")
    except Exception as e:
        print(f"오류: {e}", file=sys.stderr)
        sys.exit(1)