from __future__ import annotations

from pathlib import Path

from a1.adapters import A1SafetyPolicyAdapter
from a2.mcp.client import A2MCPClient
from a2.mcp.server import build_mcp_server, build_service as build_a2_service
from a5.adapters.openai_compatible_claim_generator import OpenAICompatibleClaimGenerator
from a5.adapters.rule_based_claim_verifier import (
    ExactSpanTextualSupportEvaluator,
    RuleBasedClaimVerifier,
)
from a5.adapters.semantic_claim_verifier import (
    CompositeTextualSupportEvaluator,
    OpenAICompatibleSemanticEvaluator,
)
from a5.agent.workflow import A5Workflow
from a5.facade import BackendDependencies
from a5.gates.evidence_integrity import EvidenceIntegrityGate
from a5.gates.research_sufficiency import ResearchEvidenceSufficiencyGate
from a5.generation.research_finalizer import ResearchAnswerFinalizer
from a5.runtime_config import load_runtime_config
from backend.extractive_claims import ExtractiveClaimGenerator, PreAtomicClaimSplitter
from backend.hashing_embedding import HashingEmbeddingProvider
from backend.local_claim_presenter import LocalVerifiedClaimPresenter
from backend.research_planner import PublicEvidenceResearchSkill
from backend.research_profile import ResearchProfile, load_research_profile
from backend.research_safety import ConservativeResearchSafetyClassifier
from backend.retriever import CoordinatedEvidenceRetriever
from backend.source import A2EvidenceSource
from backend.structured_transport import OllamaStructuredTransport
from retrieval.config_io import load_config_yaml


ROOT = Path(__file__).resolve().parents[2]


def build_research_dependencies(
    profile: ResearchProfile | None = None,
) -> BackendDependencies:
    """Compose the real public-source research experience.

    The profile is intentionally distinct from clinically approved ``live``.
    It uses real public Evidence and all A5 gates, but the local hashing vector
    and development thresholds are recorded honestly in the run snapshot.
    """

    profile = profile or load_research_profile()
    runtime = load_runtime_config()
    a2_client = A2MCPClient(build_mcp_server(build_a2_service()))
    retriever = CoordinatedEvidenceRetriever(
        A2EvidenceSource(a2_client),
        HashingEmbeddingProvider(),
        index_root=ROOT / "data" / "research" / "indexes",
        retrieval_config=load_config_yaml(ROOT / "config" / "retrieval-p0-v1.yaml"),
    )
    transport = OllamaStructuredTransport(
        profile.models.ollama_base_url,
        timeout_seconds=profile.models.request_timeout_seconds,
    )
    if transport.available(profile.models.generation_model):
        generator = OpenAICompatibleClaimGenerator(
            transport=transport,
            model=profile.models.generation_model,
            prompt_path=ROOT / "prompts" / "claim_generation_v0.4.0.md",
        )
        semantic = OpenAICompatibleSemanticEvaluator(
            transport=transport,
            model=profile.models.verification_model,
            prompt_path=ROOT / "prompts" / "semantic_verification_v0.4.0.md",
            name=f"ollama_semantic_verifier:{profile.models.verification_model}",
        )
        support = CompositeTextualSupportEvaluator(
            ExactSpanTextualSupportEvaluator(), semantic
        )
        claim_splitter = None
        generation_mode = "structured_model"
    else:
        generator = ExtractiveClaimGenerator(
            max_claims=profile.generation.max_claims,
            min_chars=profile.generation.min_span_chars,
            max_chars=profile.generation.max_span_chars,
        )
        support = ExactSpanTextualSupportEvaluator()
        claim_splitter = PreAtomicClaimSplitter()
        generation_mode = "exact_span_extractive"
    presenter = None
    if profile.models.enable_local_answer_presentation:
        configured_path = Path(profile.models.answer_presentation_model_path)
        model_path = configured_path if configured_path.is_absolute() else ROOT / configured_path
        candidate = LocalVerifiedClaimPresenter(
            model_path,
            ROOT / "prompts" / "verified_claim_presentation_v0.1.0.md",
        )
        presenter = candidate if candidate.available else None
    workflow = A5Workflow(
        retriever=retriever,
        claim_generator=generator,
        claim_verifier=RuleBasedClaimVerifier(runtime.gates.gate5, textual_support=support),
        safety_policy=A1SafetyPolicyAdapter(
            classifier=ConservativeResearchSafetyClassifier()
        ),
        evidence_integrity=EvidenceIntegrityGate(runtime.gates.gate1),
        research_skill=PublicEvidenceResearchSkill(runtime),
        claim_splitter=claim_splitter,
        sufficiency_gate=ResearchEvidenceSufficiencyGate(profile.retrieval),
        finalizer=ResearchAnswerFinalizer(presenter=presenter),
        runtime_snapshot_extension={
            "research_profile": profile.model_dump(mode="json"),
            "effective_generation_mode": generation_mode,
            "embedding_provider": "hashing-candidate-recall-v0.1.0",
            "ranking_semantics": "query_local_not_calibrated_quality",
            "answer_presentation": {
                "enabled": presenter is not None,
                "model": profile.models.answer_presentation_model,
                "presenter_version": (
                    presenter.version if presenter is not None else None
                ),
                "prompt_version": "0.1.0",
                "trust_boundary": "post_gate5_presentation_only",
            },
        },
        runtime_config=runtime,
    )
    return BackendDependencies(workflow=workflow)
