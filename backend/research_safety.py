from __future__ import annotations

import re

from a1.models import SafetyPolicyInput, SpecialPopulation, TopicScope
from a1.ports.safety_classifier import SafetyClassificationRequest


class ConservativeResearchSafetyClassifier:
    """Narrow deterministic classifier for the public research experience.

    It is deliberately limited to the configured cardiometabolic topics. It does not diagnose,
    prescribe, or infer a patient's condition. Ambiguous/out-of-scope input is
    completed as OTHER so A1's reference policy refuses before retrieval.
    """

    version = "research-scope-classifier-v0.2.0"

    _hypertension = re.compile(r"高血压|血压|hypertension|blood\s+pressure", re.I)
    _dyslipidemia = re.compile(
        r"血脂|胆固醇|低密度脂蛋白|高密度脂蛋白|甘油三酯|"
        r"dyslipid|cholesterol|\bldl\b|\bhdl\b|triglyceride",
        re.I,
    )
    _cardiovascular = re.compile(
        r"心血管|冠心病|冠状动脉|动脉粥样硬化|心肌梗死|心衰|心力衰竭|房颤|心房颤动|"
        r"cardiovascular|coronary|atherosclero|myocardial infarction|heart failure|atrial fibrillation",
        re.I,
    )
    _cerebrovascular = re.compile(
        r"心脑血管|脑血管|脑卒中|卒中|脑梗|短暂性脑缺血|"
        r"cerebrovascular|stroke|transient ischemic attack|\btia\b",
        re.I,
    )
    _diabetes = re.compile(
        r"糖尿病|血糖|糖化血红蛋白|胰岛素抵抗|diabetes|glycemi|hba1c|insulin resistance",
        re.I,
    )
    _emergency = re.compile(
        r"急救|救命|马上怎么办|胸痛|呼吸困难|昏迷|晕厥|抽搐|"
        r"emergency|chest\s+pain|shortness\s+of\s+breath|unconscious",
        re.I,
    )
    _personal_diagnosis = re.compile(
        r"我是不是|我得了|帮我诊断|给我诊断|diagnose\s+me|do\s+i\s+have",
        re.I,
    )
    _prescribing = re.compile(
        r"我该吃|我能吃|给我开|开药|停药|换药|加量|减量|剂量|多少毫克|"
        r"prescribe|my\s+dose|change\s+my\s+medication|stop\s+taking",
        re.I,
    )
    _injection = re.compile(
        r"忽略.{0,12}(规则|指令)|伪造.{0,8}(引用|论文)|编造.{0,8}(PMID|DOI|NCT)|"
        r"ignore.{0,20}instructions|fabricate.{0,20}(citation|pmid|doi)",
        re.I,
    )
    _identifiable = re.compile(
        r"\b\d{17}[0-9Xx]\b|\b1[3-9]\d{9}\b|身份证|病历号|住院号",
        re.I,
    )
    _pregnancy = re.compile(r"孕妇|妊娠|怀孕|pregnan", re.I)
    _pediatric = re.compile(r"儿童|小儿|婴儿|未成年|pediatric|child|infant", re.I)
    _other_population = re.compile(r"透析|肾移植|器官移植", re.I)

    def classify(self, request: SafetyClassificationRequest) -> SafetyPolicyInput:
        text = request.text.strip()
        # Choose the population/primary disease before an outcome domain. A
        # single safety topic is only a scope label; A5 preserves all concepts
        # for retrieval (for example diabetes AND cardiovascular outcomes).
        if self._diabetes.search(text):
            topic = TopicScope.DIABETES
        elif self._cerebrovascular.search(text):
            topic = TopicScope.CEREBROVASCULAR
        elif self._cardiovascular.search(text):
            topic = TopicScope.CARDIOVASCULAR
        elif self._hypertension.search(text):
            topic = TopicScope.HYPERTENSION
        elif self._dyslipidemia.search(text):
            topic = TopicScope.DYSLIPIDEMIA
        else:
            topic = TopicScope.OTHER
        if self._pregnancy.search(text):
            population = SpecialPopulation.PREGNANCY
        elif self._pediatric.search(text):
            population = SpecialPopulation.PEDIATRIC
        elif self._other_population.search(text):
            population = SpecialPopulation.OTHER
        else:
            population = SpecialPopulation.NONE
        return SafetyPolicyInput(
            question_id=request.question_id,
            topic=topic,
            acute_emergency=bool(self._emergency.search(text)),
            personal_diagnosis=bool(self._personal_diagnosis.search(text)),
            personalized_prescribing_or_dose_change=bool(self._prescribing.search(text)),
            prompt_injection_or_fabricated_reference=bool(self._injection.search(text)),
            identifiable_personal_data=bool(self._identifiable.search(text)),
            special_population=population,
        )
