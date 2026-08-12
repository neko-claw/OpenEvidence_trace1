from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path
from threading import RLock
from typing import Any


class LocalVerifiedClaimPresenter:
    """Fail-closed local Chinese presentation of a verified source statement.

    This adapter runs *after* Gate5 and cannot change Claim/Evidence bindings.
    It rejects output when numeric values, medical abbreviations, comparative
    direction, or external-reference policy drift. The verified English source
    statement always remains in ``AnswerFinding.statement`` for audit.
    """

    version = "local-verified-claim-presenter-v0.1.0"
    _numbers = re.compile(r"(?<![A-Za-z])\d+(?:\.\d+)?")
    _external_reference = re.compile(
        r"(?:https?://|www\.|\bPMID\s*:?\s*\d+\b|\bNCT\d{8}\b|"
        r"\b10\.\d{4,9}/\S+|\bGUIDELINE\s*:)",
        re.I,
    )
    _unsafe_terms = re.compile(r"阿德福韦|adefovir", re.I)
    _glossary: tuple[tuple[str, str], ...] = (
        ("DOACs", "直接口服抗凝药（DOAC）"),
        ("DOAC", "直接口服抗凝药（DOAC）"),
        ("NOACs", "新型口服抗凝药（NOAC）"),
        ("NOAC", "新型口服抗凝药（NOAC）"),
        ("VKAs", "维生素K拮抗剂（VKA）"),
        ("VKA", "维生素K拮抗剂（VKA）"),
        ("Warfarin", "华法林"),
        ("RR", "RR"),
        ("CI", "CI"),
    )

    def __init__(
        self,
        model_path: str | Path,
        prompt_path: str | Path,
        *,
        max_new_tokens: int = 256,
    ) -> None:
        self._model_path = Path(model_path)
        self._prompt = Path(prompt_path).read_text(encoding="utf-8")
        self._max_new_tokens = max_new_tokens
        self._lock = RLock()
        self._tokenizer: Any | None = None
        self._model: Any | None = None

    @property
    def available(self) -> bool:
        return (self._model_path / "model.safetensors").is_file()

    def present(self, statement: str) -> str | None:
        if not self.available:
            return None
        try:
            with self._lock:
                tokenizer, model = self._load()
                messages = (
                    {"role": "system", "content": self._prompt},
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "verified_source_statement": statement,
                                "required_glossary": {
                                    source: target
                                    for source, target in self._glossary
                                    if re.search(rf"\b{re.escape(source)}\b", statement, re.I)
                                },
                            },
                            ensure_ascii=False,
                        ),
                    },
                )
                text = tokenizer.apply_chat_template(
                    messages, tokenize=False, add_generation_prompt=True
                )
                inputs = tokenizer([text], return_tensors="pt")
                generated = model.generate(
                    **inputs,
                    max_new_tokens=self._max_new_tokens,
                    do_sample=False,
                    pad_token_id=tokenizer.eos_token_id,
                )
                output = tokenizer.decode(
                    generated[0][inputs.input_ids.shape[1] :],
                    skip_special_tokens=True,
                ).strip()
            payload = json.loads(self._extract_object(output))
            candidate = payload.get("display_statement")
            if not isinstance(candidate, str):
                return None
            candidate = candidate.strip()
            return candidate if self._validate(statement, candidate) else None
        except Exception:
            return None

    def _load(self):
        if self._tokenizer is not None and self._model is not None:
            return self._tokenizer, self._model
        from transformers import AutoModelForCausalLM, AutoTokenizer
        import torch

        torch.set_num_threads(max(1, min(8, os.cpu_count() or 1)))
        self._tokenizer = AutoTokenizer.from_pretrained(
            self._model_path, local_files_only=True
        )
        self._model = AutoModelForCausalLM.from_pretrained(
            self._model_path, local_files_only=True, device_map=None
        )
        self._model.eval()
        return self._tokenizer, self._model

    @staticmethod
    def _extract_object(text: str) -> str:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("no JSON object")
        return text[start : end + 1]

    def _validate(self, source: str, candidate: str) -> bool:
        if not candidate or len(candidate) > max(1000, len(source) * 4):
            return False
        if self._external_reference.search(candidate) or self._unsafe_terms.search(candidate):
            return False
        if Counter(self._numbers.findall(source)) != Counter(self._numbers.findall(candidate)):
            return False
        for term, translated in self._glossary:
            if re.search(rf"\b{re.escape(term)}\b", source, re.I):
                required_abbreviation = re.search(r"（([^）]+)）", translated)
                if required_abbreviation and required_abbreviation.group(1) not in candidate:
                    return False
                if not required_abbreviation and translated.casefold() not in candidate.casefold():
                    return False
        directions = (
            (r"\b(?:lower|reduced|decreased)\b", r"降低|较低|减少|低于"),
            (r"\b(?:higher|increased)\b", r"升高|较高|增加|高于"),
            (r"\bsuperior\b", r"优于|更优"),
            (r"\bno (?:significant )?difference\b", r"无(?:显著)?差异|没有(?:显著)?差异"),
        )
        return all(
            not re.search(source_pattern, source, re.I)
            or re.search(target_pattern, candidate)
            for source_pattern, target_pattern in directions
        )
