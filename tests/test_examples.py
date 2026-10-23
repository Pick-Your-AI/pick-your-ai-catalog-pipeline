"""Meaningful negative tests for the draft fixture admission boundary."""
from copy import deepcopy
import importlib.util
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("example_validation", ROOT / "scripts/validate_examples.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ExampleBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.record = MODULE.read_json(ROOT / "examples/synthetic-model.json")
        self.rights = MODULE.read_json(ROOT / "examples/synthetic-source-rights.json")
        self.product = self.rights["scope"]["product_id"]

    def decision(self, records=None, rights=None, op="display", product=None, production=False):
        return MODULE.fixture_policy_decision(records or [self.record], rights if rights is not None else [self.rights],
                                              op, product or self.product, production=production)[0]

    def test_committed_examples_pass(self):
        self.assertEqual(MODULE.validate(ROOT), [])

    def test_known_synthetic_display_is_scoped(self):
        self.assertTrue(self.decision())
        self.assertFalse(self.decision(product="urn:pya:synthetic:product:other"))
        self.record["claims"][0]["path"] = "spec.unapproved_field"
        self.assertFalse(self.decision())

    def test_missing_unknown_conditional_and_revoked_rights_deny(self):
        self.assertFalse(self.decision(rights=[]))
        self.assertFalse(self.decision(op="redistribute"))
        for status in ["conditional", "unknown", "deny", "revoked"]:
            grant = deepcopy(self.rights)
            next(o for o in grant["operations"] if o["operation"] == "display")["decision"] = status
            self.assertFalse(self.decision(rights=[grant]))
        grant = deepcopy(self.rights)
        grant["withdrawn"] = True
        self.assertFalse(self.decision(rights=[grant]))

    def test_synthetic_and_non_synthetic_cannot_be_production_authorized(self):
        self.assertFalse(self.decision(production=True))
        self.record["synthetic"] = False
        self.rights["synthetic"] = False
        self.assertFalse(self.decision())
        self.assertFalse(self.decision(production=True))

    def test_mixed_source_record_does_not_inherit_permission(self):
        self.record["claims"][0]["sources"].append({**self.record["claims"][0]["sources"][0],
                                                   "source_id": "urn:pya:synthetic:source:restricted"})
        self.assertFalse(self.decision())

    def test_material_scope_and_conditions_cannot_be_bypassed(self):
        grant = deepcopy(self.rights)
        grant["scope"]["material_id"] = "urn:pya:synthetic:material:different"
        self.assertFalse(self.decision(rights=[grant]))
        grant = deepcopy(self.rights)
        next(o for o in grant["operations"] if o["operation"] == "display")["conditions"] = ["Unfulfilled condition"]
        self.assertFalse(self.decision(rights=[grant]))

    def test_conflicting_grant_denies_even_if_one_source_permits(self):
        deny = deepcopy(self.rights)
        next(o for o in deny["operations"] if o["operation"] == "display")["decision"] = "deny"
        self.assertFalse(self.decision(rights=[self.rights, deny]))

    def test_unknown_claim_cannot_contain_invented_zero(self):
        schema = MODULE.read_json(ROOT / "schemas/v0.1/catalog-record.schema.json")
        self.record["claims"][1]["value"] = 0
        self.assertTrue(MODULE.schema_errors(self.record, schema))

    def test_decimal_requires_exact_string(self):
        schema = MODULE.read_json(ROOT / "schemas/v0.1/catalog-record.schema.json")
        self.record["claims"][0].update(value_type="decimal", value=0.01)
        self.assertTrue(MODULE.schema_errors(self.record, schema))
        self.record["claims"][0]["value"] = "0.0100"
        self.assertEqual(MODULE.schema_errors(self.record, schema), [])

    def test_release_cannot_erase_synthetic_boundary(self):
        schema = MODULE.read_json(ROOT / "schemas/v0.1/release-manifest.schema.json")
        release = MODULE.read_json(ROOT / "examples/synthetic-release.json")
        release.update(channel="production", publication_eligible=True)
        self.assertTrue(MODULE.schema_errors(release, schema))

    def test_tampered_bytes_and_path_traversal_fail(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(ROOT / "examples", root / "examples")
            shutil.copytree(ROOT / "schemas/v0.1", root / "schemas/v0.1")
            path = root / "examples/synthetic-model.json"
            path.write_text(path.read_text() + " ")
            self.assertTrue(any("checksum mismatch" in e for e in MODULE.validate(root)))
            release_path = root / "examples/synthetic-release.json"
            release = json.loads(release_path.read_text())
            release["artifacts"][0]["path"] = "../outside.json"
            release_path.write_text(json.dumps(release))
            self.assertTrue(MODULE.validate(root))

    def test_duplicate_json_keys_and_nonfinite_numbers_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "input.json"
            for data in ['{"synthetic":true,"synthetic":false}', '{"value":NaN}']:
                path.write_text(data)
                with self.assertRaises(ValueError):
                    MODULE.read_json(path)

    def test_release_cannot_substitute_unvalidated_same_id_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(ROOT / "examples", root / "examples")
            shutil.copytree(ROOT / "schemas/v0.1", root / "schemas/v0.1")
            substituted = deepcopy(self.record)
            substituted.update(revision=99, synthetic=False, claims=[])
            path = root / "examples/substituted-model.json"
            path.write_text(json.dumps(substituted))
            release_path = root / "examples/synthetic-release.json"
            release = json.loads(release_path.read_text())
            release["artifacts"][0].update(path="examples/substituted-model.json",
                                            sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            release_path.write_text(json.dumps(release))
            self.assertTrue(MODULE.validate(root))


if __name__ == "__main__":
    unittest.main()
