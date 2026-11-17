"""Offline draft conformance only; every generated record and grant is fictional."""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "contract_example_validation", ROOT / "scripts/validate_examples.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

# Independent scenarios exercise the shared envelope, not domain truth or a
# builder mapping. No fixture implies that this draft has domain-specific rules.
DOMAIN_CLAIMS = (
    ("model_family", "metadata.family", "string", "Fictional Aurora"),
    ("model_release", "metadata.version", "string", "fictional-1"),
    ("model_artifact", "metadata.format", "string", "fictional-format"),
    ("provider", "metadata.name", "string", "Fictional provider"),
    ("provider_offering", "offering.region", "string", "fictional-region"),
    ("hardware", "spec.memory_gib", "integer", 8),
    ("device", "spec.memory_gib", "integer", 4),
    ("runtime", "metadata.version", "string", "fictional-2"),
    ("dataset", "metadata.name", "string", "Fictional dataset"),
    ("dataset_release", "metadata.split", "string", "fictional-test"),
    ("benchmark_suite", "metadata.version", "string", "fictional-1"),
    ("benchmark_run", "metadata.run_id", "string", "fictional-run"),
    ("application", "metadata.name", "string", "Fictional application"),
    ("service", "metadata.name", "string", "Fictional service"),
    ("agent_framework", "metadata.version", "string", "fictional-3"),
    ("tool", "metadata.name", "string", "Fictional tool"),
    ("mcp_server", "metadata.version", "string", "fictional-1"),
    ("integration", "metadata.name", "string", "Fictional integration"),
    ("memory_store", "metadata.name", "string", "Fictional store"),
    ("paper", "metadata.title", "string", "Fictional paper"),
    ("method", "metadata.name", "string", "Fictional method"),
    ("organization", "metadata.name", "string", "Fictional organization"),
    ("use_case", "metadata.name", "string", "Fictional use case"),
    ("trust_attribute", "metadata.scope", "string", "fictional-scope"),
    ("cost_observation", "price.amount", "decimal", "0.0100"),
    ("energy_observation", "energy.amount", "decimal", "1.2500"),
    ("learning_resource", "metadata.title", "string", "Fictional guide"),
)


class ContractConformanceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        shutil.copytree(ROOT / "examples", self.root / "examples")
        shutil.copytree(ROOT / "schemas/v0.1", self.root / "schemas/v0.1")
        self.record = self.read("synthetic-model.json")
        self.record_schema = MODULE.read_json(
            ROOT / "schemas/v0.1/catalog-record.schema.json")

    def read(self, name):
        return MODULE.read_json(self.root / "examples" / name)

    def write(self, name, value):
        path = self.root / "examples" / name
        path.write_text(json.dumps(value, ensure_ascii=False) + "\n", encoding="utf-8")
        return path

    def replace_record(self, record):
        """Keep packet references/hash valid so tests isolate the intended fault."""
        old_id = self.read("synthetic-model.json")["id"]
        path = self.write("synthetic-model.json", record)
        rights = self.read("synthetic-source-rights.json")
        rights["scope"]["record_ids"] = [
            record["id"] if value == old_id else value
            for value in rights["scope"]["record_ids"]]
        rights["scope"]["claim_paths"] = sorted(set(
            rights["scope"]["claim_paths"] + [claim["path"] for claim in record["claims"]]))
        self.write("synthetic-source-rights.json", rights)
        release = self.read("synthetic-release.json")
        artifact = next(a for a in release["artifacts"]
                        if a["path"] == "examples/synthetic-model.json")
        artifact.update(record_id=record["id"], revision=record["revision"],
                        sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        self.write("synthetic-release.json", release)

    def assert_rejected_at(self, value, schema, location):
        errors = MODULE.schema_errors(value, schema)
        self.assertTrue(errors, f"Expected rejection at {location}")
        self.assertTrue(any(error.startswith(location + ":") for error in errors), errors)

    def test_every_declared_domain_has_a_valid_packet_and_requires_evidence(self):
        for kind, claim_path, value_type, value in DOMAIN_CLAIMS:
            with self.subTest(kind=kind):
                record = deepcopy(self.record)
                record.update(id=f"urn:pya:synthetic:{kind}:conformance:1",
                              entity_kind=kind, display_name=f"Fictional {kind}")
                claim = record["claims"][0]
                claim.update(id=record["id"] + ":claim:1", path=claim_path,
                             value_type=value_type, value=value)
                claim.pop("unit", None)
                record["claims"] = [claim]
                self.replace_record(record)
                self.assertEqual(MODULE.validate(self.root), [])
                # Correct hashes and grants cannot rescue a missing evidence basis.
                del claim["evidence"]["basis"]
                self.replace_record(record)
                self.assertTrue(any("claims/0/evidence" in error
                                    for error in MODULE.validate(self.root)))

    def test_unsupported_wire_versions_fail_for_each_document_type(self):
        for name, schema_name in MODULE.SCHEMA_MAP.items():
            value = self.read(name)
            schema = MODULE.read_json(ROOT / "schemas/v0.1" / schema_name)
            for version in ("1.0.0", "catalog-pipeline-draft-99.0.0", ""):
                with self.subTest(document=name, version=version):
                    changed = deepcopy(value)
                    changed["schema_version"] = version
                    self.assert_rejected_at(changed, schema, "schema_version")

    def test_typed_claims_preserve_false_zero_and_exact_decimal_strings(self):
        cases = (("integer", 0, [False, "0", 0.5]),
                 ("boolean", False, [0, "false", None]),
                 ("decimal", "-0.0100", ["1e-2", "01.0", ".1", "1."]),
                 ("string", "Fictional value", [0, False, ""]))
        for kind, valid, invalid_values in cases:
            with self.subTest(value_type=kind):
                record = deepcopy(self.record)
                record["claims"][0].update(value_type=kind, value=valid)
                self.assertEqual(MODULE.schema_errors(record, self.record_schema), [])
                for invalid in invalid_values:
                    with self.subTest(value=invalid):
                        record["claims"][0]["value"] = invalid
                        self.assert_rejected_at(record, self.record_schema, "claims/0/value")

    def test_known_values_cannot_carry_unknown_reasons_or_omit_values(self):
        for known_type, value in (("integer", 1), ("boolean", False),
                                  ("decimal", "0.0"), ("string", "fictional")):
            with self.subTest(value_type=known_type):
                record = deepcopy(self.record)
                claim = record["claims"][0]
                claim.update(value_type=known_type, value=value,
                             unknown_reason="Fictional contradiction")
                self.assert_rejected_at(record, self.record_schema, "claims/0")
                del claim["unknown_reason"]
                del claim["value"]
                self.assert_rejected_at(record, self.record_schema, "claims/0")

    def test_unknown_requires_a_nonempty_explanation(self):
        for reason in (None, ""):
            with self.subTest(reason=reason):
                record = deepcopy(self.record)
                claim = record["claims"][1]
                if reason is None:
                    del claim["unknown_reason"]
                    location = "claims/1"
                else:
                    claim["unknown_reason"] = reason
                    location = "claims/1/unknown_reason"
                self.assert_rejected_at(record, self.record_schema, location)

    def test_unversioned_extension_fields_do_not_gain_authority(self):
        for location in ((), ("claims", 0), ("claims", 0, "evidence"),
                         ("claims", 0, "sources", 0)):
            with self.subTest(location=location):
                record = deepcopy(self.record)
                target = record
                for key in location:
                    target = target[key]
                target["approved_for_publication"] = True
                path = "/".join(map(str, location)) or "$"
                self.assert_rejected_at(record, self.record_schema, path)

    def test_relationships_require_exact_revision_and_legal_reference_shape(self):
        # This checks wire shape only, not graph resolution or kind compatibility.
        relationship = {"relation": "cites", "target_id":
                        "urn:pya:synthetic:paper:synthetic-paper:1", "target_revision": 1}
        record = deepcopy(self.record)
        record["relationships"] = [relationship]
        self.assertEqual(MODULE.schema_errors(record, self.record_schema), [])
        for field, value in (("target_revision", 0), ("target_revision", "latest"),
                             ("target_id", "https://example.invalid/current"),
                             ("relation", "automatically_compatible_with")):
            with self.subTest(field=field, value=value):
                record["relationships"] = [{**relationship, field: value}]
                self.assert_rejected_at(record, self.record_schema,
                                        "relationships/0/" + field)
        record["relationships"] = [{k: v for k, v in relationship.items()
                                     if k != "target_revision"}]
        self.assert_rejected_at(record, self.record_schema, "relationships/0")

    def test_bootstrap_requires_label_and_reserved_identity_in_all_documents(self):
        for name in MODULE.SCHEMA_MAP:
            original = self.read(name)
            for fault in ("missing_label", "false_label", "real_looking_id"):
                with self.subTest(document=name, fault=fault):
                    value = deepcopy(original)
                    if fault == "missing_label":
                        del value["synthetic"]
                    elif fault == "false_label":
                        value["synthetic"] = False
                    else:
                        value["id"] = "urn:pya:catalog:unqualified:1"
                    self.write(name, value)
                    errors = MODULE.validate(self.root)
                    self.assertTrue(any(name in error and "synthetic" in error
                                        for error in errors), errors)
                    self.write(name, original)

    def test_fictional_receipt_or_signature_cannot_approve_synthetic_release(self):
        original = self.read("synthetic-release.json")
        schema = MODULE.read_json(ROOT / "schemas/v0.1/release-manifest.schema.json")
        for field, value in (("publication_eligible", True),
                             ("signature", "fictional-not-a-signature"),
                             ("approvals", [{"reviewer_ref": "urn:pya:synthetic:reviewer:test",
                                             "scope": "fictional-only",
                                             "receipt_ref": "urn:pya:synthetic:receipt:test"}])):
            with self.subTest(field=field):
                release = deepcopy(original)
                release[field] = value
                self.assert_rejected_at(release, schema, field)

    def test_manifest_rejects_wrong_revision_or_incomplete_duplicate_artifact_set(self):
        original = self.read("synthetic-release.json")
        mutations = (
            ("revision", "release artifact identity or revision mismatch"),
            ("missing", "release artifact set is missing, duplicated or extraneous"),
            ("duplicate", "release artifact set is missing, duplicated or extraneous"),
            ("rights", "release has missing or unpinned fixture rights decision"),
        )
        for fault, diagnostic in mutations:
            with self.subTest(fault=fault):
                release = deepcopy(original)
                if fault == "revision":
                    release["artifacts"][0]["revision"] += 1
                elif fault == "missing":
                    release["artifacts"].pop()
                elif fault == "duplicate":
                    release["artifacts"].append(deepcopy(release["artifacts"][0]))
                else:
                    release["rights_decision_ids"] = ["urn:pya:synthetic:rights:other:1"]
                self.write("synthetic-release.json", release)
                self.assertIn(diagnostic, MODULE.validate(self.root))

    def test_duplicate_claim_identity_and_field_path_are_diagnosed(self):
        for field, diagnostic in (("id", "duplicate fixture or claim identity"),
                                  ("path", ": duplicate claim path")):
            with self.subTest(field=field):
                record = deepcopy(self.record)
                record["claims"][1][field] = record["claims"][0][field]
                self.replace_record(record)
                self.assertTrue(any(diagnostic in error
                                    for error in MODULE.validate(self.root)))

    def test_unknown_entity_kind_fails_without_importing_builder_semantics(self):
        for kind in ("unknown_future_kind", "llm"):
            with self.subTest(kind=kind):
                record = deepcopy(self.record)
                record["entity_kind"] = kind
                self.assert_rejected_at(record, self.record_schema, "entity_kind")


if __name__ == "__main__":
    unittest.main()
