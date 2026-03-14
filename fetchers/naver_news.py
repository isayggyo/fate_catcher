"""네이버 뉴스 검색 API 연동 모듈.

필요 환경변수:
  NAVER_CLIENT_ID     - 네이버 개발자센터 Client ID
  NAVER_CLIENT_SECRET - 네이버 개발자센터 Client Secret

API 문서: https://developers.naver.com/docs/serviceapi/search/news/news.md
"""

import os
import requests
from datetime import datetime
from email.utils import parsedate_to_datetime
from difflib import SequenceMatcher

API_URL = "https://openapi.naver.com/v1/search/news.json"

# 1군 언론사 도메인 — 이 출처의 기사만 Stage 1에 투입
ELITE_MEDIA_DOMAINS = [
    "hankyung.com",   # 한국경제
    "mk.co.kr",       # 매일경제
    "thebell.co.kr",  # 더벨
]

# Policy 기사 검증용: 제목+설명에 이 중 하나라도 있어야 통과
POLICY_MUST_CONTAIN = [
    "금융위", "금감원", "공정위", "거래소", "증선위", "금융당국",
    "과징금", "제재", "영업정지", "상장폐지", "거래정지",
    "기준금리", "금투세", "공매도", "STO", "토큰증권",
    "법안", "규제", "시행령", "가이드라인",
]

# Policy 노이즈 제거: 제목에 이 키워드가 있으면 제외
POLICY_BLACKLIST = [
    "부동산", "임대", "전세", "월세", "다주택", "아파트", "빌딩",
    "연예", "스포츠", "드라마", "K-POP",
    "삼겹살", "물가", "생활",
]

# 카테고리별 키워드 (각 카테고리당 1회 API 호출)
CATEGORY_QUERIES = {
    "Governance": [
        "경영권", "가처분", "공개매수", "임시주총",
        "주주서한", "위임장", "블록딜",
        "경영권 분쟁", "지분 전쟁", "행동주의 펀드",
        "M&A 인수합병", "승계 경영",
    ],
    "Policy": [
        "과징금", "영업정지", "상장폐지", "거래정지",
        "금감원", "금융위", "공정위", "증선위",
        "기준금리", "공매도", "금투세",
        "STO 토큰증권", "가상자산 규제", "가상자산 제재",
        "국회 본회의", "시행령 개정",
        "금융당국", "관세", "무역규제", "제재 대상",
        "감사인 지정", "회계처리 위반", "검찰 고발",
    ],
    "Capital&Theme": [
        "잠정실적", "컨센서스", "보호예수 해제", "FDA 승인",
        "임상결과", "MSCI 편입", "무상증자",
        "실적 발표", "어닝 서프라이즈", "어닝 쇼크",
        "수주", "리밸런싱",
        "유상증자", "물적분할", "CB 발행", "테마주",
    ],
}


def _search(query: str, display: int = 50, sort: str = "date") -> list[dict]:
    """네이버 뉴스 검색 단건 호출."""
    headers = {
        "X-Naver-Client-Id": os.getenv("NAVER_CLIENT_ID"),
        "X-Naver-Client-Secret": os.getenv("NAVER_CLIENT_SECRET"),
    }
    params = {"query": query, "display": display, "sort": sort}

    resp = requests.get(API_URL, headers=headers, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json().get("items", [])


def _is_similar(title: str, seen_titles: list[str], threshold: float = 0.45) -> bool:
    """제목 유사도 기반 중복 판별."""
    for seen in seen_titles:
        if SequenceMatcher(None, title, seen).ratio() >= threshold:
            return True
    return False


MAX_PER_CATEGORY = 13


def _collect_category(keywords: list[str], seen_links: set, seen_titles: list[str], cat: str = "", max_items: int = MAX_PER_CATEGORY) -> list[str]:
    """카테고리 키워드 리스트로 기사를 수집한다 (URL + 제목 유사도 dedup)."""
    articles = []
    for kw in keywords:
        if len(articles) >= max_items:
            break
        try:
            items = _search(kw, display=50)
        except Exception as e:
            print(f"[WARN] 네이버 뉴스 '{kw}' 검색 실패: {e}")
            continue

        for item in items:
            if len(articles) >= max_items:
                break
            link = item.get("originallink") or item.get("link", "")
            if link in seen_links:
                continue
            # 1군 언론사 필터
            if not any(domain in link for domain in ELITE_MEDIA_DOMAINS):
                continue

            # 2026년 기사만 수집
            pub_date_str = item.get("pubDate", "")
            if pub_date_str:
                try:
                    pub_dt = parsedate_to_datetime(pub_date_str)
                    if pub_dt.year != 2026:
                        continue
                except Exception:
                    pass

            # HTML 태그 제거
            title = item.get("title", "").replace("<b>", "").replace("</b>", "")
            desc = item.get("description", "").replace("<b>", "").replace("</b>", "")

            # 제목 너무 짧으면 스킵 (잘린 제목)
            if len(title) < 10:
                continue

            # 주가조작/불공정거래 기사 제외
            if any(k in title for k in ("주가조작", "주가 조작", "불공정거래", "시세조종")):
                continue

            # Policy 카테고리: 제목에 핵심어 있으면 통과, 없으면 설명에 2개 이상 필요
            if cat == "Policy":
                title_hit = any(k in title for k in POLICY_MUST_CONTAIN)
                if not title_hit:
                    desc_hits = sum(1 for k in POLICY_MUST_CONTAIN if k in desc)
                    if desc_hits < 2:
                        continue
                if any(k in title for k in POLICY_BLACKLIST):
                    continue

            # 제목 유사도 중복 체크
            if _is_similar(title, seen_titles):
                continue

            seen_links.add(link)
            seen_titles.append(title)
            articles.append(f"[{title}] {desc} (출처: {link})")

    return articles


def fetch_naver_news(queries: list[str] | None = None, display: int = 50) -> str:
    """카테고리별 3회 호출로 뉴스를 수집하여 텍스트로 반환한다.

    Returns:
        GPT에 넘길 수 있는 뉴스 텍스트 문자열 (카테고리 태그 포함)
    """
    seen_links = set()
    seen_titles: list[str] = []
    all_lines = []
    idx = 0

    for cat, keywords in CATEGORY_QUERIES.items():
        cat_articles = _collect_category(keywords, seen_links, seen_titles, cat=cat)
        for article in cat_articles:
            idx += 1
            all_lines.append(f"{idx}. [{cat}] {article}")
        print(f"         [{cat}] {len(cat_articles)}건")

    return "\n".join(all_lines)


def fetch_naver_news_full(display: int = 50) -> str:
    """카테고리 제한 없이 전체 뉴스를 수집한다 (Stage A용, ~90개).

    MAX_PER_CATEGORY 제한을 100으로 풀어 카테고리별 최대한 수집.
    """
    seen_links = set()
    seen_titles: list[str] = []
    all_lines = []
    idx = 0

    for cat, keywords in CATEGORY_QUERIES.items():
        cat_articles = _collect_category(
            keywords, seen_links, seen_titles, cat=cat, max_items=100
        )
        for article in cat_articles:
            idx += 1
            all_lines.append(f"{idx}. [{cat}] {article}")
        print(f"         [{cat}] {len(cat_articles)}건 (full)")

    return "\n".join(all_lines)
