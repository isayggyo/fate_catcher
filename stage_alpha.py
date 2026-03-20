"""Stage Alpha: 글로벌 이슈 스나이핑 + 매크로 트리거 추출.

Tavily 검색으로 타겟 이슈별 뉴스를 수집한 뒤,
GPT로 72시간 내 5대 핵심 트리거를 TICKER-Event 형식으로 추출한다.
독립 스테이지로 기존 파이프라인과 무관하게 단독 실행.
"""

import json
import os
from datetime import datetime, timedelta
from openai import OpenAI
from tavily import TavilyClient
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
tavily = TavilyClient(api_key=os.getenv("TAVILY_API_KEY"))
MODEL = "gpt-4o-mini"

TODAY = datetime.now().strftime("%Y-%m-%d")
TODAY_WEEKDAY = ["월요일","화요일","수요일","목요일","금요일","토요일","일요일"][datetime.now().weekday()]
TODAY_US = (datetime.now() - timedelta(hours=14)).strftime("%Y-%m-%d")  # 한국 대비 약 -14h
TODAY_US_WEEKDAY = ["월요일","화요일","수요일","목요일","금요일","토요일","일요일"][(datetime.now() - timedelta(hours=14)).weekday()]
DEADLINE_END = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")

TARGET_ISSUES = [
    "Fed March FOMC rate hold Iran energy shock",
    "Strait of Hormuz oil supply global stagflation",
    "BOJ policy rate hike underlying inflation",
    "ECB BoE rate hold supply-side shock",
    "US 30-year mortgage rate high tech stock valuation",
]


def _fetch_global_news() -> dict[str, str]:
    """Tavily로 타겟 이슈별 뉴스를 검색하여 반환한다."""
    quest_materials: dict[str, str] = {}

    print("  [Stage Alpha] 글로벌 이슈 스나이핑 시작...\n")

    for issue in TARGET_ISSUES:
        print(f"  [Stage Alpha] 타겟 추적 중: {issue}...")
        try:
            response = tavily.search(
                query=issue,
                search_depth="advanced",
                include_domains=[
                    "reuters.com",
                    "bloomberg.com",
                    "cnbc.com",
                    "wsj.com",
                ],
                max_results=3,
            )

            combined = ""
            for result in response.get("results", []):
                combined += f"- {result['title']}: {result['content']}\n"

            quest_materials[issue] = combined

        except Exception as e:
            print(f"  [Stage Alpha] {issue} 검색 실패: {e}")

    return quest_materials


EXTRACTION_PROMPT = f"""You are a financial news analyst. Today is {TODAY} ({TODAY_WEEKDAY}). US date: {TODAY_US} ({TODAY_US_WEEKDAY}).

Extract structured facts from the provided news articles about a single issue. Only include what is explicitly stated or clearly implied in the articles. If a field cannot be determined, use "unknown".

Return JSON only. No explanation.
{{
  "event": "What is the specific event or data release?",
  "date": "When is the event scheduled? (YYYY-MM-DD or descriptive if exact date unknown)",
  "prior": "What was the previous reading or outcome?",
  "drivers": "Key factors driving this issue (comma-separated)",
  "policy_context": "Relevant central bank or government policy stance",
  "bull_case": "Why this could be better than expected (1 sentence)",
  "bear_case": "Why this could be worse than expected (1 sentence)"
}}"""


def _extract_articles(quest_materials: dict[str, str]) -> dict[str, dict]:
    """각 이슈의 뉴스에서 구조화된 팩트를 추출한다."""
    extracted = {}

    print(f"\n  [Extraction] 뉴스 팩트 추출 시작 ({len(quest_materials)}개 이슈)")

    for issue, news_text in quest_materials.items():
        if not news_text.strip():
            print(f"  [Extraction] {issue} — 뉴스 없음, 스킵")
            continue

        print(f"  [Extraction] {issue} 분석 중...")

        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": EXTRACTION_PROMPT},
                    {"role": "user", "content": f"[Issue: {issue}]\n{news_text}"},
                ],
                temperature=0.2,
                max_tokens=400,
                response_format={"type": "json_object"},
            )

            result = json.loads(response.choices[0].message.content)
            result["issue"] = issue
            extracted[issue] = result

            print(f"  [Extraction] {issue} → event: {result.get('event','?')} | date: {result.get('date','?')}")

        except Exception as e:
            print(f"  [Extraction] {issue} 실패: {e}")

    return extracted


