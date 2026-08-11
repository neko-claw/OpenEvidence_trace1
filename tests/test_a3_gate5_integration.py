from datetime import datetime, timezone

import pytest

from a3.domain.models import Evidence
from a3.indexing.chunking import ChunkPolicy, chunk_evidence
from a5.adapters.a3 import adapt_a3_selection
from a5.adapters.rule_based_claim_verifier import RuleBasedClaimVerifier
from a5.adapters.default_safety_policy import FixtureSafetyPolicy
from a5.adapters.mock_claim_generator import MockClaimGenerator
from a5.agent.workflow import A5Workflow
from a5.domain.enums import ClaimCriticality, MatchStatus, VerificationStatus
from a5.domain.models import Claim, Question, RetrievalResult, VerificationContext
from a5.runtime_config import load_runtime_config
from tests.a3_support import make_manifest


def record(**updates):
    data=dict(id="E1",source_type="trial",title="Mock",abstract_or_chunk="Exact synthetic outcome is stable.",
        population="synthetic adults",intervention="synthetic A",comparator="synthetic B",outcome="synthetic outcome",
        published_at=datetime(2025,1,1,tzinfo=timezone.utc),mock=True,provenance={"fixture":"gate5"})
    data.update(updates); e=Evidence(**data)
    policy=ChunkPolicy(version="test",max_chars=1200,overlap_chars=150,natural_boundary_ratio=.6)
    c,s=chunk_evidence(e,policy)
    manifest=make_manifest([e])
    return adapt_a3_selection(e,c,s,manifest,index_version=manifest.index_version,
        corpus_version=manifest.corpus_version).evidence


def claim(rec, **updates):
    data=dict(claim_id="C1",text="Exact synthetic outcome is stable",criticality=ClaimCriticality.CRITICAL,
        evidence_ids=[rec.id],evidence_span_ids=[rec.spans[0].span_id])
    data.update(updates); return Claim(**data)


def verify(c, records, fresh=False):
    return RuleBasedClaimVerifier().verify(c,records,VerificationContext(freshness_required=fresh,run_date=datetime(2026,1,1).date()))


def test_legal_span_exact_support_and_pico_match():
    r=record(); result=verify(claim(r,population="synthetic adults",intervention="synthetic A",
        comparator="synthetic B",outcome="synthetic outcome"),[r])
    assert result.citation_valid and result.span_check is MatchStatus.MATCH
    assert result.population_match is MatchStatus.MATCH and result.status is VerificationStatus.SUPPORTED


def test_illegal_evidence_and_illegal_span_fail_closed():
    r=record()
    bad_e=claim(r,evidence_ids=["OUTSIDE"]); a=verify(bad_e,[r])
    assert a.illegal_evidence_ids and not a.citation_valid and a.status is not VerificationStatus.SUPPORTED
    bad_s=claim(r,evidence_span_ids=["S-OUTSIDE"]); b=verify(bad_s,[r])
    assert b.span_check is MatchStatus.MISMATCH and b.status is not VerificationStatus.SUPPORTED


def test_missing_span_is_unknown_and_insufficient():
    r=record(); result=verify(claim(r,evidence_span_ids=[]),[r])
    assert result.span_check is MatchStatus.UNKNOWN and result.status is VerificationStatus.INSUFFICIENT


@pytest.mark.parametrize(("population","expected"),[("different",MatchStatus.MISMATCH),("synthetic adults",MatchStatus.MATCH)])
def test_pico_explicit_match_and_mismatch(population,expected):
    r=record(); result=verify(claim(r,population=population),[r])
    assert result.population_match is expected
    if expected is MatchStatus.MISMATCH: assert result.status is not VerificationStatus.SUPPORTED


def test_pico_missing_remains_unknown():
    r=record(population=None); result=verify(claim(r,population="synthetic adults"),[r])
    assert result.population_match is MatchStatus.UNKNOWN and result.status is not VerificationStatus.SUPPORTED


def test_time_match_mismatch_and_unknown():
    r=record(); assert verify(claim(r),[r],True).time_match is MatchStatus.MATCH
    future=record(published_at=datetime(2027,1,1,tzinfo=timezone.utc)); assert verify(claim(future),[future],True).time_match is MatchStatus.MISMATCH
    missing=record(published_at=None); assert verify(claim(missing),[missing],True).time_match is MatchStatus.UNKNOWN


def test_paraphrase_remains_insufficient():
    r=record(); result=verify(claim(r,text="A similar but non-exact semantic paraphrase"),[r])
    assert result.status is VerificationStatus.INSUFFICIENT


def test_adapter_diagnostics_reach_trace_and_unknown_score_cannot_pass_gate2():
    evidence=Evidence(id="E-TRACE",source_type="trial",title="Mock",
        abstract_or_chunk="Exact synthetic trace sentence.",mock=True,
        provenance={"fixture":"trace"})
    chunks,spans=chunk_evidence(evidence,ChunkPolicy(version="trace",max_chars=1200,
        overlap_chars=0,natural_boundary_ratio=.6)); manifest=make_manifest([evidence])
    adapted=adapt_a3_selection(evidence,chunks,spans,manifest,index_version=manifest.index_version,
        corpus_version=manifest.corpus_version)

    class A4SelectionFixtureRetriever:
        def retrieve(self, question, plan, request):
            del question,plan,request
            return RetrievalResult(evidence=[adapted.evidence],tool_name="a4-selection-fixture",
                diagnostics=adapted.diagnostics.model_dump(mode="json"))

    config=load_runtime_config(); workflow=A5Workflow(retriever=A4SelectionFixtureRetriever(),
        claim_generator=MockClaimGenerator(),claim_verifier=RuleBasedClaimVerifier(config.gates.gate5),
        safety_policy=FixtureSafetyPolicy(),runtime_config=config)
    run=workflow.answer(Question(text="Synthetic trace test.",metadata={"mock_safety_decision":"ALLOW"}))
    retrieve=next(event for event in run.trace if event.tool == "a4-selection-fixture")
    assert retrieve.details["diagnostics"]["a3_contract_version"] == "a3-compat-v0.3"
    assert retrieve.details["diagnostics"]["selected_span_ids"] == [spans[0].span_id]
    assert run.evidence_sufficiency.metrics.top_score is None
    assert run.decision.value == "REFUSE"
