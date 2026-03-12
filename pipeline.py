"""Fate Catcher 파이프라인: 뉴스 수집 → GPT 필터링 → 결과 출력.

사용법:
    python pipeline.py                  # 네이버 + DART 전체 실행
    python pipeline.py --source naver   # 네이버 뉴스만
    python pipeline.py --source dart    # DART 공시만
"""

import argparse
import json
from dotenv import load_dotenv

load_dotenv()

from fetchers import fetch_naver_news, fetch_dart_disclosures
from news_scanner import scan_news


def run(source: str = "all") -> dict:
    """뉴스 수집 + GPT 필터링 파이프라인 실행."""
    raw_parts = []

    if source in ("all", "naver"):
        print("[1/3] 네이버 뉴스 수집 중...")
        naver_data = fetch_naver_news()
        count = len(naver_data.strip().split("\n")) if naver_data.strip() else 0
        print(f"      → {count}건 수집 완료")
        if naver_data.strip():
            raw_parts.append("=== 네이버 뉴스 ===\n" + naver_data)

    if source in ("all", "dart"):
        print("[2/3] DART 공시 수집 중...")
        dart_data = fetch_dart_disclosures()
        if dart_data.startswith("[ERROR]") or dart_data.startswith("[INFO]"):
            print(f"      → {dart_data}")
        else:
            count = len(dart_data.strip().split("\n"))
            print(f"      → {count}건 수집 완료")
            raw_parts.append("=== DART 공시 ===\n" + dart_data)

    if not raw_parts:
        print("[ERROR] 수집된 데이터가 없습니다.")
        return {"scouted_list": []}

    combined = "\n\n".join(raw_parts)

    print(f"[3/3] GPT-4o-mini 분석 중... (총 {len(combined)}자)")
    result = scan_news(combined)

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fate Catcher 뉴스 파이프라인")
    parser.add_argument(
        "--source",
        choices=["all", "naver", "dart"],
        default="all",
        help="데이터 소스 선택 (기본: all)",
    )
    parser.add_argument(
        "--output", "-o",
        help="결과를 JSON 파일로 저장",
    )
    args = parser.parse_args()

    result = run(source=args.source)

    print("\n" + "=" * 50)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print(f"\n총 {len(result.get('scouted_list', []))}개 이슈 엄선 완료.")

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"결과 저장: {args.output}")
