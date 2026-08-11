"""Tests for tuning grid, freeze records, and R0–R3 ablation (4.3/4.6)."""

from __future__ import annotations

import json

from retrieval.ablation import decide, run_ablation, write_ablation_csv
from retrieval.cross_encoder import CrossEncoderScorer
from retrieval.models import EvidenceChunk, Query
from retrieval.tuning import recall_curve, run_grid, write_freeze_record
from retrieval.config import RetrievalConfig


def _chunk(chunk_id: str, text: str, **changes: object) -> EvidenceChunk:
    values: dict[str, object] = {
        "chunk_id": chunk_id,
        "evidence_id": f"evidence-{chunk_id}",
        "stable_id": f"PMID:{chunk_id}",
        "text": text,
        "source_type": "pubmed",
        "evidence_level": "rct",
        "index_version": "idx-t",
        "corpus_version": "corpus-t",
    }
    values.update(changes)
    return EvidenceChunk(**values)  # type: ignore[arg-type]


def _config() -> RetrievalConfig:
    return RetrievalConfig(
        index_version="idx-t",
        corpus_version="corpus-t",
        rerank_config_version="rerank-t",
        selection_top_k=2,
    )


CHUNKS = (
    _chunk("c-amlodipine", "Amlodipine reduced systolic blood pressure in older adults with hypertension."),
    _chunk("c-statin", "Statins lower LDL cholesterol in adults with dyslipidemia."),
    _chunk("c-guideline", "The hypertension guideline recommends first-line amlodipine for older adults.", source_type="guideline", evidence_level="guideline"),
    _chunk("c-trial", "A recent randomized trial of amlodipine versus placebo reported blood pressure reduction."),
)

QUESTIONS = (
    (
        Query(query_id="q1", text="amlodipine hypertension older adults", question_type="therapy"),
        {"c-amlodipine": 3.0, "c-guideline": 2.0},
    ),
    (
        Query(query_id="q2", text="statin LDL cholesterol"),
        {"c-statin": 3.0},
    ),
)


def test_run_grid_sweeps_k_triples_and_aggregates_metrics() -> None:
    rows = run_grid(
        QUESTIONS,
        CHUNKS,
        k0_values=(20, 50),
        k1_values=(10, 20),
        k2_values=(3, 5),
        config=_config(),
    )

    assert len(rows) == 8
    assert all(0.0 <= row.recall_at_k0 <= 1.0 for row in rows)
    assert all(0.0 <= row.ndcg_at_k2 <= 1.0 for row in rows)
    assert {row.k0 for row in rows} == {20, 50}
    # K2 never exceeds K1.
    assert all(row.k2 <= row.k1 for row in rows)


def test_recall_curve_keeps_k1_k2_fixed() -> None:
    rows = recall_curve(QUESTIONS, CHUNKS, k0_values=(20, 80), k1=10, k2=3, config=_config())

    assert len(rows) == 2
    assert {row.k1 for row in rows} == {10}
    assert {row.k2 for row in rows} == {3}
    assert {row.k0 for row in rows} == {20, 80}


def test_write_freeze_record_contains_chosen_k_and_config(tmp_path) -> None:
    row = run_grid(QUESTIONS, CHUNKS, k0_values=(20,), k1_values=(10,), k2_values=(3,), config=_config())[0]
    path = write_freeze_record(
        tmp_path / "freeze.json",
        chosen=row,
        config=_config(),
        dev_summary={"recall_at_k0": row.recall_at_k0, "ndcg_at_k2": row.ndcg_at_k2},
    )

    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["chosen_k"] == {"k0": 20, "k1": 10, "k2": 3}
    assert record["config"]["rerank_config_version"] == "rerank-t"
    assert "frozen_at" in record


class FakeCrossEncoder:
    def predict(self, pairs: object) -> list[float]:
        return [0.9] * len(list(pairs))  # type: ignore[arg-type]


def test_run_ablation_produces_r0_r1_r2_r3_rows_and_decisions() -> None:
    scorer = CrossEncoderScorer(model_factory=lambda name: FakeCrossEncoder())
    rows = run_ablation(
        QUESTIONS,
        CHUNKS,
        cross_encoder=scorer,
        config=_config(),
    )

    conditions = [row.condition for row in rows]
    assert conditions == ["R0", "R1", "R2", "R3"]
    assert all(0.0 <= row.recall_at_k0 <= 1.0 for row in rows)
    assert rows[-1].context_tokens >= 0

    decisions = decide(rows)
    assert "cross_encoder" in decisions
    assert "gate" in decisions


def test_write_ablation_csv(tmp_path) -> None:
    rows = run_ablation(QUESTIONS, CHUNKS, config=_config())
    path = write_ablation_csv(tmp_path / "ablation.csv", rows)

    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1 + len(rows)
    assert lines[0].startswith("condition,recall_at_k0")
