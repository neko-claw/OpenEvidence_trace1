from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from a2.connectors.base import A2HTTPClient
from a2.models.errors import A2Error, A2ErrorCode, A2Exception
from a2.models.evidence import A2Evidence, SourceType
from a2.storage.dedup import compute_content_hash


class ClinicalTrialsConnector:
    """ClinicalTrials.gov API v2 connector."""

    def __init__(self, http: A2HTTPClient, base_url: str) -> None:
        self.http = http
        self.base_url = base_url.rstrip("/")

    def search(self, query: str, limit: int = 10, page_token: str | None = None) -> list[A2Evidence]:
        """Search ClinicalTrials.gov API v2 studies."""
        params: dict[str, Any] = {"query.term": query, "pageSize": limit, "format": "json"}
        if page_token:
            params["pageToken"] = page_token
        payload = self.http.get_json(f"{self.base_url}/studies", params=params)
        studies = payload.get("studies")
        if not isinstance(studies, list):
            raise A2Exception(A2Error(code=A2ErrorCode.UPSTREAM_PARSE_ERROR, source="clinical_trials", message="ClinicalTrials response missing studies"))
        return [self._parse(item, payload.get("dataTimestamp")) for item in studies[:limit]]

    def get(self, nct_id: str) -> A2Evidence:
        """Fetch one exact NCT identifier."""
        try:
            payload = self.http.get_json(f"{self.base_url}/studies/{nct_id.upper()}", params={"format": "json"})
        except A2Exception as exc:
            if exc.error.http_status == 404:
                raise A2Exception(A2Error(code=A2ErrorCode.NOT_FOUND, source="clinical_trials", message="ClinicalTrials study not found", http_status=404)) from exc
            raise
        return self._parse(payload, payload.get("dataTimestamp"))

    def _parse(self, study: dict[str, Any], data_timestamp: Any = None) -> A2Evidence:
        protocol = study.get("protocolSection", {})
        identity = protocol.get("identificationModule", {})
        nct_id = str(identity.get("nctId") or "").upper()
        title = str(identity.get("officialTitle") or identity.get("briefTitle") or "").strip()
        if not nct_id or not title:
            raise A2Exception(A2Error(code=A2ErrorCode.UPSTREAM_PARSE_ERROR, source="clinical_trials", message="ClinicalTrials study missing required identity/title"))
        status = protocol.get("statusModule", {})
        conditions = protocol.get("conditionsModule", {}).get("conditions", [])
        arms = protocol.get("armsInterventionsModule", {}).get("interventions", [])
        outcomes_module = protocol.get("outcomesModule", {})
        outcomes = outcomes_module.get("primaryOutcomes", []) + outcomes_module.get("secondaryOutcomes", [])
        eligibility = protocol.get("eligibilityModule", {}).get("eligibilityCriteria")
        summary = protocol.get("descriptionModule", {}).get("briefSummary")
        content = str(summary or eligibility or title).strip()
        start_date = status.get("startDateStruct", {}).get("date")
        data: dict[str, Any] = {
            "id": f"NCT:{nct_id}", "source_type": SourceType.CLINICAL_TRIALS,
            "title": title, "abstract_or_chunk": content, "published_at": _date(start_date),
            "url": f"https://clinicaltrials.gov/study/{nct_id}", "nct_id": nct_id,
            "evidence_level": "clinical_trial_registry",
            "source_metadata": {
                "api_version": "v2", "data_timestamp": data_timestamp,
                "overall_status": status.get("overallStatus"), "conditions": conditions,
                "interventions": arms, "outcomes": outcomes, "eligibility_summary": eligibility,
                "start_date": start_date,
                "completion_date": status.get("completionDateStruct", {}).get("date"),
                "last_update": status.get("studyFirstSubmitDate") or status.get("studyFirstPostDateStruct", {}).get("date"),
                "sponsor": protocol.get("sponsorCollaboratorsModule", {}).get("leadSponsor"),
            },
        }
        data["content_hash"] = compute_content_hash(data)
        return A2Evidence.model_validate(data)


def _date(value: Any) -> datetime | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y-%m", "%Y"):
        try:
            return datetime.strptime(str(value), fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None
