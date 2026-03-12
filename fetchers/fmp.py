"""Financial Modeling Prep (FMP) API 연동 모듈.

필요 환경변수:
  FMP_API_KEY - https://site.financialmodelingprep.com/developer 에서 발급

API 문서: https://site.financialmodelingprep.com/developer/docs
"""

import os
import requests

BASE_URL = "https://financialmodelingprep.com/api/v3"


def _get(endpoint: str, params: dict | None = None) -> list:
    """FMP API 공통 호출."""
    api_key = os.getenv("FMP_API_KEY")
    if not api_key:
        return []

    p = {"apikey": api_key}
    if params:
        p.update(params)

    resp = requests.get(f"{BASE_URL}/{endpoint}", params=p, timeout=10)
    resp.raise_for_status()
    return resp.json()


def fetch_fmp_news(limit: int = 30) -> str:
    """FMP 주식 뉴스 + 일반 뉴스를 수집하여 텍스트로 반환한다."""
    api_key = os.getenv("FMP_API_KEY")
    if not api_key:
        return "[ERROR] FMP_API_KEY가 설정되지 않았습니다."

    seen_urls = set()
    lines = []
    idx = 0

    # 1) 일반 뉴스
    try:
        general = _get("fmp/articles", {"page": 0, "size": limit})
        # FMP articles endpoint returns {"content": [...]}
        articles = general if isinstance(general, list) else general.get("content", [])
    except Exception as e:
        print(f"[WARN] FMP articles 실패: {e}")
        articles = []

    # 2) 주식 뉴스
    try:
        stock_news = _get("stock_news", {"limit": limit})
    except Exception as e:
        print(f"[WARN] FMP stock_news 실패: {e}")
        stock_news = []

    for item in articles + stock_news:
        url = item.get("url") or item.get("link", "")
        if url in seen_urls:
            continue
        seen_urls.add(url)
        idx += 1

        title = item.get("title", "")
        text = (item.get("text") or item.get("content") or "")[:200]
        symbol = item.get("symbol", "")
        site = item.get("site") or item.get("source", "")

        prefix = f"[{symbol}] " if symbol else ""
        lines.append(f"{idx}. {prefix}[{title}] {text} (source: {site}, url: {url})")

    return "\n".join(lines)
