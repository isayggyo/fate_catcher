"""Finnhub 마켓 뉴스 API 연동 모듈.

필요 환경변수:
  FINNHUB_API_KEY - https://finnhub.io/dashboard 에서 발급

API 문서: https://finnhub.io/docs/api/market-news
"""

import os
import requests

BASE_URL = "https://finnhub.io/api/v1"

# 뉴스 카테고리
CATEGORIES = ["general", "forex", "crypto", "merger"]


def fetch_finnhub_news(categories: list[str] | None = None, min_id: int = 0) -> str:
    """Finnhub 마켓 뉴스를 수집하여 텍스트로 반환한다."""
    api_key = os.getenv("FINNHUB_API_KEY")
    if not api_key:
        return "[ERROR] FINNHUB_API_KEY가 설정되지 않았습니다."

    if categories is None:
        categories = CATEGORIES

    seen_ids = set()
    lines = []
    idx = 0

    for cat in categories:
        try:
            resp = requests.get(
                f"{BASE_URL}/news",
                params={"category": cat, "minId": min_id, "token": api_key},
                timeout=10,
            )
            resp.raise_for_status()
            items = resp.json()
        except Exception as e:
            print(f"[WARN] Finnhub '{cat}' 뉴스 실패: {e}")
            continue

        for item in items[:15]:  # 카테고리당 최대 15건
            news_id = item.get("id", 0)
            if news_id in seen_ids:
                continue
            seen_ids.add(news_id)
            idx += 1

            headline = item.get("headline", "")
            summary = item.get("summary", "")[:200]
            url = item.get("url", "")
            source = item.get("source", "")

            lines.append(
                f"{idx}. [{headline}] {summary} (source: {source}, url: {url})"
            )

    return "\n".join(lines)
