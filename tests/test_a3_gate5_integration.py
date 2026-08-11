from datetime import datetime, timezone

import pytest

from a3.domain.models import Evidence
from a3.indexing.chunking import chunk_evidence
from a5.adapters.a3_evidence_adapter import adapt_a3_evidence
from a5.adapters.rule_based_claim_verifier import RuleBasedClaimVerifier
from a5.domain.enums import ClaimCriticality, MatchStatus, VerificationStatus
from a5.domain.models import Claim, VerificationContext


def record(**updates):
    data=dict(id="E1",source_type="trial",title="Mock",abstract_or_chunk="Exact synthetic outcome is stable.",
        population="synthetic adults",intervention="synthetic A",comparator="synthetic B",outcome="synthetic outcome",
        published_at=datetime(2025,1,1,tzinfo=timezone.utc),mock=True)
    data.update(updates); e=Evidence(**data); c,s=chunk_evidence(e)
    return adapt_a3_evidence(e,c,s,index_version="i",corpus_version="c")


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
