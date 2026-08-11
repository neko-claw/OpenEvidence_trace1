"""Rule-based query understanding for A4 (4.2 查询理解).

``parse_query`` turns a raw clinical question into a ``QueryPlan``: domain,
question type, freshness, PICO slots, atomic claims, and bilingual search
terms.  It is deliberately deterministic and LLM-free in P0; the original
question text is always preserved.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from .models import Query

# (zh terms, en terms) per domain
_DOMAINS: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    ("hypertension", ("高血压", "降压", "血压"), ("hypertension", "blood pressure", "antihypertensive")),
    ("lipid", ("血脂", "胆固醇", "他汀", "脂质"), ("lipid", "cholesterol", "statin", "dyslipidemia")),
    ("diabetes", ("糖尿病", "血糖"), ("diabetes", "glycemic", "glucose")),
)

# (slot, [(zh, en), ...]) — aliases for PICO slot extraction
_PICO_TERMS: dict[str, tuple[tuple[str, str], ...]] = {
    "population": (
        ("老年", "older adults"),
        ("成人", "adults"),
        ("妊娠", "pregnant"),
        ("儿童", "children"),
        ("糖尿病", "diabetes"),
    ),
    "intervention": (
        ("氨氯地平", "amlodipine"),
        ("他汀", "statin"),
        ("ACEI", "acei"),
        ("噻嗪", "thiazide"),
        ("依折麦布", "ezetimibe"),
    ),
    "comparator": (
        ("安慰剂", "placebo"),
        ("对照", "control"),
    ),
    "outcome": (
        ("血压", "blood pressure"),
        ("死亡率", "mortality"),
        ("心血管", "cardiovascular"),
        ("LDL", "ldl"),
        ("不良事件", "adverse events"),
        ("血糖", "glucose"),
    ),
}

_GUIDELINE_TERMS = ("指南", "推荐", "guideline", "guidelines", "recommendation")
_TRIAL_TERMS = ("试验", "随机", "trial", "rct", "randomized")
_LATEST_TERMS = ("最新", "近期", "当前", "新近", "latest", "recent", "current", "newest")
_THERAPY_TERMS = ("治疗", "疗法", "干预", "药物", "用药", "疗效", "treatment", "therapy", "drug")
_MECHANISM_TERMS = ("机制", "危险因素", "病理", "mechanism", "risk factor")
_OUT_OF_SCOPE_TERMS = (
    "剂量", "处方", "诊断我", "我的病", "开药", "服用多少", "吃多少", "毫克",
    "dose", "prescription", "diagnose me",
)

_SENTENCE_SPLIT = re.compile(r"[。；;！？!?\n]+")
_CLAUSE_SPLIT = re.compile(r"[，,、]")
_TOKEN = re.compile(r"\w+", re.UNICODE)


@dataclass(frozen=True)
class QueryPlan:
    """Structured interpretation of one clinical question."""

    query_id: str
    original_text: str
    domain: str = "generic"
    question_type: str = "generic"
    freshness: str = "generic"
    pico_population: tuple[str, ...] = ()
    pico_intervention: tuple[str, ...] = ()
    pico_comparator: tuple[str, ...] = ()
    pico_outcome: tuple[str, ...] = ()
    atomic_claims: tuple[str, ...] = ()
    queries_zh: tuple[str, ...] = ()
    queries_en: tuple[str, ...] = ()
    out_of_scope: bool = False

    def to_query(self) -> Query:
        """Build the immutable service Query consumed by ``RetrievalService``."""
        return Query(
            query_id=self.query_id,
            text=self.original_text,
            language="zh",
            pico_population=self.pico_population,
            pico_intervention=self.pico_intervention,
            pico_comparator=self.pico_comparator,
            pico_outcome=self.pico_outcome,
            topic="therapy" if self.question_type in {"therapy", "latest_trial"} else "generic",
            question_type=self.question_type,
            freshness=self.freshness,
            english_terms=self.queries_en,
            atomic_claims=self.atomic_claims,
            domain=self.domain,
        )


def parse_query(query_id: str, text: str) -> QueryPlan:
    """Parse one question into a deterministic QueryPlan (no LLM)."""
    if not isinstance(query_id, str) or not query_id.strip():
        raise ValueError("query_id must be a nonblank string")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("text must be a nonblank string")
    normalized = text.strip()
    lowered = normalized.casefold()

    domain = _detect_domain(lowered)
    question_type = _detect_question_type(lowered)
    freshness = _detect_freshness(lowered)
    out_of_scope = _detect_out_of_scope(lowered)
    pico = _extract_pico(lowered)
    claims = _split_claims(normalized)
    queries_zh = (normalized,)
    queries_en = _build_english_terms(lowered, domain)

    return QueryPlan(
        query_id=query_id,
        original_text=normalized,
        domain=domain,
        question_type=question_type,
        freshness=freshness,
        pico_population=pico["population"],
        pico_intervention=pico["intervention"],
        pico_comparator=pico["comparator"],
        pico_outcome=pico["outcome"],
        atomic_claims=claims,
        queries_zh=queries_zh,
        queries_en=queries_en,
        out_of_scope=out_of_scope,
    )


def _detect_domain(text: str) -> str:
    for name, zh_terms, en_terms in _DOMAINS:
        if any(term in text for term in zh_terms) or any(term in text for term in en_terms):
            return name
    return "generic"


def _detect_question_type(text: str) -> str:
    if any(term in text for term in _GUIDELINE_TERMS):
        return "guideline"
    latest = any(term in text for term in _LATEST_TERMS)
    trial = any(term in text for term in _TRIAL_TERMS)
    if latest and trial:
        return "latest_trial"
    if any(term in text for term in _THERAPY_TERMS):
        return "therapy"
    if any(term in text for term in _MECHANISM_TERMS):
        return "generic"  # mechanism maps to the generic evidence mapping in P0
    return "generic"


def _detect_freshness(text: str) -> str:
    if any(term in text for term in _GUIDELINE_TERMS):
        return "current"
    if any(term in text for term in _TRIAL_TERMS) and any(term in text for term in _LATEST_TERMS):
        return "latest"
    if any(term in text for term in _LATEST_TERMS):
        return "current"
    return "generic"


def _detect_out_of_scope(text: str) -> bool:
    return any(term in text for term in _OUT_OF_SCOPE_TERMS)


def _extract_pico(text: str) -> dict[str, tuple[str, ...]]:
    extracted: dict[str, list[str]] = {"population": [], "intervention": [], "comparator": [], "outcome": []}
    for slot, aliases in _PICO_TERMS.items():
        for zh_term, en_term in aliases:
            if zh_term in text or en_term in text:
                extracted[slot].append(en_term)
    return {slot: tuple(values) for slot, values in extracted.items()}


def _split_claims(text: str) -> tuple[str, ...]:
    sentences = [part.strip() for part in _SENTENCE_SPLIT.split(text) if part.strip()]
    if len(sentences) >= 2:
        return tuple(sentences[:5])
    # Single sentence: split into clauses on comma/和/与 separators.
    clauses = [part.strip() for part in _CLAUSE_SPLIT.split(sentences[0]) if part.strip()]
    clauses = [part for part in clauses if part]
    return tuple(clauses[:5]) if clauses else (sentences[0],)


def _build_english_terms(text: str, domain: str) -> tuple[str, ...]:
    terms: list[str] = []
    for name, zh_terms, en_terms in _DOMAINS:
        if name == domain and domain != "generic":
            terms.extend(en_terms)
    for slot_aliases in _PICO_TERMS.values():
        for zh_term, en_term in slot_aliases:
            if zh_term in text or en_term in text:
                terms.append(en_term)
    return tuple(dict.fromkeys(terms))[:8]
