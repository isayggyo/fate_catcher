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
아래 뉴스 데이터에서 [{cat['label']}] 카테고리에 해당하는 이슈를 찾아 아래 4대 생존 심사를 통과한 것만 남겨라.

## {cat['label']} 범위
{cat['desc']}

# THE FATE CATCHER PROTOCOL — 4대 생존 심사

## 1. No Date, No Quest (기한 없으면 버려라)
- "하반기", "연내", "추진 중", "전망이다", "기대된다" → 즉시 탈락
- 기사 본문에 '내일', '이번 주', 'X월 X일', '임박' 등 7일 이내에 결과가 확정되는 구체적 타임라인이 없으면 탈락
- 오늘은 2026년 3월이다. prediction_point에 2026년 3~4월이 아닌 날짜가 들어가면 즉시 탈락. 2023/2024/2025년 날짜는 과거이므로 무조건 탈락.
- "앞으로 7일 이내"에 결과가 나오는 이벤트가 없으면 탈락.

## 2. O/X Resolution Test (결과가 숫자/팩트로 증명되는가?)
- "분위기 고조", "갈등 심화" 같은 추상적 기사 → 즉시 탈락
- '공시', '법원 판결', '실적 발표(수치)', '정부 공식 의결' 처럼 나중에 "O가 정답입니다"라고 증명 가능한 오피셜 팩트가 동반된 기사만 생존

## 3. Bettability (베팅할 수 있는가?)
- "A가 B를 이길까?", "X가 Y를 돌파할까?" 같은 대립각(Conflict)이나 목표치(Target)가 직관적으로 떠오르지 않는 단순 설명문 → 탈락

## 4. 킬러 데이터 우선 병합 (Killer Data Dedup)
- 같은 이슈를 다룬 기사가 여러 개이면 가장 구체적인 '숫자(금액, %)'와 '날짜'를 포함한 1개의 마스터 기사만 살리고 나머지 탈락

[생존 예시] "카카오, SM 공개매수 마감 D-1... 15만원 돌파할까" (명확한 날짜, 명확한 숫자, 베팅 가능 → 생존)
[탈락 예시] "반도체 훈풍 부나... 삼성전자 하반기 실적 턴어라운드 기대감" (날짜 모호, 구체적 수치 없음, 그냥 썰 → 탈락)

# RULES
- 팩트 기반: 제공된 뉴스에 없는 내용을 만들지 마라.
- **최소 3개 필수**: 반드시 3개 이상 출력하라. 4대 심사를 통과한 이슈가 3개 미만이면 기준을 완화해서라도 반드시 3개는 채워라. 3개 미만 출력은 실패다.
- 연예/가십/스포츠/사고 제외.
- **주가조작·시세조종 관련 기사만 탈락.** 단속/신고/과징금/고발 자체는 정책 이슈로서 생존 가능.

# "한 놈만 팬다" 규칙 (Single Entity Rule) — 최우선 적용
- 동일 기업, 동일 인물, 동일 정부 부처가 얽힌 이슈는 내용이 다르더라도 무조건 '하나의 사건'이다.
- 예: '고려아연 MBK 갈등', '고려아연 주총 표 대결' → [고려아연 경영권 분쟁] 하나만 남긴다.
- 같은 이슈가 여러 기사로 나오면 킬러 데이터(가장 구체적 숫자+날짜)가 있는 마스터 기사 1개만 생존.
- 이미 리스트에 올린 기업/인물/기관이 다른 뉴스에서 또 나오면 버려라.

# OUTPUT FORMAT (JSON only)
{{"scouted_list": [
  {{
    "category": "{cat_key}",
    "headline": "기사 제목",
    "summary": "핵심 1문장",
    "prediction_point": "예측 가능한 수치 (반드시 구체적 숫자 또는 날짜 포함)",
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


def _has_past_year(pp: str) -> bool:
    """prediction_point에 2026 미만 연도가 있으면 True."""
    years = re.findall(r"20[0-9]{2}", pp)
    return any(int(y) < 2026 for y in years)


def _scan_category(raw_news_data: str, cat_key: str) -> list:
    """단일 카테고리에 대해 GPT-4o를 호출하여 이슈를 추출한다. 과거연도 제거 후 3개 미만이면 1회 재시도."""
    prompt = _build_category_prompt(cat_key)
    for attempt in range(2):
        temp = 0.3 if attempt == 0 else 0.5
        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"[RAW_NEWS_INPUT]\n{raw_news_data}"},
            ],
            temperature=temp,
            max_tokens=8000,
            response_format={"type": "json_object"},
        )
        result = json.loads(response.choices[0].message.content)
        items = result.get("scouted_list", [])
        for item in items:
            item["category"] = cat_key
        # 과거 연도 prediction_point 제거
        items = [x for x in items if not _has_past_year(x.get("prediction_point", ""))]
        if len(items) >= 3 or attempt == 1:
            return items
        print(f"    [{cat_key}] {len(items)}개 < 3개, 재시도...")
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

    # 카테고리 간 중복 제거 (카테고리별 최소 3개 보장)
    from collections import defaultdict
    by_cat = defaultdict(list)
    for item in all_scouted:
        by_cat[item.get("category", "?")].append(item)

    seen_urls = set()
    seen_entities = set()
    final = []
    from difflib import SequenceMatcher as SM

    for cat_key in CATEGORIES:
        cat_items = by_cat.get(cat_key, [])
        cat_added = 0
        for item in cat_items:
            url = item.get("source_url", "")
            headline = item.get("headline", "")
            if url and url in seen_urls:
                continue
            is_dup = any(SM(None, headline, k["headline"]).ratio() >= 0.75 for k in final)
            entities = _extract_entities(headline)
            entity_dup = entities and entities & seen_entities
            # 최소 3개 미달이면 중복이어도 포함
            if (is_dup or entity_dup) and cat_added >= 3:
                continue
            seen_urls.add(url)
            seen_entities.update(entities)
            final.append(item)
            cat_added += 1

    before = len(all_scouted)
    all_scouted = final
    after = len(all_scouted)
    if before != after:
        print(f"    [크로스 dedup] {before}→{after}개")
    if after < 10:
        print(f"  [WARN] 총 {after}개 - 10개 미만")

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
