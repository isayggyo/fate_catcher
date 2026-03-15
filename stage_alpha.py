"""Stage Alpha: 글로벌 매크로 트리거 추출.

Finnhub/FMP/Alpha Vantage 데이터를 분석하여
72시간 내 5대 핵심 트리거를 TICKER-Event 형식으로 추출한다.
독립 스테이지로 기존 파이프라인과 무관하게 단독 실행.
"""

import json
import os
from datetime import datetime, timedelta
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

from fetchers.finnhub import fetch_finnhub_news
from fetchers.fmp import fetch_fmp_news
from fetchers.alpha_vantage import fetch_alpha_vantage_news

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL = "gpt-4o-mini"

TODAY = datetime.now().strftime("%Y-%m-%d")
DEADLINE_END = (datetime.now() + timedelta(days=3)).strftime("%Y-%m-%d")


def _fetch_global_news() -> str:
    """Finnhub + FMP + Alpha Vantage 뉴스를 합산하여 반환한다."""
    parts = []

    for label, fetcher in [
        ("Finnhub", fetch_finnhub_news),
        ("FMP", fetch_fmp_news),
        ("Alpha Vantage", fetch_alpha_vantage_news),
    ]:
        try:
            data = fetcher()
            if data and not data.startswith("[ERROR]") and not data.startswith("[INFO]"):
                count = len(data.strip().split("\n"))
                print(f"  [Stage Alpha] {label}: {count}건 수집")
                parts.append(f"=== {label} ===\n{data}")
            else:
                print(f"  [Stage Alpha] {label}: {data}")
        except Exception as e:
            print(f"  [Stage Alpha] {label} 실패: {e}")

    return "\n\n".join(parts)


def _build_prompt() -> str:
    return f"""당신은 'Fate Catcher'의 글로벌 매크로 전략가입니다.
오늘은 {TODAY}입니다. 유효 기한: {TODAY} ~ {DEADLINE_END}.

제공된 실시간 금융 데이터(Finnhub, FMP, Alpha Vantage)를 분석하여, 향후 72시간 내에 가격 변동성이나 정책적 결론이 극대화될 '5대 핵심 트리거'를 추출하십시오.

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

    raw_news = _fetch_global_news()
    if not raw_news.strip():
        print("  [Stage Alpha] 글로벌 뉴스 수집 실패. 빈 결과 반환.")
        return []

    print(f"  [Stage Alpha] GPT 분석 중... ({len(raw_news)}자)")

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
    return triggers


if __name__ == "__main__":
    import sys
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

    triggers = run_stage_alpha()
    print(f"\n글로벌 5대 트리거: {triggers}")

    with open("stage_alpha_result.json", "w", encoding="utf-8") as f:
        json.dump({"triggers": triggers}, f, ensure_ascii=False, indent=2)
    print("결과 저장: stage_alpha_result.json")
