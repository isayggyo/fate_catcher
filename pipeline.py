"""Fate Catcher 파이프라인: 뉴스 수집 → GPT 필터링 → 스코어링 → 결과 출력.

사용법:
    python pipeline.py                    # 국내 + 글로벌 전체 실행
    python pipeline.py --source domestic  # 국내(네이버+DART)만
    python pipeline.py --source global    # 글로벌(Finnhub+FMP+AlphaVantage)만
"""

import argparse
import json
from dotenv import load_dotenv

load_dotenv()

from fetchers import (
    fetch_naver_news,
    fetch_dart_disclosures,
    fetch_finnhub_news,
    fetch_fmp_news,
    fetch_alpha_vantage_news,
)
from news_scanner import scan_news
from scorer import score_scouted
from question_maker import make_questions

# ── 소스 그룹 정의 ──
DOMESTIC_SOURCES = [
    ("네이버 뉴스", fetch_naver_news),
    ("DART 공시", fetch_dart_disclosures),
]

GLOBAL_SOURCES = [
    ("Finnhub 마켓뉴스", fetch_finnhub_news),
    ("FMP 주식뉴스", fetch_fmp_news),
    ("Alpha Vantage 뉴스", fetch_alpha_vantage_news),
]


def _collect(sources: list, group_label: str) -> str:
    """소스 리스트에서 데이터를 수집하여 합친 텍스트를 반환한다."""
    parts = []
    for i, (label, fetcher) in enumerate(sources, 1):
        print(f"  [{i}/{len(sources)}] {label} 수집 중...")
        try:
            data = fetcher()
        except Exception as e:
            print(f"         → 실패: {e}")
            continue

        if data.startswith("[ERROR]") or data.startswith("[INFO]"):
            print(f"         → {data}")
            continue

        if data.strip():
            count = len(data.strip().split("\n"))
            print(f"         → {count}건 수집 완료")
            parts.append(f"=== {label} ===\n" + data)

    return "\n\n".join(parts)


def _run_pipeline(combined: str, label: str, domestic: bool = False) -> dict:
    """수집된 텍스트에 GPT Stage 1 + Stage 2를 적용한다."""
    if not combined.strip():
        print(f"[{label}] 수집된 데이터가 없습니다. 스킵.")
        return {"scouted_list": [], "survivors": []}

    print(f"[{label}] GPT-4o-mini Stage 1 분석 중... (총 {len(combined)}자)")
    result = scan_news(combined)

    scouted = result.get("scouted_list", [])
    if scouted:
        print(f"[{label}] Stage 2 스코어링 중... ({len(scouted)}개 항목)")
        survivors = score_scouted(scouted, domestic=domestic)
        print(f"         → {len(survivors)}개 생존 (7점 이상, 최소 7개)")
        result["survivors"] = survivors
    else:
        result["survivors"] = []

    return result


def run(source: str = "all") -> dict:
    """뉴스 수집 + GPT 필터링 파이프라인 실행.

    source: 'all' | 'domestic' | 'global'
    """
    domestic_result = {"scouted_list": [], "survivors": []}
    global_result = {"scouted_list": [], "survivors": []}

    # ── 국내 파이프라인 ──
    if source in ("all", "domestic"):
        print("=" * 50)
        print("📌 [국내 파이프라인] 네이버 뉴스 + DART 공시")
        print("=" * 50)
        domestic_text = _collect(DOMESTIC_SOURCES, "국내")
        domestic_result = _run_pipeline(domestic_text, "국내", domestic=True)

    # ── 글로벌 파이프라인 ──
    if source in ("all", "global"):
        print("=" * 50)
        print("🌐 [글로벌 파이프라인] Finnhub + FMP + Alpha Vantage")
        print("=" * 50)
        global_text = _collect(GLOBAL_SOURCES, "글로벌")
        global_result = _run_pipeline(global_text, "글로벌")

    # ── 결과 합산 ──
    all_survivors = (
        domestic_result.get("survivors", [])
        + global_result.get("survivors", [])
    )

    # ── Stage 3: Yes/No 질문 변환 ──
    questions = []
    if all_survivors:
        print("=" * 50)
        print("🎯 [Stage 3] Yes/No 질문 변환 중...")
        print("=" * 50)
        questions = make_questions(all_survivors)
        print(f"         → {len(questions)}개 질문 생성 완료")

    merged = {
        "domestic": domestic_result,
        "global": global_result,
        "scouted_list": (
            domestic_result.get("scouted_list", [])
            + global_result.get("scouted_list", [])
        ),
        "survivors": all_survivors,
        "questions": questions,
    }
    return merged


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fate Catcher 뉴스 파이프라인")
    parser.add_argument(
        "--source",
        choices=["all", "domestic", "global"],
        default="all",
        help="데이터 소스 그룹 선택 (기본: all)",
    )
    parser.add_argument(
        "--output", "-o",
        help="결과를 JSON 파일로 저장",
    )
    args = parser.parse_args()

    result = run(source=args.source)

    total_scouted = len(result["scouted_list"])
    survivors = result["survivors"]
    questions = result.get("questions", [])

    print("\n" + "=" * 50)
    print(f" {total_scouted}개 스캔 → {len(survivors)}개 생존 → {len(questions)}개 질문")
    print("=" * 50)

    if survivors:
        for i, s in enumerate(survivors, 1):
            print(f"  [{s['score']}] {s['headline']}")
        print("=" * 50)
    else:
        print("  생존자 없음")
        print("=" * 50)

    if questions:
        print("\n" + "=" * 50)
        print(" 🎲 내일의 베팅 질문")
        print("=" * 50)
        for i, q in enumerate(questions, 1):
            print(f"\n  Q{i}. {q['question']}")
            print(f"      🔴 {q['side_yes']}")
            print(f"      🔵 {q['side_no']}")
            print(f"      📏 판정: {q['resolution']}")
            print(f"      ⏰ 마감: {q['deadline']}")
        print("\n" + "=" * 50)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"결과 저장: {args.output}")

