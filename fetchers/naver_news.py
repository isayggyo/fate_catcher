"""네이버 뉴스 검색 API 연동 모듈.

필요 환경변수:
  NAVER_CLIENT_ID     - 네이버 개발자센터 Client ID
  NAVER_CLIENT_SECRET - 네이버 개발자센터 Client Secret

API 문서: https://developers.naver.com/docs/serviceapi/search/news/news.md
"""

import os
import requests

API_URL = "https://openapi.naver.com/v1/search/news.json"

# Fate Catcher 핵심 키워드
DEFAULT_QUERIES = [
    # Governance
    "경영권 분쟁",
    "지분 전쟁",
    "행동주의 펀드",
    "M&A 인수합병",
    "승계 경영",
    # Policy
    "금리 결정",
    "정부 규제",
    "국회 법안",
    "금융당국",
    "금투세",
    # Capital & Theme
    "유상증자",
    "물적분할",
    "CB 발행",
    "테마주",
    "AI 반도체",
]


def _search(query: str, display: int = 20, sort: str = "date") -> list[dict]:
    """네이버 뉴스 검색 단건 호출."""
    headers = {
        "X-Naver-Client-Id": os.getenv("NAVER_CLIENT_ID"),
        "X-Naver-Client-Secret": os.getenv("NAVER_CLIENT_SECRET"),
    }
    params = {"query": query, "display": display, "sort": sort}

    resp = requests.get(API_URL, headers=headers, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json().get("items", [])


def fetch_naver_news(queries: list[str] | None = None, display: int = 20) -> str:
    """여러 키워드로 뉴스를 수집하여 텍스트로 반환한다.

    Returns:
        GPT에 넘길 수 있는 뉴스 텍스트 문자열
    """
    if queries is None:
        queries = DEFAULT_QUERIES

    seen_links = set()
    articles = []
    idx = 0

    for q in queries:
        try:
            items = _search(q, display=display)
        except Exception as e:
            print(f"[WARN] 네이버 뉴스 '{q}' 검색 실패: {e}")
            continue

        for item in items:
            link = item.get("originallink") or item.get("link", "")
            if link in seen_links:
                continue
            seen_links.add(link)
            idx += 1

            # HTML 태그 제거
            title = item.get("title", "").replace("<b>", "").replace("</b>", "")
            desc = item.get("description", "").replace("<b>", "").replace("</b>", "")

            articles.append(f"{idx}. [{title}] {desc} (출처: {link})")

    return "\n".join(articles)
