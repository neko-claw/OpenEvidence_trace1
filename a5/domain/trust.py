"""A4↔A5 trust-tier metadata contract.

A4's Evidence Mixer splits RRF candidates into a verified pool and a discovery
pool; the A2/A4 adapter records which pool a record came from in
``EvidenceRecord.source_metadata`` using the keys below. A5 never infers trust
from ``source_type``: a web page can carry a PMID and a PubMed row can be
unverified. Only an explicit ``trust_tier=verified`` passes the Gate5 trust
check for CRITICAL claims; a missing tier is treated as not verified.

Promotion (discovery → verified) is an action, not a third tier: A2 resolves
PMID/DOI/NCT against an authoritative source and rewrites the metadata, so the
record stays at ``trust_tier=verified`` with ``promoted=true`` in diagnostics.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Any

TRUST_TIER = "trust_tier"
VERIFICATION_METHOD = "verification_method"
ORIGINAL_SOURCE = "original_source"
PROMOTED = "promoted"


class TrustTier(StrEnum):
    VERIFIED = "verified"
    DISCOVERY = "discovery"


def trust_tier_of(metadata: Mapping[str, Any]) -> TrustTier:
    """Fail-closed: only an explicit ``verified`` value counts as verified."""
    return (
        TrustTier.VERIFIED
        if metadata.get(TRUST_TIER) == TrustTier.VERIFIED
        else TrustTier.DISCOVERY
    )
