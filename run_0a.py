"""Stage 0 → A 단축 실행 스크립트.

사용법: python run_0a.py
"""
import sys
import io
import json
from dotenv import load_dotenv

load_dotenv()

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

from early_bird import run_early_bird
from stage_0 import fetch_stage0_news
from stage_a import run_stage_a

keywords = run_early_bird()
print(f"\nEarly Bird 키워드: {keywords}\n")

raw = fetch_stage0_news(extra_keywords=keywords)
print(f"Stage 0 수집: {len(raw.splitlines())}건\n")

events = run_stage_a(raw)

# 결과 저장
with open("stage0a_result.json", "w", encoding="utf-8") as f:
    json.dump(events, f, ensure_ascii=False, indent=2)

# 테이블 출력
header = f"{'ID':<14} {'subject':<16} {'conflict':<28} {'trigger':<20} {'deadline':<12} {'pivot'}"
sep = "-" * len(header)
print(f"\n{sep}")
print(header)
print(sep)
for e in events:
    dl = e.get("deadline", "")[:10]
    print(f"{e['id']:<14} {e['subject']:<16} {e['conflict']:<28} {e['trigger']:<20} {dl:<12} {e['pivot']}")
print(sep)
print(f"총 {len(events)}개 이벤트 | 결과 저장: stage0a_result.json")
