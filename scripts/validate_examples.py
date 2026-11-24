#!/usr/bin/env python3
"""Offline draft-contract conformance, never a real publication authorizer."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
import math
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_MAP = {
    "synthetic-model.json": "catalog-record.schema.json",
    "synthetic-hardware.json": "catalog-record.schema.json",
    "synthetic-paper.json": "catalog-record.schema.json",
    "synthetic-source-rights.json": "source-use-decision.schema.json",
    "synthetic-release.json": "release-manifest.schema.json",
}


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_constant(value):
    raise ValueError(f"non-JSON number: {value}")


def read_json(path):
    return json.loads(Path(path).read_text(), object_pairs_hook=_unique_object,
                      parse_constant=_reject_constant)


def schema_errors(instance, schema):
    try:
        from jsonschema import Draft202012Validator, FormatChecker
    except ImportError as exc:
        raise RuntimeError("Install requirements-validation.txt before validation.") from exc
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    return [f"{'/'.join(map(str, error.absolute_path)) or '$'}: {error.message}"
            for error in sorted(validator.iter_errors(instance), key=lambda e: str(list(e.absolute_path)))]


def _synthetic_identity(value):
    """Require reserved synthetic identifiers, not only a synthetic=true flag."""
    return type(value) is str and re.fullmatch(r"urn:pya:synthetic:[a-z0-9][a-z0-9:._-]*", value) is not None


def _reserved_example_url(value):
    """Accept only byte-for-byte canonical reserved-host fixture URLs.

    urlsplit can silently remove ASCII control characters and empty delimiters,
    so compare its round trip with the original string before accepting.
    """
    if type(value) is not str:
        return False
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    # A URI path is slash-separated pchar segments; pchar includes only
    # unreserved, sub-delimiter, colon, at-sign, or complete percent triplets.
    if re.fullmatch(
            r"(?:[A-Za-z0-9\-._~!$&'()*+,;=:@/]|%[0-9A-Fa-f]{2})*",
            parsed.path) is None:
        return False
    return (parsed.scheme == "https" and parsed.netloc == "example.invalid" and
            not parsed.query and not parsed.fragment and parsed.geturl() == value)


def _bounded_fixture_data(value):
    """Bound schema work and reject non-JSON containers before inspecting scope.

    These are offline fixture ceilings, not production parser guarantees. Cycles
    also terminate at the depth/node bounds. Never invoke payload-defined methods.
    """
    stack = [(value, 0)]
    nodes = text_bytes = 0
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if nodes > 10_000 or depth > 32:
            return False
        kind = type(item)
        if kind is dict or kind is list:
            # Bound queued work before allocating children. Dicts enqueue both
            # their keys and values, not just the number of entries.
            pending = len(item) * (2 if kind is dict else 1)
            if nodes + len(stack) + pending > 10_000:
                return False
            if kind is dict:
                if any(type(key) is not str for key in item):
                    return False
                stack.extend((key, depth + 1) for key in item)
                stack.extend((child, depth + 1) for child in item.values())
            else:
                stack.extend((child, depth + 1) for child in item)
        elif kind is str:
            if len(item) > 1_048_576:
                return False
            try:
                text_bytes += len(item.encode("utf-8", errors="strict"))
            except UnicodeEncodeError:
                return False
            if text_bytes > 1_048_576:
                return False
        elif kind is int:
            if item.bit_length() > 4096:
                return False
        elif kind is float:
            if not math.isfinite(item):
                return False
        elif kind is not bool and kind is not type(None):
            return False
    return True


def _valid_utc_timestamp(value):
    if type(value) is not str or re.fullmatch(
            r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}(?:\.[0-9]+)?Z",
            value) is None:
        return False
    try:
        datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError:
        return False
    return True


def _fixture_dates_are_valid(value):
    """Inspect already-bounded JSON without allocating input-derived paths."""
    stack = [value]
    while stack:
        item = stack.pop()
        if type(item) is dict:
            for key, child in item.items():
                if key.endswith("_at") and not _valid_utc_timestamp(child):
                    return False
                if type(child) is dict or type(child) is list:
                    stack.append(child)
        elif type(item) is list:
            stack.extend(item)
    return True


def fixture_policy_decision(records, decisions, operation, product_id, *, production=False):
    """Demonstrate exact-scope fail-closed behavior with synthetic fixtures only.

    It intentionally cannot authorize real acquisition, real publication or a
    production channel. Every source behind every selected claim must match a
    scoped permission for the requested operation. Missing, conflicting and
    conditional grants are rejected; the caller cannot assert conditions met.
    """
    reasons = []
    if production is not False:
        return False, ["The offline bootstrap gate cannot authorize production."]
    allowed_ops = {"retrieve", "retain", "display", "redistribute", "commercial_use", "derive"}
    if type(operation) is not str or operation not in allowed_ops:
        return False, ["Unknown operation is denied."]
    if type(records) is not list or type(decisions) is not list or not records or not decisions:
        return False, ["Empty records or source-use decisions cannot authorize an operation."]
    if not _bounded_fixture_data([records, decisions]):
        return False, ["Malformed or oversized fixture data is denied."]
    if not _fixture_dates_are_valid([records, decisions]):
        return False, ["Fixture dates require explicit valid UTC timestamps."]
    for items, schema_name in ((records, "catalog-record.schema.json"),
                               (decisions, "source-use-decision.schema.json")):
        schema = read_json(ROOT / "schemas/v0.1" / schema_name)
        if any(schema_errors(item, schema) for item in items):
            return False, ["Fixture data does not satisfy its declared draft schema."]
    if any(item.get("synthetic") is not True for item in records + decisions):
        return False, ["Only explicitly synthetic fixtures are supported by this offline gate."]
    if not _synthetic_identity(product_id):
        return False, ["An offline product scope must have a reserved synthetic identity."]
    for record in records:
        claim_paths = [claim["path"] for claim in record["claims"]]
        if len(set(claim_paths)) != len(claim_paths):
            return False, ["Duplicate claim paths within a record are denied."]
        if not _synthetic_identity(record.get("id")):
            return False, ["An offline record must have a reserved synthetic identity."]
        if any(not _synthetic_identity(relationship["target_id"])
               for relationship in record["relationships"]):
            return False, ["An offline relationship target must have a reserved synthetic identity."]
        for claim in record.get("claims", []):
            if not _synthetic_identity(claim.get("id")):
                return False, ["An offline claim must have a reserved synthetic identity."]
            evidence = claim["evidence"]
            if "receipt_ref" in evidence and not _synthetic_identity(evidence["receipt_ref"]):
                return False, ["An offline evidence receipt must have a reserved synthetic identity."]
            for source in claim.get("sources", []):
                if not all(_synthetic_identity(source.get(key))
                           for key in ("source_id", "material_id")):
                    return False, ["An offline source and material must have synthetic identities."]
                if not _reserved_example_url(source["url"]):
                    return False, ["Only reserved offline source URLs are supported."]
    for decision in decisions:
        authority = decision["authority_ref"]
        if not (_reserved_example_url(authority) or _synthetic_identity(authority)):
            return False, ["An offline authority reference must remain reserved and synthetic."]
        if not _synthetic_identity(decision["reviewer_ref"]):
            return False, ["An offline reviewer must have a reserved synthetic identity."]
        operation_names = [entry["operation"] for entry in decision["operations"]]
        if len(set(operation_names)) != len(operation_names):
            return False, ["Ambiguous duplicate source-use operations are denied."]
        scope = decision.get("scope", {})
        if not _synthetic_identity(decision.get("id")) or not all(
                _synthetic_identity(scope.get(key))
                for key in ("source_id", "material_id", "product_id")) or not all(
                _synthetic_identity(identity) for identity in scope.get("record_ids", [])):
            return False, ["An offline source-use decision must have synthetic identities."]
    identities = [record["id"] for record in records] + [decision["id"] for decision in decisions]
    identities.extend(claim["id"] for record in records for claim in record["claims"])
    if len(set(identities)) != len(identities):
        return False, ["Denied: ambiguous overlapping decisions or duplicate fixture identities."]
    for record in records:
        if not record.get("claims"):
            reasons.append(f"{record.get('id')}: missing claims")
        for claim in record.get("claims", []):
            if not claim.get("sources"):
                reasons.append(f"{claim.get('id')}: missing source attribution")
            for source in claim.get("sources", []):
                matching = [decision for decision in decisions
                            if decision.get("scope", {}).get("source_id") == source.get("source_id")
                            and decision.get("scope", {}).get("material_id") == source.get("material_id")
                            and decision.get("scope", {}).get("product_id") == product_id
                            and record.get("id") in decision.get("scope", {}).get("record_ids", [])
                            and claim.get("path") in decision.get("scope", {}).get("claim_paths", [])]
                if not matching:
                    reasons.append(f"{claim.get('id')}: no permission for exact source/material/product/field")
                    continue
                if len(matching) != 1:
                    reasons.append(f"{claim.get('id')}: ambiguous overlapping source-use decisions")
                    continue
                decision = matching[0]
                operations = [o for o in decision.get("operations", []) if o.get("operation") == operation]
                if decision.get("withdrawn") or len(operations) != 1:
                    reasons.append(f"{claim.get('id')}: withdrawn or ambiguous operation permission")
                elif operations[0].get("decision") != "permit" or operations[0].get("conditions"):
                    reasons.append(f"{claim.get('id')}: {operation} is not unconditionally permitted")
    return not reasons, reasons


def _check_dates(value, errors, prefix=""):
    if isinstance(value, dict):
        for key, item in value.items():
            if key.endswith("_at"):
                if not _valid_utc_timestamp(item):
                    errors.append(f"{prefix}{key}: invalid explicit UTC timestamp")
            _check_dates(item, errors, prefix + key + "/")
    elif isinstance(value, list):
        for i, item in enumerate(value):
            _check_dates(item, errors, prefix + str(i) + "/")


def validate(root=ROOT):
    root = Path(root).resolve()
    errors = []
    loaded = {}
    expected_paths = {root / "examples" / name for name in SCHEMA_MAP}
    actual_paths = set((root / "examples").rglob("*.json"))
    for extra in sorted(actual_paths - expected_paths):
        errors.append(f"{extra.relative_to(root)}: unregistered example has no explicit schema and synthetic validation")
    for name, schema_name in SCHEMA_MAP.items():
        try:
            instance = read_json(root / "examples" / name)
            schema = read_json(root / "schemas/v0.1" / schema_name)
            errors.extend(f"{name}: {message}" for message in schema_errors(instance, schema))
            if instance.get("synthetic") is not True:
                errors.append(f"{name}: bootstrap examples must retain synthetic=true")
            if not instance.get("id", "").startswith("urn:pya:synthetic:"):
                errors.append(f"{name}: fixture identity must be explicitly synthetic")
            _check_dates(instance, errors, name + ":")
            loaded[name] = instance
        except (OSError, ValueError, RuntimeError) as exc:
            errors.append(f"{name}: {exc}")
    if len(loaded) != len(SCHEMA_MAP):
        return errors
    if errors:
        return errors  # Do not continue semantic checks on malformed input.

    records = [loaded[name] for name in SCHEMA_MAP if name not in {"synthetic-source-rights.json", "synthetic-release.json"}]
    rights = loaded["synthetic-source-rights.json"]
    release = loaded["synthetic-release.json"]
    all_ids = []
    for record in records:
        all_ids.append(record["id"])
        claim_paths = []
        for claim in record["claims"]:
            all_ids.append(claim["id"])
            claim_paths.append(claim["path"])
            if claim["evidence"]["verification"] == "independently_reproduced":
                errors.append(f"{claim['id']}: bootstrap claims cannot be independently reproduced")
            for source in claim["sources"]:
                if not _reserved_example_url(source["url"]):
                    errors.append(f"{claim['id']}: examples require credential-free reserved source URLs")
        if len(set(claim_paths)) != len(claim_paths):
            errors.append(f"{record['id']}: duplicate claim path")
    all_ids.extend([rights["id"], release["id"]])
    if len(set(all_ids)) != len(all_ids):
        errors.append("duplicate fixture or claim identity")
    operations = [op["operation"] for op in rights["operations"]]
    if len(set(operations)) != len(operations):
        errors.append("duplicate source-use operation")
    if release["rights_decision_ids"] != [rights["id"]]:
        errors.append("release has missing or unpinned fixture rights decision")
    expected_ids = {r["id"] for r in records}
    if set(rights["scope"]["record_ids"]) != expected_ids:
        errors.append("source-use record scope does not match synthetic records")
    if set(a["record_id"] for a in release["artifacts"]) != expected_ids or len(release["artifacts"]) != len(records):
        errors.append("release artifact set is missing, duplicated or extraneous")
    by_id = {r["id"]: r for r in records}
    validated_paths = {loaded[name]["id"]: "examples/" + name
                       for name in SCHEMA_MAP
                       if name not in {"synthetic-source-rights.json", "synthetic-release.json"}}
    for artifact in release["artifacts"]:
        path = (root / artifact["path"]).resolve()
        if not path.is_relative_to(root / "examples"):
            errors.append("release artifact path escaped examples")
            continue
        if artifact["record_id"] not in by_id or artifact["revision"] != by_id[artifact["record_id"]]["revision"]:
            errors.append("release artifact identity or revision mismatch")
        if artifact["path"] != validated_paths.get(artifact["record_id"]):
            errors.append("release artifact does not reference the exact validated fixture path")
        try:
            if hashlib.sha256(path.read_bytes()).hexdigest() != artifact["sha256"]:
                errors.append(f"{artifact['path']}: checksum mismatch")
            referenced = read_json(path)
            if referenced.get("id") != artifact["record_id"] or referenced.get("revision") != artifact["revision"]:
                errors.append(f"{artifact['path']}: record identity or revision mismatch")
        except (OSError, ValueError) as exc:
            errors.append(f"{artifact['path']}: {exc}")
    permitted, _ = fixture_policy_decision(records, [rights], "display", rights["scope"]["product_id"])
    if not permitted:
        errors.append("expected narrow synthetic display case was denied")
    for operation in ["retrieve", "redistribute", "commercial_use"]:
        permitted, _ = fixture_policy_decision(records, [rights], operation, rights["scope"]["product_id"])
        if permitted:
            errors.append(f"unknown {operation} permission was incorrectly accepted")
    permitted, _ = fixture_policy_decision(records, [rights], "display", rights["scope"]["product_id"], production=True)
    if permitted:
        errors.append("synthetic fixture was promoted to production")
    return errors


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args(argv)
    errors = validate(args.root)
    if errors:
        print("Example validation failed:", file=sys.stderr)
        for message in errors:
            print("- " + message, file=sys.stderr)
        return 1
    print("PASS: 3 draft schemas, 5 synthetic examples, byte-integrity and rejection checks; no production eligibility.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
