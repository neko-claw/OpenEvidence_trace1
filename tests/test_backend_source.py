from __future__ import annotations

import json
from pathlib import Path

from backend.config import load_backend_config
from backend.source import A2EvidenceSource


ROOT = Path(__file__).resolve().parents[1]


class RecordingClient:
    def __init__(self, response: dict[str, object]) -> None:
        self.response = response
        self.calls: list[tuple[str, dict[str, object]]] = []

    def call_tool(self, name: str, arguments: dict[str, object]) -> dict[str, object]:
        self.calls.append((name, arguments))
        return self.response


def fixture_response() -> dict[str, object]:
    return json.loads(
        (ROOT / "contracts" / "a2" / "v1" / "fixtures" / "mock_tool_response.json")
        .read_text(encoding="utf-8")
    )


def test_source_alias_is_configured_and_one_acquire_is_exactly_one_mcp_call() -> None:
    config = load_backend_config()
    client = RecordingClient(fixture_response())
    source = A2EvidenceSource(client, config=config)

    batch = source.acquire(
        queries=["synthetic hypertension fixture"],
        source_alias="systematic_review",
        tool_call_index=2,
    )

    assert client.calls == [
        (
            "search_pubmed",
            {"queries": ["synthetic hypertension fixture"], "limit": 50},
        )
    ]
    assert source.call_count == 1
    assert batch.tool_call_index == 2
    assert batch.evidence and all(item.mock for item in batch.evidence)
    assert batch.diagnostics["backend_config_hash"] == config.snapshot_hash()


def test_unsupported_alias_does_not_spend_an_mcp_call() -> None:
    client = RecordingClient(fixture_response())
    source = A2EvidenceSource(client)

    batch = source.acquire(
        queries=["fixture"], source_alias="unapproved-source", tool_call_index=1
    )

    assert batch.error_code == "UNSUPPORTED_SOURCE_ALIAS"
    assert batch.diagnostics["tool_called"] is False
    assert client.calls == []
    assert source.call_count == 0


def test_failed_tool_envelope_is_not_accepted_as_empty_success() -> None:
    response = fixture_response()
    response["ok"] = False
    response["evidence"] = []
    response["error"] = {
        "code": "TIMEOUT",
        "source": "pubmed",
        "message": "fixture timeout",
        "retryable": True,
    }
    client = RecordingClient(response)

    batch = A2EvidenceSource(client).acquire(
        queries=["fixture"], source_alias="pubmed", tool_call_index=1
    )

    assert batch.error_code == "A2_CONTRACT_ERROR"
    assert batch.evidence == ()
    assert len(client.calls) == 1
