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
DEADLINE_END = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")

TARGET_ISSUES = [
    "US CPI",
    "DLTR",
    "LULU",
    "Micron",
    "Jabil",
    "General Mills",
    "FedEx",
    "Carnival Corp",
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


def _build_prompt() -> str:
    return f"""당신은 'Fate Catcher'의 글로벌 매크로 전략가입니다.
오늘은 {TODAY}입니다. 유효 기한: {TODAY} ~ {DEADLINE_END}.

제공된 실시간 금융 데이터를 분석하여, 향후 72시간 내에 가격 변동성이나 정책적 결론이 극대화될 '5대 핵심 트리거'를 추출하십시오.

[분석 지침]
1. 단순 기업명(Apple)이 아니라, [티커 + 핵심 이벤트]의 결합 형태로 추출하십시오. (예: NVDA-Earnings, TSLA-Autonomous_Regulation)
2. '72시간 내 결판'이 가능한 이슈를 우선순위로 둡니다. (실적 발표, 지표 공시, 예정된 판결 등)
3. 데이터에서 'Surprise(예상치와의 괴리)'가 발생할 확률이 높은 섹터를 하나 이상 포함하십시오.

[출력 형식]
오직 아래 JSON 형식으로만 답변하라. 설명은 생략한다.
{{"triggers": ["TICKER-Event", "TICKER-Event", "TICKER-Event", "TICKER-Event", "TICKER-Event"]}}"""


def run_stage_alpha() -> list[str]:
    """글로벌 5대 핵심 트리거를 추출하여 반환한다."""
    print(f"  [Stage Alpha] {TODAY} 글로벌 매크로 분석 시작...")

    quest_materials = _fetch_global_news()

    if not quest_materials:
        print("  [Stage Alpha] 글로벌 뉴스 수집 실패. 빈 결과 반환.")
        return []

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
        return []

    print(f"\n  [Stage Alpha] GPT 분석 중... ({len(raw_news)}자)")

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": _build_prompt()},
            {"role": "user", "content": raw_news},
        ],
        temperature=0.5,
        max_tokens=500,
        response_format={"type": "json_object"},
    )

    raw_text = response.choices[0].message.content
    result = json.loads(raw_text)
    triggers = result.get("triggers", [])

    # 안전장치: 5개만
    triggers = [t.strip() for t in triggers if t.strip()][:5]

    print(f"  [Stage Alpha] 트리거 추출 완료: {triggers}")

    # 캐시 저장: Alpha-2 단독 실행용
    cache = {"triggers": triggers, "raw_news": raw_news, "date": TODAY}
    with open("stage_alpha_cache.json", "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
    print("  [Stage Alpha] 캐시 저장 완료: stage_alpha_cache.json")

    return triggers, raw_news


# ── Stage Alpha-2: 트리거 → 퀘스트 JSON 변환 ─────────────────

QUEST_PROMPT = f"""당신은 글로벌/국내 거시경제와 기업 실적을 분석하여, 투자자들의 치열한 논쟁을 유발하는 72시간 단기 예측 퀘스트(Quest)를 설계하는 수석 퀀트 애널리스트입니다.
오늘은 {{TODAY}}입니다.

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
  "category": "[Domestic 또는 Global] / [세부 섹터]",
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
        selected_indices: 유저가 선택한 트리거 번호 리스트 (1-based).
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
            triggers = cache["triggers"]
            raw_news = cache["raw_news"]
            print(f"  [Stage Alpha-2] 캐시 로드 완료 ({cache['date']})")

    if not use_cache:
        triggers, raw_news = run_stage_alpha()

    if not triggers:
        print("  [Stage Alpha-2] 트리거 없음. 퀘스트 생성 스킵.")
        return []

    # Alpha-1 결과 표시
    print(f"\n  {'='*50}")
    print("  [Stage Alpha-1] 트리거 목록:")
    for i, t in enumerate(triggers, 1):
        print(f"    {i}. {t}")
    print(f"  {'='*50}")

    # 선택 대기 모드
    if selected_indices is None:
        choice = input("\n  퀘스트로 변환할 번호를 입력하세요 (예: 1,3,5 / all): ").strip()
        if choice.lower() == "all":
            selected_indices = list(range(1, len(triggers) + 1))
        else:
            selected_indices = [int(x.strip()) for x in choice.split(",") if x.strip().isdigit()]

    # 선택된 트리거만 필터
    selected = []
    for idx in selected_indices:
        if 1 <= idx <= len(triggers):
            selected.append(triggers[idx - 1])
        else:
            print(f"  [경고] {idx}번은 범위 밖. 무시.")

    if not selected:
        print("  [Stage Alpha-2] 선택된 트리거 없음.")
        return []

    print(f"\n  [Stage Alpha-2] 선택: {selected}")

    prompt = QUEST_PROMPT.replace("{TODAY}", TODAY)

    # 트리거별 개별 API 호출 (gpt-4.1이 한 번에 여러 퀘스트 생성 불가 문제 해결)
    quests = []
    for i, trigger in enumerate(selected, 1):
        print(f"  [Stage Alpha-2] ({i}/{len(selected)}) {trigger} 퀘스트 생성 중...")

        user_msg = f"[트리거]\n- {trigger}\n\n[뉴스 원문]\n{raw_news}"

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

        print(f"  [Stage Alpha-2] ({i}/{len(selected)}) {trigger} - 완료")

    print(f"  [Stage Alpha-2] 퀘스트 {len(quests)}개 생성 완료")
    return quests


if __name__ == "__main__":
    import sys
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    # --cache 옵션: Alpha-1 스킵하고 캐시로 Alpha-2만 실행
    use_cache = "--cache" in sys.argv

    quests = run_stage_alpha_quests(use_cache=use_cache)
    print(f"\n{'='*60}")
    print(json.dumps(quests, ensure_ascii=False, indent=2))

    with open("stage_alpha_result.json", "w", encoding="utf-8") as f:
        json.dump(quests, f, ensure_ascii=False, indent=2)
    print(f"\n결과 저장: stage_alpha_result.json ({len(quests)}개 퀘스트)")
