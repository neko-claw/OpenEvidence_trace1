from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from a2.models.evidence import A2Evidence, SourceType


def normalize_doi(value: str | None) -> str | None:
    """Normalize a DOI without inventing or validating an absent identifier."""
    if not value:
        return None
    normalized = value.strip().lower()
    normalized = re.sub(r"^https?://(?:dx\.)?doi\.org/", "", normalized)
    normalized = re.sub(r"^doi:\s*", "", normalized)
    return normalized.strip() or None


def canonical_key(record: A2Evidence) -> str:
    """Return the conservative cross-source deduplication key."""
    doi = normalize_doi(record.doi)
    if doi:
        return f"DOI:{doi}"
    if record.pmid:
        return f"PMID:{record.pmid}"
    if record.nct_id:
        return f"NCT:{record.nct_id.upper()}"
    if record.source_type is SourceType.GUIDELINE:
        return record.id
    return f"{record.source_type.value.upper()}:{record.id}"


def compute_content_hash(data: dict[str, Any]) -> str:
    """Hash stable core content; volatile request/fetch fields are excluded."""
    stable = {
        "source_identity": {
            "source_type": str(data.get("source_type") or ""),
            "pmid": data.get("pmid"), "doi": normalize_doi(data.get("doi")),
            "nct_id": data.get("nct_id"), "guideline_name": data.get("guideline_name"),
            "page": data.get("page"), "id": data.get("id"),
        },
        "title": " ".join(str(data.get("title") or "").split()),
        "abstract_or_chunk": " ".join(str(data.get("abstract_or_chunk") or "").split()),
        "published_at": str(data.get("published_at") or ""),
    }
    payload = json.dumps(stable, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def conservative_merge(existing: A2Evidence, incoming: A2Evidence) -> A2Evidence:
    """Fill missing fields while retaining explicit conflicts as diagnostics."""
    left = existing.model_dump(mode="python")
    right = incoming.model_dump(mode="python")
    conflicts = list(existing.source_metadata.get("dedup_conflicts", []))
    ignored = {"schema_version", "id", "source_type", "fetched_at", "content_hash", "source_metadata"}
    for field, value in right.items():
        if field in ignored or value in (None, [], ""):
            continue
        if left.get(field) in (None, [], ""):
            left[field] = value
        elif left[field] != value:
            conflicts.append({"field": field, "kept": left[field], "alternative": value, "source": incoming.source_type.value})
    aliases = list(existing.source_metadata.get("aliases", []))
    for alias in (existing.id, incoming.id):
        if alias not in aliases:
            aliases.append(alias)
    metadata = dict(existing.source_metadata)
    metadata["aliases"] = aliases
    if conflicts:
        metadata["dedup_conflicts"] = conflicts
    metadata.setdefault("source_records", {})[incoming.source_type.value] = incoming.source_metadata
    left["source_metadata"] = metadata
    left["content_hash"] = compute_content_hash(left)
    return A2Evidence.model_validate(left)
