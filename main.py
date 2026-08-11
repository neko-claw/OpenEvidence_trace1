from __future__ import annotations

import json
from pathlib import Path

from a5.api import answer
from a5.bootstrap import build_demo_workflow
from a5.domain.models import Question
from a5.observability.trace import render_trace


def load_demo_questions() -> list[Question]:
    fixture = Path(__file__).parent / "a5" / "fixtures" / "questions.json"
    payload = json.loads(fixture.read_text(encoding="utf-8"))
    return [Question.model_validate(item) for item in payload]


def main() -> None:
    workflow = build_demo_workflow()
    for question in load_demo_questions():
        run = answer(question, workflow=workflow)
        print("=" * 72)
        print(f"Question: {question.text}")
        print(f"Evidence: {[item.id for item in run.retrieved_evidence]}")
        print(f"Claims: {[item.claim_id for item in run.claims]}")
        print(f"Decision: {run.decision}")
        print("Final Answer:")
        print(run.final_answer.text if run.final_answer else "<missing>")
        if run.final_answer and run.final_answer.limitations:
            print(f"Limitations: {run.final_answer.limitations}")
        print("Trace:")
        print(render_trace(run))


if __name__ == "__main__":
    main()
