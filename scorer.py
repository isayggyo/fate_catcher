"""Stage 2: 투기장 적합도 스코어링 필터.

Stage 1에서 엄선된 15개 이슈를 GPT-4o-mini로 스코어링하여
커뮤니티 폭발력 8점 이상인 이슈만 생존시킨다.
"""

import json
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SCORER_PROMPT = """[Role]
너는 2040 한국 남성 투자자(디시, 펨코, 블라인드 유저)들의 도파민과 분노 버튼을 정확히 찾아내는 냉혹한 이슈 감별사다.

[Task]
제공된 뉴스/공시 리스트를 읽고, 각 이슈가 커뮤니티에서 피 터지는 논쟁(RED vs BLUE)을 일으킬 수 있는 '투기장 적합도'를 1~10점으로 평가하라. 평가가 끝난 후, 반드시 8점 이상(고관여 이슈)을 받은 기사들만 추려서 출력하라. 만약 8점 이상이 없다면 빈 배열([])을 출력하라.

[Scoring Criteria (8점 이상을 받는 조건)]
1. 명확한 적(Enemy)이 있는가? (개미 vs 기관, 시장 vs 규제, 경영권 분쟁 등)
2. 돈(탐욕)이나 세금(분노)과 직결되는가? (금투세, 공매도, 상폐, 테마주 폭등 등)
3. 뻔한 교과서적 이슈(단순 실적 발표, ESG 경영 등)는 제외.

[Output Format: JSON Only]
{
  "survivors": [
    {
      "id": 0,
      "score": 9,
      "reason": "이 이슈가 유저들을 미치게 만들 단 한 줄의 이유"
    }
  ]
}"""


def score_scouted(scouted_list: list[dict]) -> list[dict]:
    """scouted_list 항목들의 투기장 적합도를 평가하고 8점 이상만 반환한다."""
    if not scouted_list:
        return []

    # 임시 id 부여
    indexed = [{"id": i, **item} for i, item in enumerate(scouted_list)]
    user_content = json.dumps(indexed, ensure_ascii=False)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SCORER_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0.3,
        response_format={"type": "json_object"},
    )

    result = json.loads(response.choices[0].message.content)
    survivors_raw = result.get("survivors", [])

    # 원본 데이터와 merge + 안전장치
    merged = []
    for s in survivors_raw:
        idx = s.get("id", -1)
        score = s.get("score", 0)
        if 0 <= idx < len(scouted_list) and score >= 8:
            merged.append({
                **scouted_list[idx],
                "score": score,
                "reason": s.get("reason", ""),
            })

    # 점수 내림차순 정렬
    merged.sort(key=lambda x: x["score"], reverse=True)
    return merged
