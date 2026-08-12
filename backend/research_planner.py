from __future__ import annotations

import re

from a5.domain.models import AgentPlan, EvidenceRecord, Question, SearchPlan
from a5.runtime_config import RuntimeConfig
from a5.skills.evidence_research import EvidenceResearchSkill


class PublicEvidenceResearchSkill(EvidenceResearchSkill):
    """Question-aware bilingual retrieval planner for the focused MVP domains."""

    _latest = re.compile(r"最新|近期|近年|目前|current|latest|recent", re.I)
    _guideline = re.compile(r"指南|共识|推荐|目标|guideline|consensus|recommend", re.I)
    _trial = re.compile(r"临床试验|随机|RCT|正在进行|招募|trial|randomized|recruit", re.I)
    _diagnosis = re.compile(r"诊断|筛查|测量|diagnos|screen|measurement", re.I)
    _mechanism = re.compile(r"机制|为什么|风险因素|mechanism|risk\s+factor", re.I)
    _prognosis = re.compile(r"预后|死亡|复发|风险|结局|prognos|mortality|recurrence|outcome|risk", re.I)
    _comparison = re.compile(r"比较|相比|孰优|疗效|安全性|versus|compare|efficacy|safety", re.I)
    _hypertension = re.compile(r"高血压|血压|hypertension|blood\s+pressure", re.I)
    _dyslipidemia = re.compile(r"血脂|胆固醇|低密度脂蛋白|甘油三酯|dyslipid|cholesterol|\bldl\b|triglyceride", re.I)
    _cardiovascular = re.compile(r"心血管|冠心病|冠状动脉|动脉粥样硬化|心肌梗死|心衰|心力衰竭|房颤|心房颤动|cardiovascular|coronary|atherosclero|myocardial infarction|heart failure|atrial fibrillation", re.I)
    _cerebrovascular = re.compile(r"心脑血管|脑血管|脑卒中|卒中|脑梗|短暂性脑缺血|cerebrovascular|stroke|transient ischemic attack|\btia\b", re.I)
    _diabetes = re.compile(r"糖尿病|血糖|糖化血红蛋白|胰岛素抵抗|diabetes|glycemi|hba1c|insulin resistance", re.I)

    def __init__(self, runtime_config: RuntimeConfig) -> None:
        super().__init__(runtime_config)

    def classify(self, question: Question) -> str:
        text = question.text
        if self._trial.search(text):
            return "latest_research_trial"
        if self._guideline.search(text):
            return "guideline_treatment"
        if self._diagnosis.search(text):
            return "diagnostic_evidence"
        if self._mechanism.search(text):
            return "stable_mechanism"
        if self._prognosis.search(text):
            return "prognostic_evidence"
        if self._comparison.search(text):
            return "comparative_effectiveness"
        return "treatment_evidence"

    def plan(self, question: Question) -> AgentPlan:
        question_type = self.classify(question)
        topic = self._topic_query(question.text)
        intent = {
            "guideline_treatment": (
                '(guideline[Publication Type] OR practice guideline[Publication Type] '
                'OR guideline OR consensus OR recommendation)'
            ),
            "latest_research_trial": '(randomized controlled trial OR clinical trial)',
            "diagnostic_evidence": '(diagnosis OR screening OR measurement)',
            "stable_mechanism": '(systematic review OR review OR mechanism)',
            "prognostic_evidence": '(prognosis OR mortality OR cardiovascular outcome OR recurrence)',
            "comparative_effectiveness": '(systematic review OR meta-analysis OR randomized controlled trial OR comparative effectiveness)',
            "treatment_evidence": '(systematic review OR meta-analysis OR randomized controlled trial)',
        }[question_type]
        context_terms = self._context_terms(question.text)
        queries = [f"{topic} AND {intent}"]
        if context_terms:
            queries.insert(0, f"{topic} AND ({' OR '.join(context_terms)}) AND {intent}")
        preferred = {
            "guideline_treatment": ["current_guideline", "pubmed_review", "europe_pmc"],
            "latest_research_trial": ["clinicaltrials_record", "pubmed_trial", "europe_pmc"],
            "stable_mechanism": ["pubmed_review", "europe_pmc"],
            "diagnostic_evidence": ["pubmed_review", "europe_pmc", "primary_study"],
            "prognostic_evidence": ["pubmed_review", "europe_pmc", "primary_study"],
            "comparative_effectiveness": ["pubmed_review", "pubmed_trial", "europe_pmc"],
            "treatment_evidence": ["pubmed_review", "europe_pmc", "primary_study"],
        }[question_type]
        max_calls = min(len(preferred), self.runtime_config.agent.max_tool_calls)
        return AgentPlan(
            question_type=question_type,
            selected_skill=self.identifier,
            search_plan=SearchPlan(
                queries=queries,
                preferred_sources=preferred,
                freshness_required=bool(self._latest.search(question.text)) or question_type in {
                    "guideline_treatment", "latest_research_trial"
                },
                expected_evidence_types={
                    "guideline_treatment": ["guideline"],
                    "latest_research_trial": ["clinical_trial_registry", "controlled_study"],
                    "stable_mechanism": ["systematic_review", "review"],
                    "diagnostic_evidence": ["systematic_review", "study"],
                    "prognostic_evidence": ["systematic_review", "cohort_study"],
                    "comparative_effectiveness": ["systematic_review", "controlled_study"],
                    "treatment_evidence": ["systematic_review", "controlled_study"],
                }[question_type],
                max_tool_calls=max_calls,
            ),
            policy_version="public-evidence-query-policy-v0.2.0",
            evidence_summary=self.summarize([], freshness_required=False),
        )

    @staticmethod
    def _context_terms(text: str) -> list[str]:
        mapping = {
            "慢性肾病": '"chronic kidney disease"',
            "肾病": '"kidney disease"',
            "糖尿病": "diabetes",
            "老年": "older adults",
            "心血管": '"cardiovascular outcomes"',
            "卒中": "stroke",
            "他汀": "statin",
            "依折麦布": "ezetimibe",
            "PCSK9": "PCSK9",
            "房颤": '"atrial fibrillation"',
            "心房颤动": '"atrial fibrillation"',
            "华法林": "warfarin",
            "DOAC": '"direct oral anticoagulant"',
            "NOAC": '"novel oral anticoagulant"',
            "SGLT2": '"SGLT2 inhibitor"',
            "GLP-1": '"GLP-1 receptor agonist"',
            "不耐受": "intolerance",
            "安全": "safety",
            "目标": "target",
        }
        return [term for chinese, term in mapping.items() if chinese.casefold() in text.casefold()]

    def _topic_query(self, text: str) -> str:
        concepts: list[str] = []
        if self._diabetes.search(text):
            concepts.append('(diabetes mellitus OR glycemic control OR HbA1c)')
        if self._dyslipidemia.search(text):
            concepts.append('(dyslipidemia OR hypercholesterolemia OR cholesterol OR LDL)')
        if self._hypertension.search(text):
            concepts.append('(hypertension OR "high blood pressure")')
        if self._cardiovascular.search(text):
            terms = ['cardiovascular disease']
            focused = {
                "冠心病": 'coronary artery disease',
                "冠状动脉": 'coronary artery disease',
                "动脉粥样硬化": 'atherosclerotic cardiovascular disease',
                "心肌梗死": 'myocardial infarction',
                "心衰": 'heart failure',
                "心力衰竭": 'heart failure',
                "房颤": 'atrial fibrillation',
                "心房颤动": 'atrial fibrillation',
            }
            terms.extend(value for key, value in focused.items() if key in text)
            concepts.append(f"({' OR '.join(dict.fromkeys(terms))})")
        if self._cerebrovascular.search(text):
            concepts.append('(stroke OR cerebrovascular disease OR "transient ischemic attack")')
        return " AND ".join(dict.fromkeys(concepts)) or '(cardiometabolic disease)'

    def summarize(
        self,
        evidence: list[EvidenceRecord],
        *,
        freshness_required: bool,
        as_of_date=None,
    ):
        return super().summarize(
            evidence, freshness_required=freshness_required, as_of_date=as_of_date
        )
