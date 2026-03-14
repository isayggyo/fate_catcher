"""Stage A: 이벤트 드리븐 이슈 추출.

72시간(3일) 이내에 O/X 결과가 확정될 수 있는 이슈만 골라내어
subject / conflict / trigger / deadline / pivot 5개 필드로 구조화한다.

GPT-4o-mini API 사용.
"""

import json
import os
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL = "gpt-4o-mini"

from datetime import timedelta

TODAY = datetime.now().strftime("%Y-%m-%d")
TOMORROW = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
DEADLINE_END = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")


def _build_prompt() -> str:
    return f"""[System Role]
너는 'Fate Catcher' 서비스의 핵심 데이터 엔지니어이자 뉴스 분석가다. 너의 임무는 방대한 뉴스 텍스트에서 내일({TOMORROW}) 00:00부터 일주일({DEADLINE_END}) 이내에 O/X 결과가 확정될 수 있는 '이벤트 드리븐(Event-Driven)' 이슈만 골라내어 구조화된 데이터로 변환하는 것이다.
오늘은 {TODAY} (2026년 3월 14일 금요일)이다.
유효 기한 범위: {TOMORROW} 00:00 ~ {DEADLINE_END} 23:59
이 범위 밖의 deadline을 가진 이벤트는 절대 출력하지 마라.

[Step 1: Filtering & Selection (선별 규칙)]
다음 기준에 부합하지 않는 뉴스는 가차 없이 버려라.

시한성(Short-term): deadline이 {TOMORROW} 00:00 ~ {DEADLINE_END} 23:59 범위 밖이면 버린다. 오늘({TODAY}) 이전 또는 일주일 이후의 이슈는 탈락.

판정 가능성(Binary): 결과가 "예/아니오"로 명확히 갈리지 않는 모호한 분석 기사는 버린다.

탈주식(Non-Price): 단순히 "주가가 오를까?"를 묻는 뉴스는 버린다. 대신 공시, 판결, 승인, 합병 등 '사건'에 집중한다.

한 놈만 팬다(Single Entity Rule) — 최우선 적용:
뉴스들을 먼저 '핵심 기업명'으로 분류하라. 동일한 기업에 대한 뉴스가 여러 개라면, 그중 가장 구체적인 일정(날짜/시간)이 명시된 단 하나만 남기고 나머지는 가차 없이 삭제하라.
- 동일 기업·인물·기관이 얽힌 이슈는 내용이 다르더라도 무조건 1건만 남긴다.
- 예: '대원산업 주총 집중투표'와 '대원산업 주주서한'이 동시에 있으면 날짜가 더 구체적인 1건만 생존.
- Tier 2에서도 이미 Tier 1에 등장한 주체는 절대 중복 출력하지 마라.
- 최종 결과에 같은 기업명이 2번 이상 등장하면 출력 실패다.

[Step 2: Extraction (데이터 요약 규칙)]
선정된 이슈에 대해 아래 5개 항목을 추출하되, 각 항목은 반드시 25자 이내로 작성하라.

subject (주체): 이슈를 일으킨 핵심 기업, 기관 또는 인물

conflict (대립): 누구와 누구의 싸움인가? 또는 어떤 가치와 어떤 가치의 충돌인가?

trigger (사건): 승패를 결정지을 구체적인 행동 (예: 가처분 소송, 유상증자 납입, 실적 발표)

deadline (기한): 결과가 확정되는 정확한 날짜와 시각 (모르면 기사 맥락상 추정일)

pivot (기준): 무엇을 보고 O/X를 판단할 것인가? (예: 인용 vs 기각, 17만원 상회 여부)

[Step 4: 예외 처리 및 확장 (Tier 2 - 공시/액션 여부)]
만약 Step 1에서 선별된 이슈가 5개 미만일 경우, 아래 '절차적 공시' 이슈로 **반드시 5개가 될 때까지** 채워라. Tier 2 이벤트의 id는 "EVT_T2_001" 형식으로 작성하라. 단, 이미 Tier 1에 등장한 주체는 중복 불가(한 놈만 팬다 규칙).

Tier 2 후보 유형 (아래 중 해당하는 것을 모두 찾아라):

1. 조회공시 대기: 루머나 보도에 대해 거래소가 요구한 '조회공시' 답변이 일주일 내 올라올 것인가? (키워드: 조회공시, 미확정, 풍문, 확인요청)

2. 재공시 예정: 이전에 '미확정' 공시를 했던 기업이 예고한 '재공시 예정일'에 확정 공시를 낼 것인가?

3. 행동 포착: 특정 인물이나 기업이 일주일 내에 공식 입장문 발표, 가처분 신청 접수, 보도자료 배포, 주주서한 공개 등의 '행동'을 실제로 할 것인가?

4. 주총/이사회 의결: 일주일 내 예정된 정기·임시주총, 이사회에서 안건이 통과될 것인가?

5. 인허가/심사 결과: 금감원·공정위·거래소 등 규제기관의 심사·인가·제재 결정이 일주일 내 발표될 것인가?

6. 수치 확정: 잠정실적 → 확정실적, 수요예측 결과, 공모가 확정 등 숫자가 일주일 내 공식 발표되는 이슈.

[Step 3: Output Format (출력 형식)]
오직 아래의 JSON 형식으로만 답변하라. 서론, 결론, 설명은 모두 생략한다.

{{"events": [
  {{
    "id": "EVT_001",
    "subject": "주체 (25자 이내)",
    "conflict": "대립 (25자 이내)",
    "trigger": "사건 (25자 이내)",
    "deadline": "YYYY-MM-DD HH:MM",
    "pivot": "기준 (25자 이내)"
  }}
]}}

[Input/Output Example]

Input: "고려아연 최윤범 회장 측이 제기한 자사주 매입 금지 가처분 신청에 대한 법원의 판단이 이번 주 금요일인 20일 오전 10시에 나올 예정이다. 시장에서는 기각될 경우 MBK의 승기를 예상하고 있으며..."

Output:
{{"events": [
  {{
    "id": "EVT_001",
    "subject": "고려아연 (최윤범 vs MBK)",
    "conflict": "경영권 방어 vs 적대적 M&A",
    "trigger": "법원 자사주 매입 가처분 판결",
    "deadline": "2026-03-20 10:00",
    "pivot": "가처분 신청 인용 여부"
  }}
]}}"""


