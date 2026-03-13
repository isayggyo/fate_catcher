import json
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
MODEL = "gpt-4o-mini"

# 카테고리별 프롬프트 템플릿
CATEGORIES = {
    "Governance": {
        "label": "Governance (지배구조)",
        "desc": "지분 전쟁, 경영권 분쟁, 승계 작업, 행동주의 펀드의 기습, M&A 갈등, 이사회 갈등, 대주주 지분 변동, 적대적 인수, 주주총회 표 대결, 전문경영인 교체, 오너 리스크.",
    },
    "Policy": {
        "label": "Policy (정책·규제)",
        "desc": "금리 결정, 정부의 특정 산업 규제/지원, 국회 법안 통과 여부, 금융당국의 압박, 금투세, 공매도 재개, 세법 개정, 중앙은행 통화정책, 금감원 제재, 관세/무역 규제.",
    },
    "Capital&Theme": {
        "label": "Capital & Theme (자본·테마)",
        "desc": "유상증자, 물적분할, CB/BW 발행, 초전도체/AI 등 테마주 이슈, 주가 급등락, 환율/유가/금 등 원자재 변동, 비트코인/알트코인, IPO/수요예측, 자사주 소각, ETF 상장.",
    },
}


def _build_category_prompt(cat_key: str) -> str:
    cat = CATEGORIES[cat_key]
    return f"""# ROLE
너는 플랫폼 'Fate Catcher'의 수석 뉴스 스카우트다.

# MISSION
아래 뉴스 데이터에서 [{cat['label']}] 카테고리에 해당하는 이슈를 최소 13개 이상 찾아라.

## {cat['label']} 범위
{cat['desc']}

# FILTERING CRITERIA
1. Quantitative: 향후 특정 시점에 숫자(주가, 지표, 투표수)로 승패를 가릴 수 있는가?
2. High Stakes: 돈, 자산, 커리어, 국가적 경쟁력과 직결되는가?
3. Conflict: 찬반이 팽팽하게 대립할 여지가 있는가?

# RULES
- 중복 금지: 동일 종목/이슈/사건은 1개만 남겨라.
- 팩트 기반: 제공된 뉴스에 없는 내용을 만들지 마라.
- 최소 13개: 13개 미만이면 실패.
- 연예/가십/스포츠/사고 제외.

# "한 놈만 팬다" 규칙 (Single Entity Rule) — 최우선 적용
- 동일 기업, 동일 인물, 동일 정부 부처가 얽힌 이슈는 내용이 다르더라도 무조건 '하나의 사건'이다.
- 예: '고려아연 MBK 갈등', '고려아연 주총 표 대결', 'MBK 김병주 회장 구속 위기' → [고려아연 경영권 분쟁] 하나만 남긴다.
- 예: '금융당국 공매도 경고', '금융당국 금투세 논의' → 금융당국이 중복이므로 더 자극적인 것 하나만.
- 이미 리스트에 올린 기업/인물/기관이 다른 뉴스에서 또 나오면 버려라.

# OUTPUT FORMAT (JSON only)
{{"scouted_list": [
  {{
    "category": "{cat_key}",
    "headline": "기사 제목",
    "summary": "핵심 1문장",
    "prediction_point": "예측 가능한 수치",
    "source_url": "URL",
    "data_source": "출처명 (YYYY-MM-DD)"
  }}
]}}"""


import re

# "한 놈만 팬다" — 엔티티 추출용 패턴
_ENTITY_PATTERN = re.compile(
    r"고려아연|한미약품|MBK|삼성전자|삼성|SK하이닉스|SK|LG화학|LG|현대차|현대|"
    r"카카오|네이버|셀트리온|하이브|포스코|두산|롯데|CJ|KT|한화|미래에셋|키움|"
    r"넷마블|크래프톤|엔씨소프트|쿠팡|토스|KCC|RFHIC|제주반도체|한패스|토비스|팰리서|"
    r"금감원|금융감독원|금융당국|금융위|한은|한국은행|국민연금|기재부|산업부|국회|정부|"
    r"이재용|최태원|신동빈|정의선|김범수|최윤범|임종룡"
)


