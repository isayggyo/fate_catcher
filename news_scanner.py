import json
import os
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM_PROMPT = """# ROLE
너는 'Fate Catcher'의 데이터 전처리 전문가이자 뉴스 스캐너다.
수백 개의 뉴스 데이터 중에서 203040 남성 유저들이 열광할 만한 '예측 가능한' 이슈 15개를 엄선하라.

# FILTERING CRITERIA (필수 통과 조건)
1. Quantitative (수치화): 향후 특정 시점에 숫자(주가, 지표, 투표수)로 승패를 가릴 수 있는가?
2. High Stakes (자본주의적 가치): 돈, 자산, 커리어, 혹은 국가적 경쟁력과 직결된 이슈인가?
3. Conflict (논쟁성): 찬성과 반대 의견이 팽팽하게 대립할 여지가 있는가?

# EXCLUSION LIST (무조건 버릴 것)
- 연애/가십, 스포츠 경기 결과, 단순 사고/재해, 연예인 근황, 문화/예술 전시.
- "성공적일 것으로 보인다"와 같은 주관적이고 모호한 서술만 있는 뉴스.

# CATEGORIES
- TECH: AI 반도체, 대형 언어 모델(LLM), 빅테크 규제.
- FINANCE: 미국/한국 증시, 금리, 환율, 원자재.
- CRYPTO: 비트코인, 알트코인 정책, 온체인 변동성.
- MACRO: 부동산 정책, 글로벌 지정학(에너지/공급망), 세법 개정.

# OUTPUT FORMAT (JSON)
반드시 아래 JSON 형식으로만 응답하라. 다른 텍스트 없이 순수 JSON만 출력하라.
{
  "scouted_list": [
    {
      "category": "카테고리명",
      "headline": "기사 제목",
      "summary": "핵심 내용 1문장 요약",
      "prediction_point": "이 뉴스에서 어떤 수치를 예측할 수 있는지 기술",
      "source_url": "URL"
    }
  ]
}"""


def scan_news(raw_news_data: str) -> dict:
    """GPT-4o-mini로 뉴스 데이터를 필터링하여 예측 가능한 이슈 15개를 엄선한다."""
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"[RAW_NEWS_INPUT]\n{raw_news_data}"},
        ],
        temperature=0.3,
        response_format={"type": "json_object"},
    )

    result = json.loads(response.choices[0].message.content)
    return result


def scan_news_from_file(filepath: str) -> dict:
    """파일에서 뉴스 데이터를 읽어 스캔한다."""
    with open(filepath, "r", encoding="utf-8") as f:
        raw_data = f.read()
    return scan_news(raw_data)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        # 파일 경로가 주어진 경우
        result = scan_news_from_file(sys.argv[1])
    else:
        # stdin에서 읽기
        print("뉴스 데이터를 붙여넣으세요 (Ctrl+Z로 종료):")
        raw = sys.stdin.read()
        result = scan_news(raw)

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\n총 {len(result.get('scouted_list', []))}개 이슈 엄선 완료.")