def run_stage_a(raw_news: str) -> list[dict]:
    """원본 뉴스 텍스트에서 이벤트 드리븐 이슈를 추출한다.

    Returns:
        [{id, subject, conflict, trigger, deadline, pivot}, ...]
    """
    if not raw_news.strip():
        return []

    prompt = _build_prompt()

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"[RAW_NEWS_INPUT]\n{raw_news}"},
        ],
        temperature=0.2,
        max_tokens=8000,
        response_format={"type": "json_object"},
    )

    raw_text = response.choices[0].message.content
    result = json.loads(raw_text)

    events = result.get("events", [])

    # ── 후처리: 프롬프트 규칙을 코드로 강제 ──
    tomorrow_dt = datetime.strptime(TOMORROW, "%Y-%m-%d")
    end_dt = datetime.strptime(DEADLINE_END, "%Y-%m-%d").replace(hour=23, minute=59)

    # 1) deadline 범위 필터
    valid = []
    for evt in events:
        dl = evt.get("deadline", "")
        try:
            dl_dt = datetime.strptime(dl[:10], "%Y-%m-%d")
            if dl_dt < tomorrow_dt or dl_dt > end_dt:
                continue
        except (ValueError, IndexError):
            pass  # 파싱 실패 시 일단 포함
        valid.append(evt)

    # 2) 한 놈만 팬다 — subject에서 핵심 기업명 추출 후 중복 제거
    import re
    seen_entities = set()
    deduped = []
    for evt in valid:
        subj = evt.get("subject", "")
        # 괄호 앞의 핵심 기업명 추출: "롯데홈쇼핑 (태광 vs 김재겸)" → "롯데홈쇼핑"
        entity = re.split(r"[\s(（]", subj)[0].strip()
        if entity and entity in seen_entities:
            continue
        if entity:
            seen_entities.add(entity)
        deduped.append(evt)

    return deduped


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        with open(sys.argv[1], "r", encoding="utf-8") as f:
            raw = f.read()
    else:
        print("뉴스 데이터를 붙여넣으세요 (Ctrl+Z로 종료):")
        raw = sys.stdin.read()

    events = run_stage_a(raw)
    print(json.dumps(events, ensure_ascii=False, indent=2))
    print(f"\n총 {len(events)}개 이벤트 추출 완료.")
