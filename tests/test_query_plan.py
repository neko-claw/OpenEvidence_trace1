"""Tests for rule-based query understanding (4.2 query parsing)."""

from __future__ import annotations

import pytest

from retrieval.query_plan import parse_query


def test_parse_query_identifies_domain_question_type_and_freshness() -> None:
    plan = parse_query("q1", "最新高血压临床试验有哪些？")

    assert plan.domain == "hypertension"
    assert plan.question_type == "latest_trial"
    assert plan.freshness == "latest"


def test_parse_query_identifies_guideline_question() -> None:
    plan = parse_query("q2", "老年高血压患者的一线降压指南推荐是什么？")

    assert plan.question_type == "guideline"
    assert plan.freshness == "current"


def test_parse_query_identifies_therapy_question_and_english_terms() -> None:
    plan = parse_query("q3", "氨氯地平治疗高血压的疗效如何？")

    assert plan.question_type == "therapy"
    assert "amlodipine" in plan.queries_en
    assert "hypertension" in plan.queries_en
    assert plan.queries_zh[0] == "氨氯地平治疗高血压的疗效如何？"  # original preserved


def test_parse_query_extracts_pico_slots() -> None:
    plan = parse_query("q4", "老年高血压患者使用氨氯地平对比安慰剂的血压下降情况")

    assert plan.pico_population
    assert "older adults" in " ".join(plan.pico_population) or "老年" in " ".join(plan.pico_population)
    assert plan.pico_intervention
    assert plan.pico_comparator
    assert plan.pico_outcome


def test_parse_query_splits_atomic_claims() -> None:
    plan = parse_query("q5", "指南推荐老年患者使用氨氯地平；他汀可降低 LDL。最新试验显示血压下降。")

    assert len(plan.atomic_claims) >= 2
    assert all(isinstance(claim, str) and claim.strip() for claim in plan.atomic_claims)


def test_parse_query_marks_out_of_scope_questions() -> None:
    plan = parse_query("q6", "帮我算一下我应该吃多少毫克氨氯地平")

    assert plan.out_of_scope is True


def test_parse_query_does_not_mark_normal_questions_out_of_scope() -> None:
    plan = parse_query("q7", "高血压的流行病学证据")

    assert plan.out_of_scope is False


def test_parse_query_unknown_domain_is_generic() -> None:
    plan = parse_query("q8", "糖尿病的治疗指南")

    assert plan.domain == "generic" or plan.domain == "diabetes"


def test_parse_query_builds_query_object_with_claims() -> None:
    plan = parse_query("q9", "老年高血压的一线降压治疗；最新试验")

    query = plan.to_query()

    assert query.query_id == "q9"
    assert query.text == "老年高血压的一线降压治疗；最新试验"
    assert query.domain == "hypertension"
    assert query.atomic_claims
    assert query.question_type in {"therapy", "latest_trial"}


def test_parse_query_requires_nonblank_text() -> None:
    with pytest.raises(ValueError, match="text"):
        parse_query("q10", "   ")
