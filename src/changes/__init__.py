"""Deterministic, synthetic-only source change classification (CP-11.02).

No retrieval, rights adjudication, evidence promotion or publication occurs here.
Observations remain immutable inputs to a proposed review queue.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import json
from pathlib import Path
import re
from typing import Any, Mapping

from jsonschema import Draft202012Validator, FormatChecker

_VERSION = "change-set-draft-0.1.0"
_KINDS = frozenset({"identity", "price", "license", "availability", "evidence", "rights", "other"})
_UTC_INSTANT = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]{1,6})?Z")


class ChangeError(ValueError):
    """A malformed or unsafe synthetic observation was rejected."""


def _validator() -> tuple[Draft202012Validator, Draft202012Validator]:
    path = Path(__file__).resolve().parents[2] / "schemas/change-set.schema.json"
    schema = json.loads(path.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return (Draft202012Validator({"$defs": schema["$defs"], "$ref": "#/$defs/observation"}, format_checker=FormatChecker()),
            Draft202012Validator(schema, format_checker=FormatChecker()))


def _timestamp(value: str) -> datetime:
    if not isinstance(value, str) or _UTC_INSTANT.fullmatch(value) is None:
        raise ChangeError("captured_at must be a UTC Z instant with at most six fractional digits")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ChangeError("invalid captured_at calendar instant") from None
    if parsed.utcoffset().total_seconds() != 0:
        raise ChangeError("captured_at must use UTC")
    return parsed


def _check(observation: Any, validator: Draft202012Validator) -> dict[str, Any]:
    if not isinstance(observation, dict):
        raise ChangeError("observation must be a plain object")
    if next(validator.iter_errors(observation), None) is not None:
        # Neither validation messages nor instance paths are safe diagnostics:
        # both can contain submitted values and attacker-chosen property names.
        raise ChangeError("invalid draft observation: schema validation failed") from None
    if observation["synthetic"] is not True or observation["schema_version"] != _VERSION:
        raise ChangeError("synthetic draft observations only")
    _timestamp(observation["captured_at"])
    paths = [claim["path"] for claim in observation["claims"]]
    if len(set(paths)) != len(paths):
        raise ChangeError("duplicate claim paths cannot be compared")
    return deepcopy(observation)


def _classification(before: Mapping[str, Any] | None,
                    after: Mapping[str, Any] | None) -> tuple[str, str]:
    kinds = {c["kind"] for c in (before, after) if c is not None}
    if not kinds or not kinds <= _KINDS:
        raise ChangeError("unknown claim kind")
    if kinds & {"rights", "license"}:
        return "hold", "source_rights_review_before_any_operation"
    if len(kinds) > 1 or "identity" in kinds:
        return "critical", "identity_or_claim_kind_review"
    if "price" in kinds:
        if before is None or after is None or (before["unit"], before["currency"]) != (after["unit"], after["currency"]):
            return "critical", "price_meter_or_currency_review"
        return "critical", "price_value_review"
    if "availability" in kinds:
        return "critical", "availability_or_retirement_review"
    if "evidence" in kinds:
        return "review", "evidence_lineage_review"
    return "review", "unclassified_claim_review"


def _evidence_changed(before: Mapping[str, Any] | None,
                      after: Mapping[str, Any] | None) -> bool:
    return before is None or after is None or before["evidence_ref"] != after["evidence_ref"]


def _review_requirements(before: Mapping[str, Any] | None,
                         after: Mapping[str, Any] | None) -> tuple[str, str, list[str]]:
    priority, route = _classification(before, after)
    evidence_changed = _evidence_changed(before, after)
    if (evidence_changed and priority != "hold" and before is not None and after is not None
            and {key: value for key, value in before.items() if key != "evidence_ref"}
            == {key: value for key, value in after.items() if key != "evidence_ref"}):
        priority, route = "review", "evidence_lineage_review"
    requirements = [route]
    if evidence_changed and "evidence_lineage_review" not in requirements:
        requirements.append("evidence_lineage_review")
    return priority, route, requirements


def classify(previous: Mapping[str, Any], current: Mapping[str, Any]) -> dict[str, Any]:
    """Compare exact synthetic observations; return no authorization or side effects.

    Byte changes, parser revisions and claim changes are distinct causes.  A
    diff is not evidence that a source removed, licensed or retired anything.
    """
    input_validator, output_validator = _validator()
    old = _check(previous, input_validator)
    new = _check(current, input_validator)
    if (old["source_id"], old["material_id"]) != (new["source_id"], new["material_id"]):
        raise ChangeError("source/material mismatch requires separate review")
    if old["observation_id"] == new["observation_id"]:
        raise ChangeError("observations must have distinct immutable identities")
    if _timestamp(new["captured_at"]) < _timestamp(old["captured_at"]):
        raise ChangeError("current observation predates previous observation")

    old_claims = {item["path"]: item for item in old["claims"]}
    new_claims = {item["path"]: item for item in new["claims"]}
    changes: list[dict[str, Any]] = []
    for path in sorted(old_claims.keys() | new_claims.keys()):
        before, after = old_claims.get(path), new_claims.get(path)
        if before == after:
            continue
        priority, route, requirements = _review_requirements(before, after)
        changes.append({"path": path, "before": before, "after": after,
                        "priority": priority, "review_route": route,
                        "review_requirements": requirements})

    byte_changed = old["content_sha256"] != new["content_sha256"]
    parser_changed = old["parser_revision"] != new["parser_revision"]
    causes = []
    if byte_changed:
        causes.append("raw_bytes_changed")
    if parser_changed:
        causes.append("parser_revision_changed")
    if changes:
        causes.append("semantic_claims_changed")
        if not byte_changed:
            causes.append("same_bytes_claim_conflict")
    if any(c["priority"] == "hold" for c in changes):
        decision, action = "rights_hold", "pause_source_operations_and_request_exact_rights_decision"
    elif changes:
        decision, action = "semantic_review", "retain_both_and_route_all_changed_claims"
    elif parser_changed:
        decision, action = "parser_review", "requalify_parser_version_before_publication"
    elif byte_changed:
        decision, action = "byte_only_review", "verify_parser_coverage_no_unrestricted_refetch"
    else:
        decision, action = "unchanged", "retain_last_known_no_automatic_publication"

    impact_classes = {item["kind"] for c in changes for item in (c["before"], c["after"]) if item}
    if any(_evidence_changed(c["before"], c["after"]) for c in changes):
        impact_classes.add("evidence")
    result = {
        "schema_version": _VERSION,
        "synthetic": True,
        "publication_eligible": False,
        "source_id": old["source_id"],
        "material_id": old["material_id"],
        "previous": old,
        "current": new,
        "cause_flags": causes,
        "impact_classes": sorted(impact_classes),
        "changes": changes,
        "decision": decision,
        "requires_review": decision != "unchanged",
        "next_action": action,
    }
    if next(output_validator.iter_errors(result), None) is not None:
        raise ChangeError("internal change-set schema violation: validation failed") from None
    return result
