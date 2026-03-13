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
제공된 뉴스/공시 리스트를 읽고, **모든** 이슈에 대해 커뮤니티에서 피 터지는 논쟁(RED vs BLUE)을 일으킬 수 있는 '투기장 적합도'를 1~10점으로 평가하라. 반드시 입력된 모든 항목에 점수를 매겨서 출력하라. 하나도 빠뜨리지 마라.

[Scoring Criteria]
1. 명확한 적(Enemy)이 있는가? (개미 vs 기관, 시장 vs 규제, 경영권 분쟁 등)
2. 돈(탐욕)이나 세금(분노)과 직결되는가? (금투세, 공매도, 상폐, 테마주 폭등 등)
3. 뻔한 교과서적 이슈(단순 실적 발표, ESG 경영 등)는 낮은 점수.

[Output Format: JSON Only — 반드시 모든 항목 포함]
{
  "survivors": [
    {
      "id": 0,
      "score": 9,
      "reason": "이 이슈가 유저들을 미치게 만들 단 한 줄의 이유"
    }
  ]
}"""

SCORER_PROMPT_DOMESTIC = """[Role]
너는 2040 한국 남성 투자자(디시, 펨코, 블라인드 유저)들의 도파민과 분노 버튼을 정확히 찾아내는 냉혹한 이슈 감별사다.

[Task]
제공된 뉴스/공시 리스트를 읽고, **모든** 이슈에 대해 커뮤니티에서 피 터지는 논쟁(RED vs BLUE)을 일으킬 수 있는 '투기장 적합도'를 1~10점으로 평가하라. 반드시 입력된 모든 항목에 점수를 매겨서 출력하라. 하나도 빠뜨리지 마라.

[CRITICAL: 국내 소스 필터]
이것은 국내(domestic) 뉴스 분석이다. 반드시 한국과 직접적으로 관련된 이슈만 생존시켜라.
- headline에 한국 관련 키워드가 포함되어야 한다: 한국, 코스피, 코스닥, 삼성, SK, LG, 현대, 카카오, 네이버, 한은, 금감원, 금융위, 국민연금, 서울, 부산, KRW, 원화, 한투, 키움, 미래에셋, 셀트리온, 하이브, 포스코, 두산, 롯데, CJ, KT, 대한민국, 정부, 국회, 대통령, 여야, 연금, 부동산, 전세, 아파트, 공매도, 금투세, 상폐, 따상, 코인원, 업비트, 빗썸 등
- 해외 뉴스라도 한국 시장에 직접적 파급효과가 명확한 경우(예: "미국 금리 인상 → 코스피 하락 전망")는 허용하되, headline을 한국 투자자 시점으로 재작성하라.
  예: "TSMC 점유율 확대" → "삼성 파운드리 점유율 위기, TSMC에 밀려"
- 한국과 무관한 순수 해외 이슈는 아무리 점수가 높아도 탈락시켜라.

[Scoring Criteria]
1. 명확한 적(Enemy)이 있는가? (개미 vs 기관, 시장 vs 규제, 경영권 분쟁 등)
2. 돈(탐욕)이나 세금(분노)과 직결되는가? (금투세, 공매도, 상폐, 테마주 폭등 등)
3. 뻔한 교과서적 이슈(단순 실적 발표, ESG 경영 등)는 낮은 점수.

[Output Format: JSON Only — 반드시 모든 항목 포함]
{
  "survivors": [
    {
      "id": 0,
      "score": 9,
      "headline": "한국 투자자 시점으로 재작성된 헤드라인",
      "reason": "이 이슈가 유저들을 미치게 만들 단 한 줄의 이유"
    }
  ]
}"""


def score_scouted(scouted_list: list[dict], domestic: bool = False) -> list[dict]:
    """scouted_list 항목들의 투기장 적합도를 평가하고 7점 이상만 반환한다.

    최소 7개를 보장한다. 7점 이상이 7개 미만이면 점수 순으로 상위 7개를 반환.
    domestic=True이면 한국 관련 키워드 필터가 적용된 프롬프트를 사용한다.
    """
    if not scouted_list:
        return []

    prompt = SCORER_PROMPT_DOMESTIC if domestic else SCORER_PROMPT

    # 임시 id 부여
    indexed = [{"id": i, **item} for i, item in enumerate(scouted_list)]
    user_content = json.dumps(indexed, ensure_ascii=False)

    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": user_content},
        ],
        temperature=0.3,
        response_format={"type": "json_object"},
    )

    result = json.loads(response.choices[0].message.content)
    survivors_raw = result.get("survivors", [])

    # 원본 데이터와 merge
    all_scored = []
    for s in survivors_raw:
        idx = s.get("id", -1)
        score = s.get("score", 0)
        if 0 <= idx < len(scouted_list) and score > 0:
            entry = {**scouted_list[idx], "score": score, "reason": s.get("reason", "")}
            if domestic and s.get("headline"):
                entry["headline"] = s["headline"]
            all_scored.append(entry)

    # 점수 내림차순 정렬
    all_scored.sort(key=lambda x: x["score"], reverse=True)

    # 7점 이상 필터, 최소 7개 보장
    MIN_SURVIVORS = 7
    merged = [x for x in all_scored if x["score"] >= 7]
    if len(merged) < MIN_SURVIVORS:
        merged = all_scored[:MIN_SURVIVORS]

    return merged