SCORING_PROMPT = """You are an editor for a forecasting platform called 'Fate Catcher'.

Evaluate the following issue using the criteria below. Base your evaluation on the structured extraction provided.

Criteria:
1. market_impact (1-10): How much could this move markets in the next 72 hours?
2. uncertainty (1-10): How divided is the market on the outcome? (10 = maximum disagreement)
3. resolution_clarity (1-10): Can the outcome be objectively verified by a specific data release or event? (10 = binary yes/no verdict possible)
4. discussion_potential (1-10): How engaging is this as a debate topic for retail investors?
5. data_availability (1-10): How rich is the extracted data? (10 = exact date, consensus number, prior number all present; 1 = mostly "unknown")

Also provide:
- "trigger": A concise TICKER-Event label (e.g. "FOMC-Rate_Decision", "PMI-Manufacturing")
- "summary": One-sentence Korean summary of the current situation.

Return JSON only. No explanation.
{"market_impact": N, "uncertainty": N, "resolution_clarity": N, "discussion_potential": N, "data_availability": N, "trigger": "...", "summary": "..."}"""

# 가중치: w1=market_impact 30%, w2=uncertainty 20%, w3=resolution_clarity 15%, w4=discussion_potential 10%, w5=data_availability 25%
SCORE_WEIGHTS = {
    "market_impact": 0.30,
    "uncertainty": 0.20,
    "resolution_clarity": 0.15,
    "discussion_potential": 0.10,
    "data_availability": 0.25,
}


def _score_issues(extracted: dict[str, dict]) -> list[dict]:
    """추출된 팩트를 기반으로 각 이슈를 스코어링한다."""
    scored = []

    for issue, facts in extracted.items():
        print(f"  [Scoring] {issue} 평가 중...")

        facts_text = json.dumps(facts, ensure_ascii=False, indent=2)

        try:
            response = client.chat.completions.create(
                model=MODEL,
                messages=[
                    {"role": "system", "content": SCORING_PROMPT},
                    {"role": "user", "content": f"[Issue: {issue}]\n{facts_text}"},
                ],
                temperature=0.3,
                max_tokens=300,
                response_format={"type": "json_object"},
            )

            result = json.loads(response.choices[0].message.content)

            # 가중 총점 계산 (만점 10.0)
            weighted = sum(
                result.get(k, 0) * w for k, w in SCORE_WEIGHTS.items()
            )
            result["weighted_total"] = round(weighted, 2)
            result["issue"] = issue
            result["extraction"] = facts
            scored.append(result)

            print(f"  [Scoring] {issue} → {result['trigger']} (가중점: {result['weighted_total']}/10.0)")

        except Exception as e:
            print(f"  [Scoring] {issue} 실패: {e}")

    # 가중 총점 내림차순 정렬
    scored.sort(key=lambda x: x["weighted_total"], reverse=True)
    return scored


