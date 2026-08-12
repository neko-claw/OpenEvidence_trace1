from __future__ import annotations

import re
from collections.abc import Sequence

from a5.domain.enums import ClaimCriticality, UncertaintyLevel
from a5.domain.models import AgentPlan, Claim, EvidenceRecord, EvidenceSpan, Question


class ExtractiveClaimGenerator:
    """Fail-closed no-model fallback that publishes only exact source spans."""

    _external_reference = re.compile(
        r"(?:https?://|www\.|\bPMID\s*:?\s*\d+\b|\bNCT\d{8}\b|\b10\.\d{4,9}/\S+)",
        re.I,
    )
    _html_tag = re.compile(r"<[^>]+>")
    _sentence_boundary = re.compile(r"(?<=[.!?。！？])\s+")
    _heading = re.compile(
        r"^(?:background|objective|objectives|methods?|results?|conclusions?|discussion)\s*:?\s*",
        re.I,
    )

    def __init__(self, *, max_claims: int = 4, min_chars: int = 45, max_chars: int = 520) -> None:
        self.max_claims = max_claims
        self.min_chars = min_chars
        self.max_chars = max_chars

    def generate(
        self,
        question: Question,
        evidence: Sequence[EvidenceRecord],
        plan: AgentPlan,
        run_id: str,
    ) -> list[Claim]:
        query_text = " ".join(plan.search_plan.queries).casefold()
        query_tokens = set(re.findall(r"[a-z0-9]+", query_text))
        focus_terms = {
            term
            for term in ("statin", "ezetimibe", "pcsk9", "obicetrapib")
            if term in query_text
        }
        focus_groups = [
            *self._required_focus_groups(question.text),
            *self._required_intervention_groups(question.text),
        ]
        ranked: list[tuple[float, EvidenceRecord, EvidenceSpan, str]] = []
        for record in evidence:
            ranking = record.source_metadata.get("ranking_score")
            base = float(ranking) if isinstance(ranking, (int, float)) else 0.0
            for span in record.spans:
                for text in self._sentences(span.text):
                    if not self.min_chars <= len(text) <= self.max_chars:
                        continue
                    if self._is_non_answer_sentence(text):
                        continue
                    if self._external_reference.search(text):
                        continue
                    tokens = set(re.findall(r"[a-z0-9]+", text.casefold()))
                    context_tokens = tokens | set(
                        re.findall(r"[a-z0-9]+", record.title.casefold())
                    )
                    if focus_terms and not focus_terms.intersection(context_tokens):
                        continue
                    if focus_groups and not all(
                        group.intersection(context_tokens) for group in focus_groups
                    ):
                        continue
                    if not self._answers_intent(plan.question_type, text):
                        continue
                    overlap = len(tokens & query_tokens) / max(1, len(query_tokens))
                    # Prefer conclusion-like, quantitative sentences without
                    # inventing a semantic probability.
                    quantitative = 0.12 if re.search(r"\b\d+(?:\.\d+)?\b", text) else 0.0
                    answer_like = 0.18 if re.search(
                        r"\b(?:recommend|target|associated|reduced|increased|should|advised)\b",
                        text,
                        re.I,
                    ) else 0.0
                    background_like = 0.42 if re.search(
                        r"(?:^|\b)(?:aim|purpose|we evaluated|we investigated|we examined|to evaluate|aimed to|objective was|methods?|eligible rcts|systematic search)\b",
                        text,
                        re.I,
                    ) else 0.0
                    conclusion_like = 0.24 if re.search(
                        r"\b(?:we found|resulted|was associated|significantly|conclusion|demonstrated|achieved|compared with)\b",
                        text,
                        re.I,
                    ) else 0.0
                    intent_bonus = self._intent_bonus(plan.question_type, text)
                    ranked.append(
                        (
                            base + overlap + quantitative + answer_like + intent_bonus
                            + conclusion_like - background_like,
                            record,
                            span,
                            text,
                        )
                    )
        ranked.sort(key=lambda item: item[0], reverse=True)
        claims: list[Claim] = []
        seen_evidence: set[str] = set()
        for _, record, span, text in ranked:
            if record.id in seen_evidence and len(seen_evidence) < 2:
                continue
            seen_evidence.add(record.id)
            claims.append(
                Claim(
                    claim_id=f"C{len(claims) + 1}",
                    run_id=run_id,
                    text=text,
                    criticality=(ClaimCriticality.CRITICAL if not claims else ClaimCriticality.IMPORTANT),
                    evidence_ids=[record.id],
                    evidence_span_ids=[span.span_id],
                    uncertainty=UncertaintyLevel.LOW,
                )
            )
            if len(claims) >= self.max_claims:
                break
        return claims

    def _sentences(self, raw_text: str) -> list[str]:
        clean = self._html_tag.sub(" ", raw_text)
        clean = " ".join(clean.split()).strip(" -")
        return [
            self._heading.sub("", part).strip(" -")
            for part in self._sentence_boundary.split(clean)
            if self._heading.sub("", part).strip(" -")
        ]

    @staticmethod
    def _is_non_answer_sentence(text: str) -> bool:
        if text.rstrip().endswith((";", ":", ",")):
            return True
        return bool(
            re.search(
                r"^(?:aim|purpose|objective|methods?|to (?:systematically )?evaluate|"
                r"we (?:evaluated|investigated|examined|compared)|eligible rcts|"
                r"this (?:systematic review|review|study|analysis).{0,80}\b(?:aimed|aims)\b|"
                r"a (?:systematic search|random-effects meta-analysis))\b",
                text,
                re.I,
            )
        )

    @staticmethod
    def _answers_intent(question_type: str, text: str) -> bool:
        """Require an answer-bearing assertion, not mere topic overlap.

        Exact-span support proves that a sentence occurs in a source. It does
        not prove that the sentence answers the user's question. These narrow,
        auditable rules form a fail-closed relevance gate for the no-model
        fallback. A future semantic answer-relevance evaluator can replace this
        adapter without changing the A5 workflow.
        """

        patterns = {
            "guideline_treatment": (
                r"\b(?:recommend(?:ed|s)?|should|target|goal|advis(?:e|ed)|"
                r"indicat(?:e|ed|ion)|contraindicat(?:e|ed|ion)|mm\s*hg|mg/dl)\b"
            ),
            "latest_research_trial": (
                r"\b(?:result(?:s|ed)?|significant(?:ly)?|associated with|"
                r"reduced|increased|lower|higher|improved|difference|"
                r"hazard ratio|risk ratio|odds ratio|confidence interval|"
                r"primary outcome|secondary outcome)\b"
            ),
            "comparative_effectiveness": (
                r"\b(?:compared with|versus|superior|inferior|noninferior|"
                r"lower|higher|reduced|increased|similar|no difference|"
                r"risk ratio|hazard ratio|odds ratio|confidence interval)\b"
            ),
            "prognostic_evidence": (
                r"\b(?:associated with|predict(?:ed|s)?|risk|mortality|"
                r"recurrence|incidence|hazard ratio|odds ratio)\b"
            ),
            "diagnostic_evidence": (
                r"\b(?:sensitivity|specificity|accuracy|threshold|cut-?off|"
                r"diagnostic performance|area under the curve)\b"
            ),
            "stable_mechanism": (
                r"\b(?:mediated|pathway|mechanism|through|contributes? to|"
                r"associated with)\b"
            ),
            "treatment_evidence": (
                r"\b(?:reduced|increased|improved|effective|efficacy|safety|"
                r"associated with|resulted in|risk ratio|hazard ratio|"
                r"confidence interval|recommend(?:ed|s)?)\b"
            ),
        }
        pattern = patterns.get(question_type)
        return bool(pattern and re.search(pattern, text, re.I))

    @staticmethod
    def _intent_bonus(question_type: str, text: str) -> float:
        patterns = {
            "guideline_treatment": r"\b(?:recommend|target|should|advised|guideline|consensus|mm\s*hg)\b",
            "latest_research_trial": r"\b(?:randomi[sz]ed|trial|outcome|reduced|increased|difference|confidence interval)\b",
            "diagnostic_evidence": r"\b(?:diagnos|screen|measure|sensitivity|specificity|threshold)\w*\b",
            "stable_mechanism": r"\b(?:mechanism|pathway|associated|mediated|risk factor)\w*\b",
            "treatment_evidence": r"\b(?:treatment|therapy|reduced|increased|outcome|effective|safety)\w*\b",
        }
        pattern = patterns.get(question_type)
        return 0.22 if pattern and re.search(pattern, text, re.I) else 0.0

    @staticmethod
    def _required_focus_groups(question: str) -> list[set[str]]:
        mapping: tuple[tuple[str, set[str]], ...] = (
            (r"糖尿病|血糖|hba1c|diabetes", {"diabetes", "diabetic", "glycemic", "hba1c"}),
            (r"房颤|心房颤动|atrial fibrillation", {"atrial", "fibrillation", "af"}),
            (r"冠心病|冠状动脉|coronary", {"coronary", "cad", "atherosclerotic"}),
            (r"心衰|心力衰竭|heart failure", {"heart", "failure", "hf"}),
            (r"卒中|脑血管|脑梗|stroke|cerebrovascular", {"stroke", "cerebrovascular", "ischemic", "tia"}),
            (r"高血压|血压|hypertension", {"hypertension", "pressure", "bp"}),
            (r"血脂|胆固醇|ldl|dyslipid", {"lipid", "cholesterol", "ldl", "dyslipidemia"}),
        )
        return [terms for pattern, terms in mapping if re.search(pattern, question, re.I)]

    @staticmethod
    def _required_intervention_groups(question: str) -> list[set[str]]:
        mapping: tuple[tuple[str, set[str]], ...] = (
            (
                r"\bdoac\b|\bnoac\b|直接口服抗凝|新型口服抗凝",
                {"doac", "doacs", "noac", "noacs", "direct"},
            ),
            (r"华法林|warfarin|维生素k拮抗", {"warfarin", "vka", "vkas"}),
            (r"他汀|statin", {"statin", "statins"}),
            (r"依折麦布|ezetimibe", {"ezetimibe"}),
            (r"pcsk9", {"pcsk9"}),
            (r"sglt2", {"sglt2", "sglt-2"}),
            (r"glp-?1", {"glp1", "glp-1"}),
        )
        return [terms for pattern, terms in mapping if re.search(pattern, question, re.I)]


class PreAtomicClaimSplitter:
    """Identity splitter for generators that already emit atomic claims."""

    def split(self, claims: Sequence[Claim]) -> list[Claim]:
        identifiers = [claim.claim_id for claim in claims]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("duplicate atomic claim ID")
        return list(claims)
