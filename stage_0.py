"""Stage 0: Stage A 전용 뉴스 수집.

Stage 1과 독립적인 키워드 조합으로 '이벤트 드리븐' 후보 뉴스를 수집한다.
쿼리 로직: (경제 OR 정책 OR 금융) AND ("예정" OR "앞두고" OR "일정" OR "검토" OR "임박" OR "기로")

수집 결과는 Stage A에만 투입된다.
"""

import os
import requests
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from difflib import SequenceMatcher
from dotenv import load_dotenv

load_dotenv()

API_URL = "https://openapi.naver.com/v1/search/news.json"

# ── 키워드 조합 ──
_GROUP_A = ["경제", "정책", "금융"]
_GROUP_B = ["예정", "앞두고", "일정", "검토", "임박", "기로"]

# 1군 언론사
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


def _search(query: str, display: int = 50) -> list[dict]:
    headers = {
        "X-Naver-Client-Id": os.getenv("NAVER_CLIENT_ID"),
        "X-Naver-Client-Secret": os.getenv("NAVER_CLIENT_SECRET"),
    }
    params = {"query": query, "display": display, "sort": "date"}
    resp = requests.get(API_URL, headers=headers, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json().get("items", [])


def _is_similar(title: str, seen_titles: list[str], threshold: float = 0.45) -> bool:
    for seen in seen_titles:
        if SequenceMatcher(None, title, seen).ratio() >= threshold:
            return True
    return False


def fetch_stage0_news(extra_keywords: list[str] = None) -> str:
    """Stage 0 전용 뉴스 수집. Stage A에 투입할 원본 텍스트를 반환한다.

    Args:
        extra_keywords: Early Bird가 추출한 트렌드 키워드. _GROUP_A와 조합하여 추가 쿼리 생성.
    """
    seen_links: set[str] = set()
    seen_titles: list[str] = []
    articles: list[str] = []

    # 기본 3 × 6 = 18 쿼리 조합
    queries = [f"{a} {b}" for a in _GROUP_A for b in _GROUP_B]

    # Early Bird 키워드 추가: 3 × N 쿼리
    if extra_keywords:
        for kw in extra_keywords:
            for a in _GROUP_A:
                q = f"{a} {kw}"
                if q not in queries:
                    queries.append(q)

    for q in queries:
        try:
            items = _search(q, display=50)
        except Exception as e:
            print(f"  [WARN] Stage 0 '{q}' 검색 실패: {e}")
            continue

        for item in items:
            link = item.get("originallink") or item.get("link", "")
            if link in seen_links:
                continue

            # 1군 언론사 필터
            if not any(domain in link for domain in ELITE_MEDIA_DOMAINS):
                continue

            # 날짜 필터 (올해 기사만)
            pub_date_str = item.get("pubDate", "")
            if pub_date_str:
                try:
                    pub_dt = parsedate_to_datetime(pub_date_str)
                    if pub_dt.year != datetime.now().year:
                        continue
                except Exception:
                    pass

            title = item.get("title", "").replace("<b>", "").replace("</b>", "")
            desc = item.get("description", "").replace("<b>", "").replace("</b>", "")

            if len(title) < 10:
                continue

            # 스포츠/연예 노이즈 제거
            if any(k in title for k in (
                "축구", "야구", "농구", "배구", "골프", "올림픽", "월드컵",
                "K리그", "프리미어리그", "챔피언스리그", "MLB", "NBA", "KBO",
                "감독", "선수", "경기", "승리", "패배", "득점", "우승",
                "연예", "드라마", "아이돌", "K-POP",
            )):
                continue

            if _is_similar(title, seen_titles):
                continue

            seen_links.add(link)
            seen_titles.append(title)
            articles.append(f"[{title}] {desc} (출처: {link})")

    today_kr = _today_kr()
    print(f"  [Stage 0] {today_kr} 기준 | {len(queries)}개 쿼리 → {len(articles)}건 수집")

    return "\n".join(f"{i+1}. {a}" for i, a in enumerate(articles))


if __name__ == "__main__":
    import sys
    extra = sys.argv[1:] if len(sys.argv) > 1 else None
    raw = fetch_stage0_news(extra_keywords=extra)
    print(f"\n총 {len(raw.splitlines())}건")
