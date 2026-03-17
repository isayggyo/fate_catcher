"""DART 전자공시 API 연동 모듈.

필요 환경변수:
  DART_API_KEY - OpenDART에서 발급받은 API 키

API 문서: https://opendart.fss.or.kr/guide/main.do
"""

import os
import io
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import requests

BASE_URL = "https://opendart.fss.or.kr/api"

def _get_api_key() -> str | None:
    return os.getenv("DART_API_KEY")

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


# ============================================================
# 재무제표 관련 함수 (Fate Catcher Scanner용)
# ============================================================

def get_corp_code(corp_name: str) -> str | None:
    """기업명으로 DART 고유번호(corp_code)를 조회한다."""
    api_key = _get_api_key()
    if not api_key:
        return None

    resp = requests.get(
        f"{BASE_URL}/corpCode.xml",
        params={"crtfc_key": api_key},
        timeout=30,
    )
    resp.raise_for_status()

    with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
        with zf.open("CORPCODE.xml") as f:
            tree = ET.parse(f)

    # 1차: 정확히 일치하는 상장 기업 우선
    # 2차: 이름에 포함되는 상장 기업
    # 3차: 이름에 포함되는 비상장 기업
    exact_listed = None
    partial_listed = None
    partial_any = None

    for corp in tree.getroot().findall("list"):
        name = corp.findtext("corp_name", "")
        stock_code = (corp.findtext("stock_code", "") or "").strip()
        code = corp.findtext("corp_code", "")

        if name == corp_name:
            if stock_code:
                return code  # 정확히 일치 + 상장 → 즉시 반환
            if exact_listed is None:
                exact_listed = code
        elif corp_name in name:
            if stock_code and partial_listed is None:
                partial_listed = code
            elif partial_any is None:
                partial_any = code

    return exact_listed or partial_listed or partial_any


def fetch_financial_statements(
    corp_code: str,
    bsns_year: str,
    reprt_code: str = "11011",
    fs_div: str = "CFS",
) -> dict:
    """DART 단일회사 전체 재무제표를 조회하여 dict(list)로 반환한다.

    Args:
        corp_code: DART 고유번호
        bsns_year: 사업연도 (예: '2024')
        reprt_code: 11011=사업보고서, 11013=1분기, 11012=반기, 11014=3분기
        fs_div: CFS=연결, OFS=개별

    Returns:
        DART API 응답 dict. 성공 시 'list' 키에 계정과목 리스트 포함.
    """
    api_key = _get_api_key()
    if not api_key:
        return {"status": "error", "message": "DART_API_KEY 미설정"}

    resp = requests.get(
        f"{BASE_URL}/fnlttSinglAcntAll.json",
        params={
            "crtfc_key": api_key,
            "corp_code": corp_code,
            "bsns_year": bsns_year,
            "reprt_code": reprt_code,
            "fs_div": fs_div,
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()
