"""Alpha Vantage 뉴스/센티멘트 API 연동 모듈.

필요 환경변수:
  ALPHA_VANTAGE_API_KEY - https://www.alphavantage.co/support/#api-key 에서 발급

API 문서: https://www.alphavantage.co/documentation/#news-sentiment
"""

import os
import requests

BASE_URL = "https://www.alphavantage.co/query"

# 관심 토픽
DEFAULT_TOPICS = "economy_fiscal,economy_monetary,finance,technology,blockchain"


def fetch_alpha_vantage_news(
    topics: str | None = None, limit: int = 50
) -> str:
    """Alpha Vantage 뉴스 센티멘트 데이터를 수집하여 텍스트로 반환한다."""
    api_key = os.getenv("ALPHA_VANTAGE_API_KEY")
    if not api_key:
        return "[ERROR] ALPHA_VANTAGE_API_KEY가 설정되지 않았습니다."

    if topics is None:
        topics = DEFAULT_TOPICS

    try:
        resp = requests.get(
            BASE_URL,
            params={
                "function": "NEWS_SENTIMENT",
                "topics": topics,
                "limit": limit,
                "apikey": api_key,
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return f"[ERROR] Alpha Vantage API 호출 실패: {e}"

    items = data.get("feed", [])
    if not items:
        return "[INFO] Alpha Vantage 뉴스가 없습니다."

    lines = []
    for i, item in enumerate(items, 1):
        title = item.get("title", "")
        summary = item.get("summary", "")[:200]
        url = item.get("url", "")
        source = item.get("source", "")
        sentiment = item.get("overall_sentiment_label", "")
        score = item.get("overall_sentiment_score", "")

        # 관련 티커
        tickers = [t.get("ticker", "") for t in item.get("ticker_sentiment", [])[:3]]
        ticker_str = ",".join(tickers) if tickers else ""

        prefix = f"[{ticker_str}] " if ticker_str else ""
        sent_tag = f" [sentiment: {sentiment} ({score})]" if sentiment else ""

        lines.append(
            f"{i}. {prefix}[{title}] {summary}{sent_tag} (source: {source}, url: {url})"
        )

    return "\n".join(lines)
