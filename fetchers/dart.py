"""DART 전자공시 API 연동 모듈.

필요 환경변수:
  DART_API_KEY - OpenDART에서 발급받은 API 키

API 문서: https://opendart.fss.or.kr/guide/main.do
"""

import os
from datetime import datetime, timedelta
import requests

BASE_URL = "https://opendart.fss.or.kr/api"

# 주요 공시 유형
REPORT_TYPES = {
    "A": "정기공시",
    "B": "주요사항보고",
    "C": "발행공시",
    "D": "지분공시",
    "E": "기타공시",
    "F": "외부감사관련",
    "G": "펀드공시",
    "H": "자산유동화",
    "I": "거래소공시",
}


def fetch_dart_disclosures(
    bgn_de: str | None = None,
    end_de: str | None = None,
    pblntf_ty: str = "",
    page_count: int = 100,
) -> str:
    """DART 공시 목록을 조회하여 텍스트로 반환한다.

    Args:
        bgn_de: 시작일 (YYYYMMDD). 기본값: 3일 전
        end_de: 종료일 (YYYYMMDD). 기본값: 오늘
        pblntf_ty: 공시유형 (A~I). 빈 문자열이면 전체
        page_count: 가져올 건수 (최대 100)

    Returns:
        GPT에 넘길 수 있는 공시 텍스트 문자열
    """
    api_key = os.getenv("DART_API_KEY")
    if not api_key:
        return "[ERROR] DART_API_KEY가 설정되지 않았습니다."

    today = datetime.now()
    if end_de is None:
        end_de = today.strftime("%Y%m%d")
    if bgn_de is None:
        bgn_de = (today - timedelta(days=3)).strftime("%Y%m%d")

    params = {
        "crtfc_key": api_key,
        "bgn_de": bgn_de,
        "end_de": end_de,
        "page_count": page_count,
        "sort": "date",
        "sort_mth": "desc",
    }
    if pblntf_ty:
        params["pblntf_ty"] = pblntf_ty

    try:
        resp = requests.get(
            f"{BASE_URL}/list.json", params=params, timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        return f"[ERROR] DART API 호출 실패: {e}"

    if data.get("status") != "000":
        return f"[ERROR] DART 응답 오류: {data.get('message', 'unknown')}"

    items = data.get("list", [])
    if not items:
        return "[INFO] 해당 기간 공시가 없습니다."

    lines = []
    for i, item in enumerate(items, 1):
        corp = item.get("corp_name", "")
        title = item.get("report_nm", "")
        date = item.get("rcept_dt", "")
        rcept_no = item.get("rcept_no", "")
        url = f"https://dart.fss.or.kr/dsaf001/main.do?rcpNo={rcept_no}"

        lines.append(f"{i}. [{date}] {corp} - {title} (공시링크: {url})")

    return "\n".join(lines)
