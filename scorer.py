"""Stage 2: 스코어링 + Yes/No 질문 변환 (통합).

Gemini 2.5 Pro를 사용하여 Stage 1 엄선 이슈를 한 번에:
  1) 투기장 적합도 스코어링 (1~10점)
  2) 7점 이상 생존자를 Yes/No 베팅 질문으로 변환
"""

import json
import os
from datetime import datetime, timedelta
from google import genai
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
MODEL = "gemini-2.5-pro"


def _build_prompt(domestic: bool = False) -> str:
    """domestic 여부에 따라 통합 프롬프트를 생성한다."""
    tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")

    domestic_filter = ""
    if domestic:
        domestic_filter = """
[CRITICAL: 국내 소스 필터]
이것은 국내(domestic) 뉴스 분석이다. 반드시 한국과 직접적으로 관련된 이슈만 생존시켜라.
- headline에 한국 관련 키워드가 포함되어야 한다: 한국, 코스피, 코스닥, 삼성, SK, LG, 현대, 카카오, 네이버, 한은, 금감원, 금융위, 국민연금, 서울, 부산, KRW, 원화, 한투, 키움, 미래에셋, 셀트리온, 하이브, 포스코, 두산, 롯데, CJ, KT, 대한민국, 정부, 국회, 대통령, 여야, 연금, 부동산, 전세, 아파트, 공매도, 금투세, 상폐, 따상, 코인원, 업비트, 빗썸, 경영권, 지분, 유상증자, 물적분할, CB, BW, 승계, M&A, 인수합병, 행동주의 등
- 해외 뉴스라도 한국 시장에 직접적 파급효과가 명확한 경우는 허용하되, headline을 한국 투자자 시점으로 재작성하라.
  예: "TSMC 점유율 확대" → "삼성 파운드리 점유율 위기, TSMC에 밀려"
- 한국과 무관한 순수 해외 이슈는 아무리 점수가 높아도 탈락시켜라.
"""

    return f"""[Role]
너는 2040 한국 남성 투자자(디시, 펨코, 블라인드 유저)들의 도파민과 분노 버튼을 정확히 찾아내는 냉혹한 이슈 감별사이자, 이슈를 내일({tomorrow}) 판정 가능한 Yes/No 베팅 질문으로 변환하는 전문가다.

[Task — 2단계를 한 번에 수행하라]

■ STEP A: 스코어링
제공된 뉴스/공시 리스트의 **모든** 이슈에 대해 커뮤니티에서 피 터지는 논쟁(RED vs BLUE)을 일으킬 수 있는 '투기장 적합도'를 1~10점으로 평가하라. 하나도 빠뜨리지 마라.
{domestic_filter}
[Scoring Criteria]
1. 명확한 적(Enemy)이 있는가? (개미 vs 기관, 시장 vs 규제, 경영권 분쟁 등)
2. 돈(탐욕)이나 세금(분노)과 직결되는가? (금투세, 공매도, 상폐, 테마주 폭등 등)
3. 뻔한 교과서적 이슈(단순 실적 발표, ESG 경영 등)는 낮은 점수.

■ STEP B: 7점 이상 생존자 → Yes/No 질문 변환
STEP A에서 7점 이상인 이슈만 골라 내일({tomorrow}) 판정 가능한 Yes/No 질문으로 변환하라.
7점 이상이 7개 미만이면 점수 상위 7개를 생존시켜라.

[질문 변환 규칙]
1. 질문은 내일({tomorrow}) 장 마감(15:30 KST) 또는 24시간 이내에 판정 가능해야 한다.
2. 판정 기준(resolution)을 구체적 수치와 함께 명시하라.
3. 질문은 한국어로, 투자 커뮤니티 유저가 바로 이해할 수 있게 작성하라.
4. side_yes와 side_no는 짧고 임팩트 있게 작성하라.
5. 같은 주제의 이슈가 여러 개 있으면 하나의 질문으로 통합하라. 중복 질문 절대 금지.

[프록시 전략 — 직접 판정이 어려운 이슈도 반드시 변환하라]
- 환율/금리 이슈 → "내일 원·달러 환율 X원 돌파할까?" (종가 기준)
- 지정학 리스크 → "내일 코스피 전일 대비 하락 마감할까?" (시장 반응으로 프록시)
- 정책/규제 이슈 → "내일 관련 법안 통과할까?" 또는 "내일 금리 동결/인하 결정?"
- 기업 이슈 → "내일 해당 종목 전일 대비 ±X% 이상 움직일까?" (주가 반응)
- 섹터 이슈 → "내일 관련 ETF/섹터 지수 상승 마감할까?"

[BANNED: 절대 금지]
- "관련 보도/발표가 나올까?" 류 질문 금지. 보도는 항상 나오므로 베팅 가치 없음.
- "뉴스가 나올까?" 류 질문 금지.
- resolution에 반드시 숫자 기준이나 공식적 결정 사항 포함.

[Output Format: JSON Only]
{{
  "scored": [
    {{
      "id": 0,
      "score": 9,
      "headline": "한국 투자자 시점 헤드라인 (국내 소스면 재작성, 글로벌이면 원본 유지)",
      "reason": "이 이슈가 유저들을 미치게 만들 단 한 줄의 이유"
    }}
  ],
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


def score_and_question(scouted_list: list[dict], domestic: bool = False) -> dict:
    """Stage 1 결과를 스코어링 + Yes/No 질문 변환하여 반환한다.

    Returns:
        {"survivors": [...], "questions": [...]}
    """
    if not scouted_list:
        return {"survivors": [], "questions": []}

    prompt = _build_prompt(domestic=domestic)

    # 임시 id 부여
    indexed = [{"id": i, **item} for i, item in enumerate(scouted_list)]
    user_content = json.dumps(indexed, ensure_ascii=False)

    response = client.models.generate_content(
        model=MODEL,
        contents=[
            {"role": "user", "parts": [{"text": f"{prompt}\n\n[INPUT]\n{user_content}"}]},
        ],
        config={
            "temperature": 0.3,
            "response_mime_type": "application/json",
        },
    )

    raw_text = response.text
    result = json.loads(raw_text)

    # ── 스코어링 결과 처리 ──
    scored_raw = result.get("scored", [])
    all_scored = []
    for s in scored_raw:
        idx = s.get("id", -1)
        score = s.get("score", 0)
        if 0 <= idx < len(scouted_list) and score > 0:
            entry = {**scouted_list[idx], "score": score, "reason": s.get("reason", "")}
            if s.get("headline"):
                entry["headline"] = s["headline"]
            all_scored.append(entry)

    all_scored.sort(key=lambda x: x["score"], reverse=True)

    # 7점 이상 필터, 최소 7개 보장
    MIN_SURVIVORS = 7
    survivors = [x for x in all_scored if x["score"] >= 7]
    if len(survivors) < MIN_SURVIVORS:
        survivors = all_scored[:MIN_SURVIVORS]

    # ── 질문 결과 처리 ──
    questions_raw = result.get("questions", [])
    questions = []
    for q in questions_raw:
        idx = q.get("id", -1)
        if 0 <= idx < len(scouted_list):
            entry = {
                **scouted_list[idx],
                "question": q.get("question", ""),
                "side_yes": q.get("side_yes", ""),
                "side_no": q.get("side_no", ""),
                "resolution": q.get("resolution", ""),
                "deadline": q.get("deadline", ""),
            }
            # 스코어링에서 받은 score/reason도 병합
            for s in all_scored:
                if s.get("headline") == scouted_list[idx].get("headline"):
                    entry["score"] = s["score"]
                    entry["reason"] = s["reason"]
                    if s.get("headline"):
                        entry["headline"] = s["headline"]
                    break
            questions.append(entry)

    return {"survivors": survivors, "questions": questions}
