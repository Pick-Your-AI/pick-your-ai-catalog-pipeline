#!/usr/bin/env python3
"""Offline draft-contract conformance, never a real publication authorizer."""
from __future__ import annotations

import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
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


def fixture_policy_decision(records, decisions, operation, product_id, *, production=False):
    """Demonstrate exact-scope fail-closed behavior with synthetic fixtures only.

    It intentionally cannot authorize real acquisition, real publication or a
    production channel. Every source behind every selected claim must match a
    scoped permission for the requested operation. Missing, conflicting and
    conditional grants are rejected; the caller cannot assert conditions met.
    """
    reasons = []
    if production:
        return False, ["The offline bootstrap gate cannot authorize production."]
    if not records or not decisions:
        return False, ["Empty records or source-use decisions cannot authorize an operation."]
    if any(item.get("synthetic") is not True for item in records + decisions):
        return False, ["Only explicitly synthetic fixtures are supported by this offline gate."]
    allowed_ops = {"retrieve", "retain", "display", "redistribute", "commercial_use", "derive"}
    if operation not in allowed_ops:
        return False, ["Unknown operation is denied."]
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
                for decision in matching:
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
                try:
                    if not isinstance(item, str) or not item.endswith("Z"):
                        raise ValueError("expected UTC Z timestamp")
                    datetime.fromisoformat(item.replace("Z", "+00:00"))
                except ValueError:
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
                parsed = urlsplit(source["url"])
                if parsed.hostname != "example.invalid" or parsed.username or parsed.password or parsed.query:
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
