"""
Fate Catcher — Logic Auditor
GPT 1회 호출 (Claim/Support 분리 + Fact 추출 + 수치 검증 + 인과 그래프)
+ 로컬 ko-sroberta 임베딩으로 순환 논리 판정
"""

import os, json, re
from openai import OpenAI
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

from auditor_schema import GPTAnalysis, LogicAuditReport, NumericalClaim, Conflict

# ── 설정 ──
OPENAI_MODEL = "gpt-4o-mini"
SIMILARITY_THRESHOLD = 0.9   # 이상이면 순환 논리
MIN_PREMISES = 2             # 미만이면 전제 실종

client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

# 로컬 임베딩 모델 (서버 시작 시 1회 로드)
_embed_model = None

def _get_embed_model():
    global _embed_model
    if _embed_model is None:
        _embed_model = SentenceTransformer("jhgan/ko-sroberta-multitask")
    return _embed_model


# ── Step 1: GPT 분석 ──

GPT_SYSTEM = """너는 CPA 출신 논리 감사관이다. 유저가 제출한 '근거(logic)'를 분석하라.

반드시 아래 JSON 스키마로만 응답하라. 다른 텍스트는 금지.

{
  "claim": "핵심 주장 1문장 요약",
  "support": "주장을 뒷받침하는 근거 부분 (원문에서 발췌/요약)",
  "premises": ["독립적 사실1", "독립적 사실2", ...],
  "numerical_claims": [
    {"value": "30%", "has_unit": true, "has_comparison": false, "plausible": true}
  ],
  "fact_nodes": [
    {"id": "F1", "statement": "사실 명제 원문 발췌", "direction": "increase"},
    {"id": "F2", "statement": "사실 명제 원문 발췌", "direction": "decrease"}
  ],
  "causal_edges": [
    {"from_id": "F1", "to_id": "F2", "relation": "A가 B를 야기함"}
  ],
  "conflicts": [
    {
      "node_a_id": "F1",
      "node_b_id": "F3",
      "conflict_type": "direction_reversal",
      "description": "F1은 증가를 주장하나 F3은 같은 지표의 감소를 전제함",
      "has_causal_bridge": false
    }
  ]
}

규칙:
- premises: '~때문에' 같은 연결어가 아니라, 독립적으로 검증 가능한 사실(Fact)만 카운트
- claim: 유저가 궁극적으로 말하고자 하는 결론
- support: claim을 뒷받침하기 위해 유저가 제시한 근거 원문
- numerical_claims: 텍스트 내 모든 수치(%,원,배,조,억 등)를 추출. 없으면 빈 배열.

④ 내부 모순 — 인과 그래프 구축:
- fact_nodes: 글에서 추출한 모든 사실 명제. 각 노드에 ID(F1,F2,...)와 방향성(increase/decrease/neutral)을 부여.
- causal_edges: 명제 사이의 인과 화살표. "A 때문에 B" 형태의 논리적 연결.
- conflicts: 그래프에서 발견된 충돌. 3가지 유형:
  - direction_reversal: 인과 체인을 따라갔을 때 수치/방향이 역행 (예: 매출↑인데 점유율↓, 설명 없음)
  - causal_contradiction: A→B와 A→¬B가 동시에 존재
  - missing_link: 두 명제가 충돌하지만 이를 연결하는 인과 화살표가 없음
- has_causal_bridge: 충돌을 해소하는 인과적 설명이 글 안에 존재하면 true
- 충돌이 없으면 conflicts는 빈 배열"""


def _gpt_analyze(logic: str) -> GPTAnalysis:
    """GPT 1회 호출로 Claim/Support/Facts/Numbers/CausalGraph 분석."""
    resp = client.chat.completions.create(
        model=OPENAI_MODEL,
        temperature=0,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": GPT_SYSTEM},
            {"role": "user", "content": logic},
        ],
    )
    raw = json.loads(resp.choices[0].message.content)
    return GPTAnalysis(**raw)


# ── Step 2: 로컬 코사인 유사도 ──

def _compute_similarity(claim: str, support: str) -> float:
    """ko-sroberta로 Claim↔Support 코사인 유사도 계산."""
    model = _get_embed_model()
    embeddings = model.encode([claim, support])
    sim = cosine_similarity([embeddings[0]], [embeddings[1]])[0][0]
    return round(float(sim), 4)


# ── Step 3: 최종 판정 ──

def audit(logic: str) -> LogicAuditReport:
    """메인 감사 함수. logic 텍스트를 받아 LogicAuditReport 반환."""

    # 1) GPT 분석
    analysis = _gpt_analyze(logic)

    # 2) 로컬 순환 논리 검사
    tautology_score = _compute_similarity(analysis.claim, analysis.support)
    is_circular = tautology_score >= SIMILARITY_THRESHOLD

    # 3) 전제 실종 검사
    premises_count = len(analysis.premises)
    has_explicit_premises = premises_count >= MIN_PREMISES

    # 4) 데이터 조작 검사
    unverified = [
        nc for nc in analysis.numerical_claims
        if not nc.plausible or (not nc.has_unit and not nc.has_comparison)
    ]
    contains_unverified = len(unverified) > 0

    # 5) 내부 모순 검사 — causal bridge 없는 그래프 충돌만 위반
    unresolved = [c for c in analysis.conflicts if not c.has_causal_bridge]
    has_contradictions = len(unresolved) > 0

    # 6) 최종 판결
    reasons = []
    if not has_explicit_premises:
        reasons.append(f"독립적 근거 {premises_count}개. 최소 {MIN_PREMISES}개 필요.")
    if is_circular:
        reasons.append(f"주장과 근거의 유사도 {tautology_score}. 순환 논리.")
    if contains_unverified:
        bad = [nc.value for nc in unverified]
        reasons.append(f"검증 불가 수치: {', '.join(bad)}")
    if has_contradictions:
        # 노드 ID→statement 매핑
        node_map = {n.id: n.statement for n in analysis.fact_nodes}
        for c in unresolved:
            a = node_map.get(c.node_a_id, c.node_a_id)
            b = node_map.get(c.node_b_id, c.node_b_id)
            reasons.append(f"내부 모순[{c.conflict_type}]: \"{a}\" ↔ \"{b}\" — {c.description}")

    is_rejected = len(reasons) > 0
    rejection_reason = " | ".join(reasons) if is_rejected else None

    return LogicAuditReport(
        has_explicit_premises=has_explicit_premises,
        premises_count=premises_count,
        is_circular=is_circular,
        tautology_score=tautology_score,
        contains_unverified_numbers=contains_unverified,
        numerical_claims=analysis.numerical_claims,
        has_contradictions=has_contradictions,
        fact_nodes=analysis.fact_nodes,
        causal_edges=analysis.causal_edges,
        conflicts=analysis.conflicts,
        is_rejected=is_rejected,
        rejection_reason=rejection_reason,
    )
