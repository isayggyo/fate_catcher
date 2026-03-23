from pydantic import BaseModel, Field
from typing import List, Optional


class NumericalClaim(BaseModel):
    """추출된 수치 데이터 하나."""
    value: str = Field(description="원문에서 추출한 수치 표현 (예: '30%', '1조원')")
    has_unit: bool = Field(description="단위가 명시되어 있는가")
    has_comparison: bool = Field(description="비교 대상이 존재하는가 (전년 대비, 평균 등)")
    plausible: bool = Field(description="재무/통계적으로 개연성이 있는 수치인가")


# ── ④ 내부 모순: 인과 그래프 기반 ──

class FactNode(BaseModel):
    """사실 명제 노드."""
    id: str = Field(description="노드 식별자 (F1, F2, ...)")
    statement: str = Field(description="사실 명제 원문 발췌")
    direction: Optional[str] = Field(default=None, description="수치 방향성 (increase/decrease/neutral)")


class CausalEdge(BaseModel):
    """인과 관계 화살표."""
    from_id: str = Field(description="원인 노드 ID")
    to_id: str = Field(description="결과 노드 ID")
    relation: str = Field(description="인과 관계 설명 (예: '금리 인상 → 소비 위축')")


class Conflict(BaseModel):
    """그래프에서 탐지된 충돌."""
    node_a_id: str = Field(description="충돌 노드 A ID")
    node_b_id: str = Field(description="충돌 노드 B ID")
    conflict_type: str = Field(description="direction_reversal | causal_contradiction | missing_link")
    description: str = Field(description="충돌 상세 설명")
    has_causal_bridge: bool = Field(description="글 내에서 이 충돌을 해소하는 인과적 설명이 존재하는가?")


class GPTAnalysis(BaseModel):
    """GPT 1회 호출로 받아오는 중간 분석 결과."""
    # ① 전제 실종
    claim: str = Field(description="핵심 주장 (1문장 요약)")
    support: str = Field(description="주장을 뒷받침하는 근거 부분 (원문 발췌/요약)")
    premises: List[str] = Field(description="식별된 독립적 사실(Fact) 리스트")

    # ③ 데이터 조작
    numerical_claims: List[NumericalClaim] = Field(default_factory=list)

    # ④ 내부 모순 — 인과 그래프
    fact_nodes: List[FactNode] = Field(default_factory=list)
    causal_edges: List[CausalEdge] = Field(default_factory=list)
    conflicts: List[Conflict] = Field(default_factory=list)


class LogicAuditReport(BaseModel):
    """최종 감사 보고서."""
    # 1. 전제의 실종
    has_explicit_premises: bool = Field(description="주장을 뒷받침하는 구체적인 근거/데이터가 존재하는가?")
    premises_count: int = Field(description="식별된 고유 근거의 개수")

    # 2. 순환 논리 (로컬 임베딩 코사인 유사도)
    is_circular: bool = Field(description="결론이 전제를 반복하는 순환 논리 구조인가?")
    tautology_score: float = Field(description="Claim↔Support 코사인 유사도 (0.0 ~ 1.0)")

    # 3. 데이터 조작
    contains_unverified_numbers: bool = Field(description="출처가 불분명하거나 비논리적인 수치가 포함되어 있는가?")
    numerical_claims: List[NumericalClaim] = Field(default_factory=list)

    # 4. 내부 모순 (인과 그래프)
    has_contradictions: bool = Field(description="글 내부에서 인과 그래프상 충돌이 존재하는가?")
    fact_nodes: List[FactNode] = Field(default_factory=list)
    causal_edges: List[CausalEdge] = Field(default_factory=list)
    conflicts: List[Conflict] = Field(default_factory=list)

    # 최종 판결
    is_rejected: bool = Field(description="기준 미달로 반려 여부")
    rejection_reason: Optional[str] = Field(default=None, description="반려 사유 (Cold & Dry 톤)")
