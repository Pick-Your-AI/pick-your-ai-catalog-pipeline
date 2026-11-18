"""Bounded, synthetic-only CP-06.02 evidence qualification rehearsal.

This module does not authenticate sources, assess rights, approve research, or
produce publication-eligible findings. All outputs are unverified proposals.
"""
from __future__ import annotations

import json
from pathlib import Path

from jsonschema import Draft202012Validator

_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "evidence-assessment.schema.json"
_STATES = ("unknown", "source_checked", "reviewed", "independently_reproduced")
_REQUIRED_SCOPE = {
    "capability": ("version", "runtime"),
    "benchmark": ("version", "runtime", "workload"),
    "hardware_fit": ("version", "runtime", "hardware", "quantization"),
    "price": ("version", "region", "currency"),
}


class EvidenceError(ValueError):
    """Fixed diagnostics only: never embed untrusted data or schema paths."""


def assess(payload: dict) -> dict:
    """Return hypothetical qualification, never accepted truth or rights.

    Repeated citations from one lineage count once. An independent reproduction
    requires a qualifying independent measurement and an explicit fixture
    reproducer; review of a vendor statement cannot establish reproduction.
    """
    schema = json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))
    if not Draft202012Validator(schema).is_valid(payload):
        raise EvidenceError("invalid synthetic evidence assessment")

    receipts = payload["receipts"]
    receipt_ids = [r["receipt_id"] for r in receipts]
    if len(receipt_ids) != len(set(receipt_ids)):
        raise EvidenceError("duplicate synthetic receipt identity")

    supporting = [r for r in receipts if r["supports_claim"]]
    lineages: dict[str, list[dict]] = {}
    for receipt in supporting:
        lineages.setdefault(receipt["lineage_id"], []).append(receipt)

    missing_scope = [k for k in _REQUIRED_SCOPE.get(payload["claim_type"], ())
                     if k not in payload["scope"]]
    warnings = []
    if missing_scope:
        warnings.append("scope_unqualified")
    if len(supporting) > len(lineages):
        warnings.append("repeated_lineage_not_independent")

    level = 0
    independent_lineages = 0
    for lineage_receipts in lineages.values():
        lineage_level = 0
        lineage_reproduced = False
        for r in lineage_receipts:
            authority = r["assessor_authority"]
            state = r["review_state"]
            if state in ("source_checked", "reviewed", "independently_reproduced") and authority != "none":
                lineage_level = max(lineage_level, 1)
            if state in ("reviewed", "independently_reproduced") and authority in ("synthetic_reviewer", "synthetic_reproducer"):
                lineage_level = max(lineage_level, 2)
            if (state == "independently_reproduced" and authority == "synthetic_reproducer"
                    and r["evidence_class"] == "Independent measurement"
                    and r["method_documented"] and r["conditions_documented"]):
                lineage_reproduced = True
                lineage_level = 3
        independent_lineages += int(lineage_reproduced)
        level = max(level, lineage_level)

    if missing_scope:
        level = 0  # A universal capability, quote or hardware-fit assertion is not qualified.
    if any(r["review_state"] == "independently_reproduced" for r in supporting) and not independent_lineages:
        warnings.append("reproduction_unsubstantiated")

    return {
        "schema_version": "0.1-draft",
        "synthetic": True,
        "publication_eligible": False,
        "rights_cleared": False,
        "assessment_authorized": False,
        "decision_status": "synthetic_unverified",
        "claim_id": payload["claim_id"],
        "proposed_evidence_state": _STATES[level],
        "evidence_classes": sorted(set(r["evidence_class"] for r in supporting)),
        "supporting_lineage_count": len(lineages),
        "independent_reproduction_lineage_count": independent_lineages,
        "warnings": warnings,
    }