def run_stage_alpha() -> tuple[list[dict], str]:
    """글로벌 이슈를 수집하고 전체 스코어링하여 반환한다."""
    print(f"  [Stage Alpha] {TODAY} 글로벌 매크로 분석 시작...")

    quest_materials = _fetch_global_news()

    if not quest_materials:
        print("  [Stage Alpha] 글로벌 뉴스 수집 실패. 빈 결과 반환.")
        return [], ""

    # 검색 결과 요약 출력
    print(f"\n  [Stage Alpha] 검색 완료! {len(quest_materials)}개 이슈 수집")
    print("  " + "=" * 50)
    for key, val in quest_materials.items():
        print(f"  [{key}]")
        if val.strip():
            for line in val.strip().split("\n"):
                try:
                    print(f"    {line}")
                except UnicodeEncodeError:
                    print(f"    {line.encode('ascii', 'ignore').decode()}")
        else:
            print("    (결과 없음)")
        print("  " + "-" * 50)

    # GPT 분석용 텍스트 합산
    raw_news = "\n".join(
        f"[{k}]\n{v}" for k, v in quest_materials.items() if v.strip()
    )

    if not raw_news.strip():
        print("  [Stage Alpha] 유효 뉴스 없음. 빈 결과 반환.")
        return [], ""

    # 뉴스 팩트 추출
    extracted = _extract_articles(quest_materials)

    if not extracted:
        print("  [Stage Alpha] 팩트 추출 실패. 빈 결과 반환.")
        return [], ""

    # 추출 결과 출력
    print(f"\n  {'='*60}")
    print("  [Extraction] 추출 결과:")
    print(f"  {'─'*60}")
    for issue, facts in extracted.items():
        print(f"  [{issue}]")
        print(f"    event: {facts.get('event','?')}")
        print(f"    date: {facts.get('date','?')}")
        print(f"    prior: {facts.get('prior','?')}")
        print(f"    drivers: {facts.get('drivers','?')}")
        print(f"    policy_context: {facts.get('policy_context','?')}")
        print(f"  {'─'*60}")

    # 추출된 팩트 기반 스코어링
    print(f"\n  [Stage Alpha] GPT 스코어링 시작 ({len(extracted)}개 이슈)")
    scored = _score_issues(extracted)

    # 전체 결과 출력
    print(f"\n  {'='*60}")
    print("  [Stage Alpha] 스코어링 결과 (총점순):")
    print(f"  {'─'*60}")
    for i, s in enumerate(scored, 1):
        print(f"  {i}. {s['trigger']} (가중점: {s['weighted_total']}/10.0)")
        print(f"     M:{s.get('market_impact',0)}(30%) | U:{s.get('uncertainty',0)}(20%) | R:{s.get('resolution_clarity',0)}(15%) | D:{s.get('discussion_potential',0)}(10%) | DA:{s.get('data_availability',0)}(25%)")
        print(f"     {s.get('summary','')}")
        print(f"  {'─'*60}")

    # 캐시 저장
    triggers = [s["trigger"] for s in scored]
    cache = {"triggers": triggers, "scored": scored, "raw_news": raw_news, "date": TODAY}
    with open("stage_alpha_cache.json", "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
    print("  [Stage Alpha] 캐시 저장 완료: stage_alpha_cache.json")

    return scored, raw_news


# ── Stage Alpha-2: 트리거 → 퀘스트 JSON 변환 ─────────────────

QUEST_PROMPT = f"""당신은 글로벌/국내 거시경제와 기업 실적을 분석하여, 투자자들의 치열한 논쟁을 유발하는 72시간 단기 예측 퀘스트(Quest)를 설계하는 수석 퀀트 애널리스트입니다.
오늘은 {{TODAY}} ({{TODAY_WEEKDAY}})입니다. 미국 현재 날짜: {{TODAY_US}} ({{TODAY_US_WEEKDAY}}).

[목표]
제공된 최신 뉴스 요약본(팩트)을 바탕으로, 유저들이 베팅하고 분석 논리를 작성할 수 있는 완벽한 퀘스트 JSON을 생성하세요.

[필수 제약 조건]
1. 정산의 절대성 (Pivot): 승패 판정은 반드시 특정 기관의 '발표 수치(예: 3.2% 이상)' 또는 '명확한 공시/보도자료 유무'로 1초 만에 기계적 정산이 가능해야 합니다. "긍정적일 것이다", "상승할 것이다" 같은 애매한 표현은 절대 금지합니다.
2. 기한 (Deadline): 모든 이슈의 결판은 영업일 기준 3~7일 이내에 나야 합니다.
3. 갈등 구조 (Conflict): 반드시 아래 3파트를 포함하여 총 500자 내외로 서술하라.
   [배경] 이 이슈가 왜 지금 시장의 핵심 변수인지 1~2문장으로 설명.
   [Bull Case] 강세론자의 핵심 논거와 데이터 근거를 구체적으로 서술.
   [Bear Case] 약세론자의 핵심 논거와 데이터 근거를 구체적으로 서술.
   예시: "[배경] Micron은 HBM3E 양산 본격화를 앞두고 있으며, AI 인프라 투자 사이클의 최대 수혜주로 부각되고 있다. [Bull Case] 강세론자는 AI 서버용 HBM 수요가 전년 대비 3배 급증하고, SK하이닉스 대비 ASP 프리미엄까지 확보했다며 매출 $8.7B 상회를 전망한다. [Bear Case] 약세론자는 DRAM 범용 제품의 재고가 9주분으로 과잉 상태이고, PC/모바일 수요 부진이 블렌디드 마진을 훼손할 것이라며 가이던스 하회를 예상한다."
4. 언어: 모든 필드는 한국어로 작성하세요. questId만 영문대문자로 작성합니다.
5. 퀘스트 수: 제공된 트리거 수만큼 반드시 퀘스트를 생성하라. 트리거 5개면 퀘스트 5개. 누락 금지.
6. 출력 형식: 오직 순수한 JSON 배열만 출력하세요. 설명은 생략한다.

[JSON 출력 스키마 — 트리거 1개당 1개의 퀘스트]
{{{{
  "questId": "[영문대문자_이벤트명_날짜]",
  "title": "[직관적이고 도발적인 질문형 제목]",
  "category": "[세부 섹터만 표기: Macro, Earnings, Trade Policy, Commodities, Tech, Consumer, Industrials 등]",
  "deadline": "YYYY-MM-DD HH:MM (결과 발표 예정일시)",
  "conflict": "[시장의 논쟁점 및 파급 효과 상세 서술]",
  "trigger": "[결과를 확인하게 될 공식 이벤트명]",
  "pivot": "[정확하고 객관적인 RED/BLUE 판정 기준]",
  "options": {{{{
    "RED": "[Pivot 충족/상회]",
    "BLUE": "[Pivot 미달/하회]"
  }}}}
}}}}"""


def run_stage_alpha_quests(selected_indices: list[int] | None = None,
                           use_cache: bool = False) -> list[dict]:
    """선택된 트리거만 퀘스트 JSON으로 변환한다.

    Args:
        selected_indices: 유저가 선택한 트리거 번호 리스트 (1-based, 스코어링 순위 기준).
                          None이면 선택 대기.
        use_cache: True면 Alpha-1 재실행 없이 캐시에서 로드.
    """
    if use_cache:
        cache_path = os.path.join(os.path.dirname(__file__) or ".", "stage_alpha_cache.json")
        if not os.path.exists(cache_path):
            print("  [Stage Alpha-2] 캐시 없음. Alpha-1부터 실행합니다.")
            use_cache = False
        else:
            with open(cache_path, "r", encoding="utf-8") as f:
                cache = json.load(f)
            scored = cache["scored"]
            raw_news = cache["raw_news"]
            print(f"  [Stage Alpha-2] 캐시 로드 완료 ({cache['date']})")

    if not use_cache:
        scored, raw_news = run_stage_alpha()

    if not scored:
        print("  [Stage Alpha-2] 스코어링 결과 없음. 퀘스트 생성 스킵.")
        return []

    # Alpha-1 스코어링 결과 표시
    print(f"\n  {'='*50}")
    print("  [Alpha-1] 스코어링 결과:")
    for i, s in enumerate(scored, 1):
        print(f"    {i}. {s['trigger']} (가중점: {s['weighted_total']}/10.0)")
    print(f"  {'='*50}")

    # 선택 대기 모드
    if selected_indices is None:
        choice = input("\n  퀘스트로 변환할 번호를 입력하세요 (예: 1,3,5 / all): ").strip()
        if choice.lower() == "all":
            selected_indices = list(range(1, len(scored) + 1))
        else:
            selected_indices = [int(x.strip()) for x in choice.split(",") if x.strip().isdigit()]

    # 선택된 스코어 항목 필터
    selected_scores = []
    for idx in selected_indices:
        if 1 <= idx <= len(scored):
            selected_scores.append(scored[idx - 1])
        else:
            print(f"  [경고] {idx}번은 범위 밖. 무시.")

    if not selected_scores:
        print("  [Stage Alpha-2] 선택된 항목 없음.")
        return []

    print(f"\n  [Stage Alpha-2] 선택: {[s['trigger'] for s in selected_scores]}")

    prompt = QUEST_PROMPT.replace("{TODAY}", TODAY).replace("{TODAY_WEEKDAY}", TODAY_WEEKDAY).replace("{TODAY_US}", TODAY_US).replace("{TODAY_US_WEEKDAY}", TODAY_US_WEEKDAY)

    # 트리거별 개별 API 호출
    quests = []
    for i, score_item in enumerate(selected_scores, 1):
        trigger = score_item["trigger"]
        extraction = score_item.get("extraction", {})

        print(f"  [Stage Alpha-2] ({i}/{len(selected_scores)}) {trigger} 퀘스트 생성 중...")

        # extraction 팩트 + 뉴스 원문을 함께 전달
        extraction_text = json.dumps(extraction, ensure_ascii=False, indent=2)
        user_msg = f"[트리거]\n- {trigger}\n\n[추출된 팩트]\n{extraction_text}\n\n[뉴스 원문]\n{raw_news}"

        response = client.chat.completions.create(
            model="gpt-4.1",
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_msg},
            ],
            temperature=0.5,
            max_tokens=4000,
            response_format={"type": "json_object"},
        )

        raw_text = response.choices[0].message.content
        result = json.loads(raw_text)

        # 단일 퀘스트 또는 배열 처리
        if isinstance(result, list):
            quests.extend(result)
        elif "quests" in result:
            quests.extend(result["quests"])
        elif "quest" in result:
            quests.extend(result["quest"] if isinstance(result["quest"], list) else [result["quest"]])
        else:
            quests.append(result)

        print(f"  [Stage Alpha-2] ({i}/{len(selected_scores)}) {trigger} - 완료")

    print(f"  [Stage Alpha-2] 퀘스트 {len(quests)}개 생성 완료")
    return quests


