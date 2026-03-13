"""Stage 3: 생존 이슈 → 내일 판정 가능한 Yes/No 질문 변환.

Stage 2에서 살아남은 이슈들을 GPT-4o-mini로 분석하여
다음 날(24시간 내) 명확하게 Yes 또는 No로 판정할 수 있는 질문으로 변환한다.
변환 불가능한(애매한) 이슈는 탈락시킨다.
"""

import json
import os
from datetime import datetime, timedelta
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

QUESTION_PROMPT = f"""[Role]
너는 금융 이슈를 내일({tomorrow}) 장 마감까지 Yes/No로 판정 가능한 베팅 질문으로 변환하는 전문가다.

[Task]
제공된 뉴스 이슈 리스트를 읽고, **모든** 이슈를 내일({tomorrow}) 판정 가능한 Yes/No 질문으로 변환하라.

[CRITICAL: 반드시 모든 이슈를 변환하라 — 최소 4개 이상]
입력된 이슈는 이미 Stage 1, 2를 통과한 고품질 이슈다. 반드시 전부 질문으로 변환해야 한다.
어떤 이슈든 프록시 전략을 사용하면 반드시 Yes/No로 변환 가능하다. 탈락시키지 마라.
직접적인 결과 확인이 어려운 이슈라도 아래 프록시 전략으로 변환하라:

- 환율/금리 이슈 → "내일 원·달러 환율 X원 돌파할까?" (종가 기준)
- 지정학 리스크 → "내일 코스피 전일 대비 하락 마감할까?" (시장 반응으로 프록시)
- 정책/규제 이슈 → "내일 관련 법안이 국회 본회의를 통과할까?" 또는 "내일 금리 동결/인하 결정이 나올까?" (구체적 의사결정 기준)
- 기업 이슈 → "내일 해당 종목 전일 대비 ±X% 이상 움직일까?" (주가 반응)
- 섹터 이슈 → "내일 관련 ETF/섹터 지수 상승 마감할까?"

[Rules]
1. 질문은 내일({tomorrow}) 장 마감(15:30 KST) 또는 24시간 이내에 판정 가능해야 한다.
2. 판정 기준(resolution)을 구체적 수치와 함께 명시하라.
3. 질문은 한국어로, 투자 커뮤니티 유저가 바로 이해할 수 있게 작성하라.
4. side_yes와 side_no는 짧고 임팩트 있게 작성하라.
5. 같은 주제(같은 종목, 같은 지표, 같은 이슈)의 이슈가 여러 개 있으면 반드시 하나의 질문으로 통합하라. 중복 질문은 절대 금지.

[BANNED: 절대 금지되는 질문 유형]
- "관련 보도/발표가 나올까?" 류의 질문은 절대 금지. 보도는 항상 나오므로 베팅 가치가 없다.
- "뉴스가 나올까?" 류의 질문도 절대 금지.
- 반드시 구체적 수치(주가 ±X%, 환율 X원, 지수 X포인트)나 구체적 의사결정(법안 통과, 금리 결정, 승인/거부)으로 판정해야 한다.
- 모든 질문의 resolution에는 반드시 숫자 기준이나 공식적 결정 사항이 포함되어야 한다.

[Output Format: JSON Only]
{{
  "questions": [
    {{
      "id": 0,
      "question": "내일 코스피 2,500선을 지킬 수 있을까?",
      "side_yes": "YES: 2,500 이상 마감",
      "side_no": "NO: 2,500 미만 마감",
      "resolution": "내일({tomorrow}) 코스피 종가 기준. 2,500 이상이면 YES, 미만이면 NO.",
      "deadline": "{tomorrow} 15:30 KST"
    }}
  ]
}}"""


def make_questions(survivors: list[dict]) -> list[dict]:
    """Stage 2 생존자들을 Yes/No 질문으로 변환한다.

    Returns:
        변환된 질문 리스트. 각 항목은 원본 survivor 데이터 + question 필드를 포함.
    """
    if not survivors:
        return []

    indexed = [{"id": i, "headline": s.get("headline", ""), "reason": s.get("reason", "")} for i, s in enumerate(survivors)]
    user_content = json.dumps(indexed, ensure_ascii=False)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": QUESTION_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.3,
        response_format={"type": "json_object"},
    )

    result = json.loads(response.choices[0].message.content)
    questions_raw = result.get("questions", [])

    merged = []
    for q in questions_raw:
        idx = q.get("id", -1)
        if 0 <= idx < len(survivors):
            entry = {
                **survivors[idx],
                "question": q.get("question", ""),
                "side_yes": q.get("side_yes", ""),
                "side_no": q.get("side_no", ""),
                "resolution": q.get("resolution", ""),
                "deadline": q.get("deadline", ""),
            }
            merged.append(entry)

    return merged
