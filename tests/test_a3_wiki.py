import pytest
from datetime import datetime, timezone

from a3.config import WikiTopicConfig
from a3.domain.models import Evidence
from a3.indexing.chunking import ChunkPolicy, chunk_evidence
from a3.indexing.versions import create_manifest
from a3.wiki.builder import DeterministicOfflineWikiGenerator, build_wiki
from a3.wiki.generator import WikiPage
from a3.wiki.validation import validate_wiki_pages

POLICY = ChunkPolicy(version="test", max_chars=1200, overlap_chars=150, natural_boundary_ratio=.6)
TOPICS = [WikiTopicConfig(slug="hypertension", title="Hypertension", synonyms=["high blood pressure"], mesh=["Hypertension"]),
          WikiTopicConfig(slug="dyslipidemia", title="Dyslipidemia", synonyms=["lipid disorder"], mesh=["Dyslipidemias"])]


def _manifest(evidence):
    manifest = create_manifest(evidence=evidence, chunk_policy_version=POLICY.version,
        chunk_policy=POLICY.as_dict(), embedding_provider="offline-smoke", embedding_model="fake",
        embedding_revision="fixture", embedding_mode="dense", vector_distance="cosine",
        bm25_tokenizer_version="tok", wiki_builder_version="wiki-v1",
        config_schema_version="config-v1", effective_config={"corpus_cutoff": "2026-01-01",
        "wiki": {"topics": [x.model_dump() for x in TOPICS]}})
    # Pin the build timestamp so repeated builds are byte-identical.
    manifest.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return manifest


def test_index_and_deterministic_mock_pages_with_whitelisted_citations(tmp_path):
    evidence=[]; spans=[]
    for topic in ("hypertension", "dyslipidemia"):
        item=Evidence(id=f"M-{topic}", source_type="review", title=f"{topic} mock",
            abstract_or_chunk="Exact synthetic fixture sentence.", mock=True, provenance={"topic":topic})
        evidence.append(item); spans.extend(chunk_evidence(item, POLICY)[1])
    manifest=_manifest(evidence); generator=DeterministicOfflineWikiGenerator("wiki-v1")
    paths, lexical = build_wiki(tmp_path, evidence, spans, manifest, TOPICS, generator)
    first=[path.read_text(encoding="utf-8") for path in paths]
    paths, lexical2 = build_wiki(tmp_path, evidence, spans, manifest, TOPICS, generator)
    assert [path.name for path in paths] == ["_index.md", "hypertension.md", "dyslipidemia.md"]
    assert first == [path.read_text(encoding="utf-8") for path in paths]
    assert all("MOCK / OFFLINE FIXTURE — NOT MEDICAL EVIDENCE" in text for text in first)
    assert all("[Evidence:" in text and "[Span:" in text for text in first[1:])
    assert lexical == lexical2 and "high blood pressure" in lexical[0].text
    # 5.3 fixed structure: provenance must carry updated-at and data-cutoff fields.
    assert all("- updated at: `2026-01-01T00:00:00+00:00`" in text for text in first)
    assert all("- data cutoff: `2026-01-01`" in text for text in first)


def test_validator_allows_dag_but_rejects_unknown_duplicate_and_cycle():
    evidence = [Evidence(id="OK", source_type="review", title="Mock", abstract_or_chunk="Exact.", mock=True)]
    span = chunk_evidence(evidence[0], POLICY)[1][0]
    pages = [WikiPage(slug="a", title="A", content=f"[B](b.md) [Evidence: OK] [Span: {span.span_id}]"),
             WikiPage(slug="b", title="B", content="end")]
    assert validate_wiki_pages(pages, evidence, [span]) == {"a": {"b"}, "b": set()}
    with pytest.raises(ValueError, match="outside current corpus"):
        validate_wiki_pages([WikiPage(slug="a", title="A", content="[Evidence: BAD]")], evidence, [span])
    with pytest.raises(ValueError, match="duplicate Wiki link"):
        validate_wiki_pages([WikiPage(slug="a", title="A", content="[B](b.md) [again](b.md)"),
            WikiPage(slug="b", title="B", content="end")], evidence, [span])
    with pytest.raises(ValueError, match="cyclic"):
        validate_wiki_pages([WikiPage(slug="a", title="A", content="[B](b.md)"),
            WikiPage(slug="b", title="B", content="[A](a.md)")], evidence, [span])


def test_offline_generator_refuses_non_mock_evidence():
    evidence = [Evidence(id="REAL", source_type="review", title="Not fixture", abstract_or_chunk="Text")]
    with pytest.raises(RuntimeError, match="mock evidence only"):
        DeterministicOfflineWikiGenerator("wiki-v1").generate(
            evidence=evidence, spans=[], manifest=_manifest(evidence), topics=TOPICS)
