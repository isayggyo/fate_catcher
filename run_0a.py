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
print(json.dumps(events, ensure_ascii=False, indent=2))
print(f"\n총 {len(events)}개 이벤트")

# 결과 저장
with open("stage0a_result.json", "w", encoding="utf-8") as f:
    json.dump(events, f, ensure_ascii=False, indent=2)
print("결과 저장: stage0a_result.json")