# 같은 엔티티로 취급할 별칭 매핑
_ENTITY_ALIASES = {
    "금감원": "금융당국", "금융감독원": "금융당국", "금융위": "금융당국",
    "한은": "한국은행",
    "삼성전자": "삼성", "SK하이닉스": "SK",
    "현대차": "현대", "LG화학": "LG",
}


def _extract_entities(headline: str) -> set:
    """headline에서 주요 엔티티(기업/인물/기관)를 추출. 별칭 정규화."""
    raw = set(_ENTITY_PATTERN.findall(headline))
    return {_ENTITY_ALIASES.get(e, e) for e in raw}


def _dedup(scouted: list) -> list:
    """headline 유사도 + 엔티티 기반 "한 놈만 팬다" 중복 제거."""
    from difflib import SequenceMatcher
    seen_urls = set()
    seen_entities = set()
    unique = []
    for item in scouted:
        url = item.get("source_url", "")
        headline = item.get("headline", "")
        # 1) 같은 URL이면 스킵
        if url and url in seen_urls:
            continue
        # 2) headline 유사도 0.75 이상이면 스킵
        is_dup = False
        for kept in unique:
            ratio = SequenceMatcher(None, headline, kept["headline"]).ratio()
            if ratio >= 0.75:
                is_dup = True
                break
        if is_dup:
            continue
        # 3) "한 놈만 팬다" — 이미 등장한 엔티티가 있으면 스킵
        entities = _extract_entities(headline)
        if entities and entities & seen_entities:
            continue
        seen_urls.add(url)
        seen_entities.update(entities)
        unique.append(item)
    return unique


def _scan_category(raw_news_data: str, cat_key: str) -> list:
    """단일 카테고리에 대해 GPT-4o를 호출하여 이슈를 추출한다."""
    prompt = _build_category_prompt(cat_key)
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": f"[RAW_NEWS_INPUT]\n{raw_news_data}"},
        ],
        temperature=0.3,
        max_tokens=8000,
        response_format={"type": "json_object"},
    )
    result = json.loads(response.choices[0].message.content)
    items = result.get("scouted_list", [])
    # 카테고리 강제 태깅
    for item in items:
        item["category"] = cat_key
    return items


def scan_news(raw_news_data: str) -> dict:
    """GPT-4o로 카테고리별 3회 호출 → 병합 → dedup."""
    all_scouted = []
    for cat_key in CATEGORIES:
        label = CATEGORIES[cat_key]["label"]
        print(f"    [{label}] 스카우팅 중...")
        items = _scan_category(raw_news_data, cat_key)
        deduped = _dedup(items)
        print(f"    [{label}] → {len(deduped)}개")
        all_scouted.extend(deduped)

    # 카테고리 간 중복 제거
    before = len(all_scouted)
    all_scouted = _dedup(all_scouted)
    after = len(all_scouted)
    if before != after:
        print(f"    [크로스 dedup] {before}→{after}개")
    if after < 30:
        print(f"  [WARN] 총 {after}개 — 목표 30개 미달")

    return {"scouted_list": all_scouted}


def scan_news_from_file(filepath: str) -> dict:
    """파일에서 뉴스 데이터를 읽어 스캔한다."""
    with open(filepath, "r", encoding="utf-8") as f:
        raw_data = f.read()
    return scan_news(raw_data)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        result = scan_news_from_file(sys.argv[1])
    else:
        print("뉴스 데이터를 붙여넣으세요 (Ctrl+Z로 종료):")
        raw = sys.stdin.read()
        result = scan_news(raw)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\n총 {len(result.get('scouted_list', []))}개 이슈 엄선 완료.")
