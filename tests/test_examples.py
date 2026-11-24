"""Meaningful negative tests for the draft fixture admission boundary."""
from copy import deepcopy
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import subprocess
import sys
import tracemalloc
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("example_validation", ROOT / "scripts/validate_examples.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _measure_date_rejection():
    """One measurement only; the caller supplies an untraced measurement process."""
    if tracemalloc.is_tracing():
        raise AssertionError("Measurement requires its own allocation tracer")
    record = MODULE.read_json(ROOT / "examples/synthetic-model.json")
    rights = MODULE.read_json(ROOT / "examples/synthetic-source-rights.json")
    record["x" * 16_384] = [{"bad_at": "bad"} for _ in range(1_000)]
    bounded = MODULE._bounded_fixture_data([[record], [rights]])
    tracemalloc.start()
    try:
        allowed, reasons = MODULE.fixture_policy_decision(
            [record], [rights], "display", rights["scope"]["product_id"])
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return {"bounded": bounded, "allowed": allowed, "reasons": len(reasons), "peak": peak}


def _measure_pending_fixture_work():
    """Measure the directly callable guard in its own allocation tracer."""
    if tracemalloc.is_tracing():
        raise AssertionError("Measurement requires its own allocation tracer")
    graph = 0
    for _ in range(31):
        graph = [graph] * 8_000
    tracemalloc.start()
    try:
        accepted = MODULE._bounded_fixture_data(graph)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    return {"accepted": accepted, "peak": peak}


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

    def test_direct_gate_rejects_non_rfc3339_utc_forms(self):
        timestamps = (
            "2026-11-19Z", "20261119T120000Z", "2026-11-19 12:00:00Z",
            "2026-11-19T12:00Z", "2026-11-19T12:00:00,25Z",
            "2026-W47-4T12:00:00Z", "2026-11-19T12:00:00+00:00Z",
        )
        for timestamp in timestamps:
            source = self.record["claims"][0]["sources"][0]
            for target, key in ((source, "observed_at"), (self.rights, "decision_at")):
                with self.subTest(timestamp=timestamp, field=key):
                    original = target[key]
                    target[key] = timestamp
                    try:
                        self.assertFalse(self.decision())
                    finally:
                        target[key] = original


    def test_direct_gate_accepts_complete_utc_seconds_and_fraction(self):
        for timestamp in (
            "2026-11-19T12:00:00Z", "2024-02-29T23:59:59.25Z",
            "2026-11-19T12:00:00.123456789Z",
        ):
            with self.subTest(timestamp=timestamp):
                self.record["claims"][0]["sources"][0]["observed_at"] = timestamp
                self.rights["decision_at"] = timestamp
                self.assertTrue(self.decision())


    def test_direct_gate_bounds_date_rejection_diagnostics(self):
        # Preserve the runner's tracer. A dedicated child owns its measurement
        # tracer even when its startup hook enables tracing before this command.
        if tracemalloc.is_tracing():
            env = dict(os.environ)
            env.pop("PYTHONTRACEMALLOC", None)
            command = [sys.executable, "-c",
                       "import json, tracemalloc; "
                       "from tests.test_examples import _measure_date_rejection; "
                       "tracemalloc.stop(); print(json.dumps(_measure_date_rejection()))"]
            result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True,
                                    text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(tracemalloc.is_tracing())
            measured = json.loads(result.stdout)
        else:
            measured = _measure_date_rejection()
        self.assertTrue(measured["bounded"])
        self.assertFalse(measured["allowed"])
        self.assertEqual(measured["reasons"], 1)
        self.assertLess(measured["peak"], 2_000_000,
                        "Rejecting bounded fixture dates must not amplify diagnostic paths")

    def test_date_measurement_terminates_with_tracing_on_every_interpreter_start(self):
        with tempfile.TemporaryDirectory(prefix="catalog-memory-fixture-") as directory:
            # Bound the regression itself to two child interpreter startups. An
            # accidental self-relaunch fails at startup instead of spawning on.
            startup = (
                "import os, sys, tracemalloc\n"
                "count = int(os.environ.get('CATALOG_FIXTURE_STARTUPS', '0'))\n"
                "if count >= 2: raise SystemExit(23)\n"
                "os.environ['CATALOG_FIXTURE_STARTUPS'] = str(count + 1)\n"
                "def deny_socket(event, args):\n"
                "    if event.startswith('socket.'): raise RuntimeError('offline fixture')\n"
                "sys.addaudithook(deny_socket)\n"
                "tracemalloc.start()\n"
            )
            (Path(directory) / "sitecustomize.py").write_text(startup)
            env = dict(os.environ)
            env.pop("PYTHONTRACEMALLOC", None)
            env["CATALOG_FIXTURE_STARTUPS"] = "0"
            env["PYTHONPATH"] = directory + os.pathsep + env.get("PYTHONPATH", "")
            command = [sys.executable, "-m", "unittest",
                       "tests.test_examples.ExampleBoundaryTests.test_direct_gate_bounds_date_rejection_diagnostics"]
            result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True,
                                    text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


    def test_direct_gate_rejects_mixed_review_evidence_and_relationship_identities(self):
        for scope in ("reviewer", "receipt", "relationship"):
            record, rights = deepcopy(self.record), deepcopy(self.rights)
            real_ref = "urn:pya:real:" + scope + ":synthetic-probe"
            if scope == "reviewer":
                rights["reviewer_ref"] = real_ref
            elif scope == "receipt":
                record["claims"][0]["evidence"]["receipt_ref"] = real_ref
            else:
                record["relationships"] = [{"relation": "cites", "target_id": real_ref,
                                             "target_revision": 1}]
            with self.subTest(scope=scope):
                self.assertFalse(self.decision(records=[record], rights=[rights]))


    def test_direct_gate_accepts_reserved_review_evidence_and_relationship_identities(self):
        self.rights["reviewer_ref"] = "urn:pya:synthetic:reviewer:fixture"
        self.record["claims"][0]["evidence"]["receipt_ref"] = "urn:pya:synthetic:receipt:fixture"
        self.record["relationships"] = [{"relation": "cites",
                                         "target_id": "urn:pya:synthetic:record:fixture-paper",
                                         "target_revision": 1}]
        self.assertTrue(self.decision())


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

    def test_direct_gate_rejects_nonreserved_rights_authority(self):
        # Schema URI-format validity is not proof of an offline authority.
        for authority in (
            "https://different.invalid/synthetic/rights",
            "https://example.invalid@different.invalid/synthetic/rights",
            "file:///tmp/synthetic-standin",
            "https://example.invalid/synthetic/rights?key=fake",
            "https://example.invalid/synthetic/rights\n",
        ):
            with self.subTest(authority=authority):
                rights = deepcopy(self.rights)
                rights["authority_ref"] = authority
                allowed, reasons = MODULE.fixture_policy_decision(
                    [self.record], [rights], "display", self.product)
                self.assertFalse(allowed)
                self.assertTrue(any("offline authority reference" in r for r in reasons))
        for authority in (
            "https://example.invalid/synthetic/rights-not-real",
            "urn:pya:synthetic:authority:fixture",
        ):
            with self.subTest(authority=authority):
                rights = deepcopy(self.rights)
                rights["authority_ref"] = authority
                allowed, reasons = MODULE.fixture_policy_decision(
                    [self.record], [rights], "display", self.product)
                self.assertTrue(allowed, reasons)

    def test_direct_gate_rejects_nonreserved_source_urls(self):
        # Offline-only reserved test domains: this test makes no network requests.
        for source_url in (
            "https://different.invalid/fictional",
            "https://example.invalid@different.invalid/fictional",
            "https://example.invalid/synthetic?token=fake",
            "http://example.invalid/synthetic/source",
            "ftp://example.invalid/synthetic/source",
            "https://example.invalid:8443/synthetic/source",
            "https://example.invalid/synthetic/source#fragment",
            "https://example.invalid/synthetic/source\n",
            "https://example.invalid/synthetic/source?",
            "https://example.invalid/synthetic/source#",
            "https://example.invalid/synthetic/raw\x00nul",
            "https://example.invalid/synthetic/raw space",
            "https://example.invalid/synthetic/raw\\backslash",
            "https://example.invalid/synthetic/bad%",
            "https://example.invalid/synthetic/bad%0G",
            "https://example.invalid/synthetic/bad%A",
            "https://example.invalid/synthetic/raw<angle",
            "https://example.invalid/synthetic/raw[bracket",
            "https://example.invalid/synthetic/rawévalue",
        ):
            with self.subTest(source_url=source_url):
                record = deepcopy(self.record)
                record["claims"][0]["sources"][0]["url"] = source_url
                allowed, reasons = MODULE.fixture_policy_decision(
                    [record], [deepcopy(self.rights)], "display", self.product
                )
                self.assertFalse(allowed)
                self.assertTrue(any("reserved offline source" in item for item in reasons))
        self.assertTrue(self.decision())

    def test_cli_rejects_noncanonical_reserved_source_url_with_pinned_checksum(self):
        # Deliberately update the byte-integrity receipt so a URL-policy
        # rejection, not a stale manifest hash, is the deciding condition.
        for source_url in (
            "http://example.invalid/synthetic/source",
            "ftp://example.invalid/synthetic/source",
            "https://example.invalid:8443/synthetic/source",
            "https://example.invalid/synthetic/source#fragment",
            "https://example.invalid/synthetic/source\n",
            "https://example.invalid/synthetic/source?",
            "https://example.invalid/synthetic/source#",
            "https://example.invalid/synthetic/raw\x00nul",
            "https://example.invalid/synthetic/raw space",
            "https://example.invalid/synthetic/raw\\backslash",
            "https://example.invalid/synthetic/bad%",
            "https://example.invalid/synthetic/bad%0G",
            "https://example.invalid/synthetic/bad%A",
            "https://example.invalid/synthetic/raw<angle",
            "https://example.invalid/synthetic/raw[bracket",
            "https://example.invalid/synthetic/rawévalue",
        ):
            with self.subTest(source_url=source_url):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    shutil.copytree(ROOT / "examples", root / "examples")
                    shutil.copytree(ROOT / "schemas/v0.1", root / "schemas/v0.1")
                    record_path = root / "examples/synthetic-model.json"
                    record = json.loads(record_path.read_text())
                    record["claims"][0]["sources"][0]["url"] = source_url
                    record_path.write_text(json.dumps(record))
                    release_path = root / "examples/synthetic-release.json"
                    release = json.loads(release_path.read_text())
                    for artifact in release["artifacts"]:
                        if artifact["path"] == "examples/synthetic-model.json":
                            artifact["sha256"] = hashlib.sha256(record_path.read_bytes()).hexdigest()
                    release_path.write_text(json.dumps(release))
                    errors = MODULE.validate(root)
                    self.assertTrue(
                        any("examples require credential-free reserved source URLs" in error
                            for error in errors), errors
                    )
                    self.assertFalse(any("checksum mismatch" in error for error in errors))

    def test_cli_accepts_rfc3986_reserved_path_characters_and_encoded_octets(self):
        for path in (
            "/synthetic/AZaz09-._~!$&'()*+,;=:@",
            "/synthetic/encoded%20space",
            "/synthetic/encoded%2Fslash",
            "/synthetic/encoded%5Cbackslash",
            "/synthetic/encoded%00nul",
            "/synthetic/encoded%3Cangle%5Bbracket",
            "/synthetic/encoded%c3%a9",
        ):
            with self.subTest(path=path):
                with tempfile.TemporaryDirectory() as tmp:
                    root = Path(tmp)
                    shutil.copytree(ROOT / "examples", root / "examples")
                    shutil.copytree(ROOT / "schemas/v0.1", root / "schemas/v0.1")
                    record_path = root / "examples/synthetic-model.json"
                    record = json.loads(record_path.read_text())
                    record["claims"][0]["sources"][0]["url"] = "https://example.invalid" + path
                    record_path.write_text(json.dumps(record))
                    release_path = root / "examples/synthetic-release.json"
                    release = json.loads(release_path.read_text())
                    for artifact in release["artifacts"]:
                        if artifact["path"] == "examples/synthetic-model.json":
                            artifact["sha256"] = hashlib.sha256(record_path.read_bytes()).hexdigest()
                    release_path.write_text(json.dumps(release))
                    errors = MODULE.validate(root)
                    self.assertFalse(errors, errors)

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

    def test_direct_gate_never_invokes_payload_metaclass_comparisons(self):
        class ComparisonTrap(type):
            def __eq__(cls, other):
                raise AssertionError("A payload-defined comparison was invoked")

        class UntrustedValue(metaclass=ComparisonTrap):
            pass

        record = deepcopy(self.record)
        record["unknowns"] = UntrustedValue()
        allowed, reasons = MODULE.fixture_policy_decision(
            [record], [self.rights], "display", self.product
        )
        self.assertFalse(allowed, reasons)

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

    def test_pending_fixture_work_remains_memory_bounded(self):
        # Shared-reference Python containers are not JSON wire data, but the
        # directly callable fixture guard must not amplify pending allocations.
        if tracemalloc.is_tracing():
            env = dict(os.environ)
            env.pop("PYTHONTRACEMALLOC", None)
            command = [sys.executable, "-c",
                       "import json, tracemalloc; "
                       "from tests.test_examples import _measure_pending_fixture_work; "
                       "tracemalloc.stop(); print(json.dumps(_measure_pending_fixture_work()))"]
            result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True,
                                    text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(tracemalloc.is_tracing())
            measured = json.loads(result.stdout)
        else:
            measured = _measure_pending_fixture_work()
            self.assertFalse(tracemalloc.is_tracing())
        self.assertFalse(measured["accepted"])
        self.assertLess(measured["peak"], 2_000_000)

    def test_pending_fixture_work_counts_dict_keys_and_values(self):
        self.assertTrue(MODULE._bounded_fixture_data([0] * 9_999))
        self.assertFalse(MODULE._bounded_fixture_data([0] * 10_000))
        self.assertTrue(MODULE._bounded_fixture_data({str(i): i for i in range(4_999)}))
        self.assertFalse(MODULE._bounded_fixture_data({str(i): i for i in range(5_000)}))

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
