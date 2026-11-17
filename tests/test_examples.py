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

    def test_duplicate_grant_is_ambiguous_even_if_both_permit(self):
        allowed, reasons = MODULE.fixture_policy_decision(
            [self.record], [self.rights, deepcopy(self.rights)], "display", self.product
        )
        self.assertFalse(allowed)
        self.assertTrue(any("ambiguous overlapping" in reason for reason in reasons))

    def test_synthetic_marker_cannot_approve_non_synthetic_identities(self):
        for kind in ("product", "record", "claim", "source", "material", "decision"):
            with self.subTest(kind=kind):
                record, rights = deepcopy(self.record), deepcopy(self.rights)
                if kind == "product":
                    rights["scope"]["product_id"] = "urn:pya:real:product:1"
                elif kind == "record":
                    before = record["id"]
                    record["id"] = "urn:pya:real:record:1"
                    rights["scope"]["record_ids"] = [
                        record["id"] if entry == before else entry
                        for entry in rights["scope"]["record_ids"]
                    ]
                elif kind == "claim":
                    record["claims"][0]["id"] = "urn:pya:real:claim:1"
                elif kind == "source":
                    record["claims"][0]["sources"][0]["source_id"] = "urn:pya:real:source:1"
                    rights["scope"]["source_id"] = "urn:pya:real:source:1"
                elif kind == "material":
                    record["claims"][0]["sources"][0]["material_id"] = "urn:pya:real:material:1"
                    rights["scope"]["material_id"] = "urn:pya:real:material:1"
                else:
                    rights["id"] = "urn:pya:real:rights:1"
                allowed, reasons = MODULE.fixture_policy_decision(
                    [record], [rights], "display", rights["scope"]["product_id"]
                )
                self.assertFalse(allowed, (kind, reasons))

    def test_direct_gate_rejects_string_scope_instead_of_exact_path_list(self):
        rights = deepcopy(self.rights)
        # Both requested paths are substrings, but neither has an array grant.
        rights["scope"]["claim_paths"] = "prefix:" + ",".join(
            claim["path"] for claim in self.record["claims"]
        ) + ":suffix"
        allowed, reasons = MODULE.fixture_policy_decision(
            [self.record], [rights], "display", self.product
        )
        self.assertFalse(allowed, reasons)

    def test_direct_gate_rejects_malformed_nested_contract_shapes(self):
        cases = [
            ("record", ("claims",), {}),
            ("record", ("claims",), [None]),
            ("record", ("claims", 0, "sources"), "source"),
            ("record", ("claims", 0, "sources"), [False]),
            ("record", ("claims", 0, "path"), ["spec.context_tokens"]),
            ("record", ("claims", 0, "evidence"), []),
            ("record", ("synthetic",), 1),
            ("record", ("schema_version",), "unsupported"),
            ("record", ("lifecycle",), []),
            ("record", ("revision",), True),
            ("record", ("unexpected",), True),
            ("rights", ("scope",), []),
            ("rights", ("scope", "record_ids"), self.record["id"]),
            ("rights", ("scope", "record_ids"), [None]),
            ("rights", ("scope", "record_ids"), [self.record["id"], self.record["id"]]),
            ("rights", ("scope", "claim_paths"), {"spec.context_tokens": True}),
            ("rights", ("scope", "claim_paths"), []),
            ("rights", ("scope", "claim_paths"), [False]),
            ("rights", ("scope", "claim_paths"), ["spec.context_tokens"] * 2),
            ("rights", ("operations",), {"display": "permit"}),
            ("rights", ("operations",), "display"),
            ("rights", ("operations",), [None]),
            ("rights", ("operations", 2, "decision"), True),
            ("rights", ("operations", 2, "decision"), ["permit"]),
            ("rights", ("operations", 2, "decision"), "PERMIT"),
            ("rights", ("operations", 2, "conditions"), ""),
            ("rights", ("operations", 2, "conditions"), {}),
            ("rights", ("operations", 2, "conditions"), [None]),
            ("rights", ("operations", 2, "operation"), ["display"]),
            ("rights", ("withdrawn",), "false"),
            ("rights", ("withdrawn",), 0),
            ("rights", ("synthetic",), "true"),
            ("rights", ("decision_at",), "invalid-date"),
            ("rights", ("decision_at",), "2026-10-01T12:00:00+01:00"),
            ("rights", ("unexpected",), True),
        ]
        for target, path, value in cases:
            with self.subTest(target=target, path=path, value=value):
                record, rights = deepcopy(self.record), deepcopy(self.rights)
                parent = record if target == "record" else rights
                for key in path[:-1]:
                    parent = parent[key]
                parent[path[-1]] = value
                allowed, reasons = MODULE.fixture_policy_decision(
                    [record], [rights], "display", self.product
                )
                self.assertFalse(allowed, reasons)

    def test_direct_gate_requires_contract_fields_instead_of_defaulting(self):
        for target, field in (("record", "claims"), ("record", "schema_version"),
                              ("rights", "withdrawn"), ("rights", "synthetic"),
                              ("rights", "operations"), ("rights", "scope")):
            with self.subTest(target=target, field=field):
                record, rights = deepcopy(self.record), deepcopy(self.rights)
                del (record if target == "record" else rights)[field]
                self.assertFalse(MODULE.fixture_policy_decision(
                    [record], [rights], "display", self.product
                )[0])

    def test_direct_gate_rejects_invalid_top_level_containers_and_arguments(self):
        for value in (None, {}, "records", (), [None], [False], [[]]):
            for side in ("records", "decisions"):
                with self.subTest(side=side, value=value):
                    records = value if side == "records" else [self.record]
                    decisions = value if side == "decisions" else [self.rights]
                    allowed, reasons = MODULE.fixture_policy_decision(
                        records, decisions, "display", self.product
                    )
                    self.assertFalse(allowed, reasons)
        for operation in (None, [], {}, True, "DISPLAY", "unknown"):
            with self.subTest(operation=operation):
                self.assertFalse(MODULE.fixture_policy_decision(
                    [self.record], [self.rights], operation, self.product
                )[0])
        for production in (True, None, 0, [], {}, "false"):
            with self.subTest(production=production):
                self.assertFalse(MODULE.fixture_policy_decision(
                    [self.record], [self.rights], "display", self.product,
                    production=production
                )[0])

    def test_direct_gate_rejects_malformed_reserved_identities(self):
        for identity in ("urn:pya:synthetic:", "urn:pya:synthetic:bad id",
                         "urn:pya:synthetic:bad\n", "urn:pya:synthetic:UPPER",
                         "urn:pya:synthetic:bad/identity", None, []):
            with self.subTest(identity=identity):
                record, rights = deepcopy(self.record), deepcopy(self.rights)
                record["claims"][0]["sources"][0]["material_id"] = identity
                rights["scope"]["material_id"] = identity
                self.assertFalse(MODULE.fixture_policy_decision(
                    [record], [rights], "display", self.product
                )[0])
                self.assertFalse(MODULE.fixture_policy_decision(
                    [self.record], [self.rights], "display", identity
                )[0])

    def test_direct_gate_rejects_duplicate_authority_and_operation_identities(self):
        other_scope = deepcopy(self.rights)
        other_scope["scope"]["product_id"] = "urn:pya:synthetic:product:other"
        self.assertFalse(MODULE.fixture_policy_decision(
            [self.record], [self.rights, other_scope], "display", self.product
        )[0])
        other_grant = deepcopy(self.rights)
        other_grant["id"] += ":other"
        self.assertFalse(MODULE.fixture_policy_decision(
            [self.record], [self.rights, other_grant], "display", self.product
        )[0])
        duplicate_operation = deepcopy(self.rights)
        # Even duplicate unrequested operations make the decision ambiguous.
        duplicate_operation["operations"].append(deepcopy(duplicate_operation["operations"][0]))
        self.assertFalse(MODULE.fixture_policy_decision(
            [self.record], [duplicate_operation], "display", self.product
        )[0])

    def test_direct_gate_bounds_schema_work_and_rejects_non_json_values(self):
        cycle = []
        cycle.append(cycle)
        for value in (cycle, ["x"] * 10_001, "x" * 1_048_577,
                      object(), {"nested": {1: "non-string key"}},
                      float("inf"), float("nan"), 1 << 4097, "\ud800"):
            with self.subTest(kind=type(value).__name__):
                record = deepcopy(self.record)
                record["unknowns"] = value
                allowed, reasons = MODULE.fixture_policy_decision(
                    [record], [self.rights], "display", self.product
                )
                self.assertFalse(allowed, reasons)

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
