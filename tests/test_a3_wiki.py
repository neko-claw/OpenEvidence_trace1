from a3.domain.models import Evidence
from a3.indexing.chunking import CHUNK_POLICY_VERSION, ChunkPolicy, chunk_evidence
from a3.indexing.versions import create_manifest
from a3.wiki.builder import build_wiki
from a3.wiki.validation import validate_wiki


def test_two_deterministic_mock_pages_with_whitelisted_citations(tmp_path):
    evidence=[]; spans=[]
    for topic in ("hypertension","dyslipidemia"):
        e=Evidence(id=f"M-{topic}",source_type="review",title=f"{topic} mock",
            abstract_or_chunk="Exact synthetic fixture sentence.",mock=True,provenance={"topic":topic})
        evidence.append(e); spans.extend(chunk_evidence(e)[1])
    manifest=create_manifest(evidence=evidence,chunk_policy_version=CHUNK_POLICY_VERSION,
        chunk_policy=ChunkPolicy().as_dict(),embedding_provider="fake",embedding_model="fake")
    paths=build_wiki(tmp_path,evidence,spans,manifest)
    first=[p.read_text(encoding="utf-8") for p in paths]
    paths=build_wiki(tmp_path,evidence,spans,manifest)
    assert len(paths)==2 and first==[p.read_text(encoding="utf-8") for p in paths]
    assert all("MOCK / OFFLINE FIXTURE" in text and "[Evidence:" in text and "[Span:" in text for text in first)


def test_validator_rejects_unknown_and_wiki_fact_citations():
    try:
        validate_wiki("x [Evidence: BAD]", {"OK"}, set())
    except ValueError:
        pass
    else:
        raise AssertionError("unknown ID accepted")
    try:
        validate_wiki("x [Wiki: other]", set(), set())
    except ValueError:
        pass
    else:
        raise AssertionError("Wiki fact citation accepted")