if __name__ == "__main__":
    import sys
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    mode = sys.argv[1] if len(sys.argv) > 1 else ""

    if mode == "--alpha1":
        # Alpha-1만 실행: 스코어링까지만 하고 캐시 저장 후 종료
        scored, raw_news = run_stage_alpha()
        print(f"\n  Alpha-1 완료. 캐시 저장됨. Alpha-2는 --alpha2 로 실행하세요.")

    elif mode == "--alpha2":
        # Alpha-2만 실행: 캐시에서 로드 → 번호 선택 → 퀘스트 생성
        quests = run_stage_alpha_quests(use_cache=True)
        print(f"\n{'='*60}")
        print(json.dumps(quests, ensure_ascii=False, indent=2))
        with open("stage_alpha_result.json", "w", encoding="utf-8") as f:
            json.dump(quests, f, ensure_ascii=False, indent=2)
        print(f"\n결과 저장: stage_alpha_result.json ({len(quests)}개 퀘스트)")

    else:
        # 기본: Alpha-1 → Alpha-2 연속 실행
        quests = run_stage_alpha_quests(use_cache="--cache" in sys.argv)
        print(f"\n{'='*60}")
        print(json.dumps(quests, ensure_ascii=False, indent=2))
        with open("stage_alpha_result.json", "w", encoding="utf-8") as f:
            json.dump(quests, f, ensure_ascii=False, indent=2)
        print(f"\n결과 저장: stage_alpha_result.json ({len(quests)}개 퀘스트)")
