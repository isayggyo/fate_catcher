"""Early Bird: 매일 아침 7시 트렌드 키워드 추출.

GPT-4o-mini가 오늘의 핫 이슈 5개를 선정하고,
각 이슈에서 핵심 키워드 한 단어씩(총 5개)을 뽑아
Stage 0 검색 키워드에 동적으로 추가한다.
"""

import json
import os
from datetime import datetime
from openai import OpenAI
from dotenv import load_dotenv
import requests

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL = "gpt-4o-mini"

API_URL = "https://openapi.naver.com/v1/search/news.json"

ELITE_MEDIA_DOMAINS = [
    "hankyung.com",
    "mk.co.kr",
    "thebell.co.kr",
    "einfomax.co.kr",
    "edaily.co.kr",
    "mt.co.kr",
    "bizwatch.co.kr",
]

_WEEKDAYS_KR = ["월요일", "화요일", "수요일", "목요일", "금요일", "토요일", "일요일"]


def _today_kr() -> str:
    now = datetime.now()
    return f"{now.year}년 {now.month}월 {now.day}일 {_WEEKDAYS_KR[now.weekday()]}"


def _fetch_trending_news() -> str:
    """네이버 뉴스 API로 오늘의 주요 뉴스를 수집한다."""
    headers = {
        "X-Naver-Client-Id": os.getenv("NAVER_CLIENT_ID"),
        "X-Naver-Client-Secret": os.getenv("NAVER_CLIENT_SECRET"),
    }
    trending_queries = ["속보 경제", "긴급 금융", "주요 정책", "오늘 증시", "핫이슈 산업"]
    articles = []

    for q in trending_queries:
        try:
            params = {"query": q, "display": 50, "sort": "date"}
            resp = requests.get(API_URL, headers=headers, params=params, timeout=10)
            resp.raise_for_status()
            items = resp.json().get("items", [])
            for item in items:
                link = item.get("originallink") or item.get("link", "")
                if not any(domain in link for domain in ELITE_MEDIA_DOMAINS):
                    continue
                title = item.get("title", "").replace("<b>", "").replace("</b>", "")
                desc = item.get("description", "").replace("<b>", "").replace("</b>", "")
                if len(title) >= 10:
                    articles.append(f"[{title}] {desc}")
        except Exception as e:
            print(f"  [WARN] Early Bird '{q}' 검색 실패: {e}")
            continue

    return "\n".join(articles)


def _build_prompt() -> str:
    today = _today_kr()
    return f"""[System Role]
너는 트렌드 분석가다. 매일 아침 7시에 핫한 트렌드를 분석한다.
오늘은 {today}이다.

[Task]
아래 뉴스 목록을 분석하여 오늘 가장 핫한 이슈 5개를 선정하라.
각 이슈에서 뉴스 검색에 유효한 핵심 키워드를 **한 단어**로 추출하라.

[Rules]
1. 키워드는 반드시 한 단어여야 한다. (예: "반도체", "관세", "금리", "합병", "파업")
2. 너무 일반적인 단어(경제, 정책, 금융, 시장, 투자)는 피하라. 이미 기본 검색에 포함되어 있다.
3. 고유명사(기업명, 인물명, 기관명)도 가능하다.
4. 5개 키워드는 서로 중복되지 않아야 한다.
5. 스포츠/연예 관련 키워드는 제외한다.

[Output Format]
오직 아래 JSON 형식으로만 답변하라. 설명은 생략한다.
{{"keywords": ["키워드1", "키워드2", "키워드3", "키워드4", "키워드5"]}}"""


def run_early_bird() -> list[str]:
    """오늘의 트렌드 키워드 5개를 반환한다."""
    print(f"  [Early Bird] {_today_kr()} 트렌드 분석 시작...")

    raw_news = _fetch_trending_news()
    if not raw_news.strip():
        print("  [Early Bird] 트렌딩 뉴스 수집 실패. 빈 키워드 반환.")
        return []

    print(f"  [Early Bird] {len(raw_news.splitlines())}건 뉴스로 GPT 분석 중...")

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": _build_prompt()},
            {"role": "user", "content": raw_news},
        ],
        temperature=0.3,
        max_tokens=500,
        response_format={"type": "json_object"},
    )

    raw_text = response.choices[0].message.content
    result = json.loads(raw_text)
    keywords = result.get("keywords", [])

    # 안전장치: 5개만, 각각 한 단어
    keywords = [k.strip() for k in keywords if k.strip()][:5]

    print(f"  [Early Bird] 키워드 추출 완료: {keywords}")
    return keywords


if __name__ == "__main__":
    keywords = run_early_bird()
    print(f"\n트렌드 키워드: {keywords}")
